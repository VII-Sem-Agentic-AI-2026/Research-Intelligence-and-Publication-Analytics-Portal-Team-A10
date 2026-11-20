"""Transactional local persistence. JSON files remain compatibility exports."""
from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
import uuid
import zipfile
from contextlib import contextmanager
from pathlib import Path

_locks: dict[str, threading.RLock] = {}
_guard = threading.Lock()


def runtime_root(path: Path):
    return next((p for p in (path.parent, *path.parents) if p.name == 'runtime'), None)


@contextmanager
def locked(root):
    key = str(Path(root).resolve())
    with _guard:
        lock = _locks.setdefault(key, threading.RLock())
    with lock:
        yield


class Store:
    def __init__(self, root):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS documents(path TEXT PRIMARY KEY, body TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS releases(version INTEGER PRIMARY KEY AUTOINCREMENT, body TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS publications(id TEXT PRIMARY KEY, body TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS faculty_publications(faculty_id TEXT, publication_id TEXT REFERENCES publications(id), PRIMARY KEY(faculty_id, publication_id));
                CREATE TABLE IF NOT EXISTS imports(id TEXT PRIMARY KEY, filename TEXT, sha256 TEXT, content BLOB NOT NULL);
                CREATE TABLE IF NOT EXISTS compatibility_exports(path TEXT PRIMARY KEY);
                CREATE TABLE IF NOT EXISTS deleted_documents(path TEXT PRIMARY KEY,cleaned INTEGER NOT NULL DEFAULT 0);
                CREATE TABLE IF NOT EXISTS deletion_events(actor_id INTEGER,entity TEXT,target TEXT,happened TEXT);
            ''')

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.root / 'portal.sqlite3', timeout=30)
        try:
            db.execute('PRAGMA foreign_keys=ON')
            db.execute('PRAGMA journal_mode=WAL')
            with db:
                yield db
        finally:
            db.close()

    def key(self, path):
        return Path(path).relative_to(self.root).as_posix()

    def export_pending(self):
        """Retry derived JSON exports without rewriting authoritative SQLite data."""
        warnings=[]
        with locked(self.root):
            with self.connect() as db:deleted=db.execute('SELECT path FROM deleted_documents WHERE cleaned=0').fetchall()
            for (key,) in deleted:
                path=(self.root/key).resolve()
                if not path.is_relative_to(self.root.resolve()):raise ValueError('Invalid deleted document path')
                try:
                    path.unlink(missing_ok=True)
                    with self.connect() as db:db.execute('UPDATE deleted_documents SET cleaned=1 WHERE path=?',(key,))
                except OSError:warnings.append('Deletion saved. File cleanup is pending and will be retried.')
            with self.connect() as db:
                rows=db.execute('SELECT e.path,d.body FROM compatibility_exports e JOIN documents d ON d.path=e.path').fetchall()
            for key,body in rows:
                path=self.root/key
                temp=path.with_suffix(path.suffix+'.'+uuid.uuid4().hex+'.tmp')
                try:
                    path.parent.mkdir(parents=True,exist_ok=True)
                    temp.write_text(body,encoding='utf-8')
                    temp.replace(path)
                    with self.connect() as db:db.execute('DELETE FROM compatibility_exports WHERE path=?',(key,))
                except OSError:
                    warnings.append('Saved successfully. A compatibility export is pending and will be retried.')
                    try:temp.unlink(missing_ok=True)
                    except OSError:pass
        return warnings

    def read(self, path):
        with self.connect() as db:
            if db.execute('SELECT 1 FROM deleted_documents WHERE path=?',(self.key(path),)).fetchone():return True,None
            row = db.execute('SELECT body FROM documents WHERE path=?', (self.key(path),)).fetchone()
        return (True, json.loads(row[0])) if row else (False, None)

    def write(self, path, value):
        with self.connect() as db:
            if isinstance(value,dict) and value.get('run_id') and (self.key(path).startswith('published/') or self.key(path).startswith('runs/')):
                if db.execute('SELECT 1 FROM deleted_documents WHERE path=?',(f"runs/{value['run_id']}.json",)).fetchone():raise ValueError('This report has been deleted')
            if self.key(path)=='published/current.json':
                db.execute('DELETE FROM deleted_documents WHERE path=?',(self.key(path),))
            elif db.execute('SELECT 1 FROM deleted_documents WHERE path=?',(self.key(path),)).fetchone():raise ValueError('This record has been deleted')
            db.execute('INSERT OR REPLACE INTO documents VALUES (?,?)', (self.key(path), json.dumps(value, ensure_ascii=False)))
            if Path(path).name == 'source_data.json':
                self.index_publications(db,value)

    def index_publications(self,db,value):
        from .core import deduplicate
        pubs, _ = deduplicate(value.get('publications', []))
        db.execute('DELETE FROM faculty_publications')
        db.execute('DELETE FROM publications')
        for p in pubs:
            db.execute('INSERT INTO publications VALUES (?,?)', (p['publication_id'], json.dumps(p)))
        for p in value.get('publications', []):
            identity = deduplicate([p])[0][0]['publication_id']
            db.execute('INSERT OR IGNORE INTO faculty_publications VALUES (?,?)', (p['faculty_id'], identity))

    def delete_documents(self,db,keys):
        for key in keys:
            db.execute('INSERT OR IGNORE INTO deleted_documents(path) VALUES (?)',(key,))
            db.execute('DELETE FROM compatibility_exports WHERE path=?',(key,))
            db.execute('DELETE FROM documents WHERE path=?',(key,))

    def archive(self, filename, content):
        digest = hashlib.sha256(content).hexdigest()
        with self.connect() as db:
            db.execute('INSERT INTO imports VALUES (?,?,?,?)', (uuid.uuid4().hex, Path(filename).name, digest, content))
        return digest

    def release(self, report):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            if db.execute('SELECT 1 FROM deleted_documents WHERE path=?',(f"runs/{report.get('run_id')}.json",)).fetchone():raise ValueError('This report has been deleted')
            # Preserve version numbers from existing installations.
            for path in sorted((self.root / 'published').glob('version-*.json')):
                if db.execute('SELECT 1 FROM deleted_documents WHERE path=?',(self.key(path),)).fetchone():continue
                old = json.loads(path.read_text(encoding='utf-8'))
                db.execute('INSERT OR IGNORE INTO releases VALUES (?,?)', (old['version'], json.dumps(old)))
            row = db.execute('INSERT INTO releases(body) VALUES (?)', ('{}',))
            report['version'] = row.lastrowid
            body = json.dumps(report, ensure_ascii=False)
            db.execute('UPDATE releases SET body=? WHERE version=?', (body, report['version']))
            db.execute("DELETE FROM deleted_documents WHERE path='published/current.json'")
            db.execute('INSERT OR REPLACE INTO documents VALUES (?,?)', ('published/current.json', body))
        return report

    def migrate(self):
        """One-time import; original files and approved releases are untouched."""
        pending=[p for p in self.root.rglob('*.json') if not self.read(p)[0]]
        if pending:
            backup=self.root / ('pre-migration-' + uuid.uuid4().hex + '.zip')
            with zipfile.ZipFile(backup,'x',compression=zipfile.ZIP_DEFLATED) as archive:
                for path in pending:
                    archive.write(path,path.relative_to(self.root))
        for path in self.root.rglob('*.json'):
            found, _ = self.read(path)
            if not found:
                self.write(path, json.loads(path.read_text(encoding='utf-8')))


@contextmanager
def single_server(root):
    """Serialize filesystem compatibility exports by allowing one server per root."""
    path=Path(root)/'server.lock'
    path.parent.mkdir(parents=True,exist_ok=True)
    handle=path.open('a+b')
    try:
        handle.write(b'0');handle.flush();handle.seek(0)
        if __import__('os').name=='nt':
            import msvcrt
            msvcrt.locking(handle.fileno(),msvcrt.LK_NBLCK,1)
        else:
            import fcntl
            fcntl.flock(handle.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        yield
    finally:
        handle.close()
