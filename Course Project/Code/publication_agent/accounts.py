"""Password accounts and revocable sessions with server-side authorization."""
import hashlib
import hmac
import re
import secrets
import time
from http.cookies import SimpleCookie
from .storage import Store

PERMISSIONS={
 'admin': {'accounts','read','run','import','profile','delete_reports'},
 'dean': {'read','run','review','publish','rollback','respond_review_request'},
 'hod': {'read','run','review','publish'},
 'research_office': {'read','run','review','publish','rollback','import','profile','request_consent','request_dean_review'},
 'faculty': {'self_read','self_profile','self_upload','respond_consent'},
}
ROLE_LABELS={'dean':'Research Dean','hod':'HoD','research_office':'Research Office','admin':'Administrator','faculty':'Faculty'}
class Forbidden(PermissionError): pass
class AuthenticationError(PermissionError): pass

def require(identity,permission):
    if permission not in PERMISSIONS.get(identity['role'],set()):raise Forbidden('Your account is not authorized for this action')

class Accounts:
    def __init__(self,root):
        self.store=Store(root)
        with self.store.connect() as db:
            db.executescript('''
            CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY,username TEXT UNIQUE NOT NULL,name TEXT NOT NULL,role TEXT NOT NULL,faculty_id TEXT,department TEXT,password_hash TEXT NOT NULL,salt TEXT NOT NULL,active INTEGER NOT NULL DEFAULT 1);
            CREATE TABLE IF NOT EXISTS sessions(digest TEXT PRIMARY KEY,user_id INTEGER REFERENCES users(id),expires REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS login_attempts(username TEXT,address TEXT,attempted REAL);
            CREATE TABLE IF NOT EXISTS account_events(actor TEXT,action TEXT,target TEXT,happened REAL);
            CREATE TABLE IF NOT EXISTS account_id_sequence(singleton INTEGER PRIMARY KEY CHECK(singleton=1),next_id INTEGER NOT NULL);
            INSERT OR IGNORE INTO account_id_sequence SELECT 1,COALESCE(MAX(id),0)+1 FROM users;
            ''')
            db.execute('BEGIN IMMEDIATE')
            columns={r[1] for r in db.execute('PRAGMA table_info(users)')}
            if 'department_confirmed' not in columns:
                db.execute('ALTER TABLE users ADD COLUMN department_confirmed INTEGER NOT NULL DEFAULT 0')

    @staticmethod
    def hash(password,salt):
        return hashlib.pbkdf2_hmac('sha256',password.encode(),bytes.fromhex(salt),600000).hex()

    @staticmethod
    def public(row):
        return dict(zip(('id','username','name','role','faculty_id','department','active','department_confirmed'),row))

    def needs_setup(self):
        with self.store.connect() as db:return db.execute('SELECT count(*) FROM users').fetchone()[0]==0

    def create(self,data,actor=None,bootstrap=False):
        username=str(data.get('username','')).strip().lower();password=data.get('password','');role=data.get('role','faculty')
        if not re.fullmatch(r'[a-z0-9][a-z0-9_.@-]{2,79}',username):raise ValueError('Login ID must be 3–80 letters, digits, dots, hyphens, underscores or @')
        if not isinstance(password,str) or not 12<=len(password)<=128:raise ValueError('Password must contain 12–128 characters')
        if role not in PERMISSIONS:raise ValueError('Unknown role')
        if bootstrap and role!='admin':raise Forbidden('First account must be an administrator')
        if role=='faculty' and not data.get('faculty_id'):raise ValueError('Assign a faculty profile')
        if role=='hod' and not data.get('department'):raise ValueError('Assign a department for the HoD')
        name=str(data.get('name','')).strip()
        if not name:raise ValueError('Display name is required')
        salt=secrets.token_hex(16);hashed=self.hash(password,salt)
        with self.store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            if bootstrap:
                if db.execute('SELECT count(*) FROM users').fetchone()[0]:raise Forbidden('Setup is already complete')
            else:
                current=db.execute('SELECT role,active FROM users WHERE id=?',((actor or {}).get('id'),)).fetchone()
                if current!=('admin',1):raise Forbidden('Administrator access required')
            if role=='faculty' and db.execute("SELECT id FROM users WHERE faculty_id=? AND role='faculty' AND active=1",(data['faculty_id'],)).fetchone():raise ValueError('Faculty profile already has an active account')
            user_id=db.execute('SELECT next_id FROM account_id_sequence WHERE singleton=1').fetchone()[0]
            db.execute('UPDATE account_id_sequence SET next_id=next_id+1 WHERE singleton=1')
            db.execute('INSERT INTO users(id,username,name,role,faculty_id,department,password_hash,salt) VALUES (?,?,?,?,?,?,?,?)',(user_id,username,name,role,data.get('faculty_id') if role=='faculty' else None,str(data.get('department','')).upper(),hashed,salt))
            db.execute('INSERT INTO account_events VALUES (?,?,?,?)',((actor or {}).get('username','first-run'),'create',username,time.time()))
        return {'username':username,'role':role}

    def login(self,username,password,address='local'):
        username=str(username).strip().lower();stamp=time.time()
        if not isinstance(password,str) or len(password)>128:raise AuthenticationError('Invalid login ID or password')
        with self.store.connect() as db:
            db.execute('DELETE FROM login_attempts WHERE attempted<?',(stamp-900,))
            if db.execute('SELECT count(*) FROM login_attempts WHERE username=? AND address=?',(username,address)).fetchone()[0]>=5:raise AuthenticationError('Too many attempts. Try again in 15 minutes')
            db.execute('INSERT INTO login_attempts VALUES (?,?,?)',(username,address,stamp))
            row=db.execute('SELECT id,password_hash,salt,active FROM users WHERE username=?',(username,)).fetchone()
        digest=self.hash(password,row[2] if row else '00'*16)
        if not row or not row[3] or not hmac.compare_digest(digest,row[1]):raise AuthenticationError('Invalid login ID or password')
        token=secrets.token_urlsafe(32)
        with self.store.connect() as db:
            db.execute('DELETE FROM login_attempts WHERE username=? AND address=?',(username,address))
            db.execute('DELETE FROM sessions WHERE expires<?',(stamp,))
            db.execute('INSERT INTO sessions VALUES (?,?,?)',(hashlib.sha256(token.encode()).hexdigest(),row[0],stamp+3600))
        return token

    def digest(self,headers):
        cookie=SimpleCookie()
        try:
            cookie.load(headers.get('Cookie',''));return hashlib.sha256(cookie['portal_session'].value.encode()).hexdigest()
        except (KeyError,ValueError):raise AuthenticationError('Sign in to continue')

    def principal(self,headers):
        with self.store.connect() as db:
            row=db.execute('SELECT u.id,u.username,u.name,u.role,u.faculty_id,u.department,u.active,u.department_confirmed FROM users u JOIN sessions s ON s.user_id=u.id WHERE s.digest=? AND s.expires>? AND u.active=1',(self.digest(headers),time.time())).fetchone()
        if not row:raise AuthenticationError('Session expired; sign in again')
        return self.public(row)

    def logout(self,headers):
        with self.store.connect() as db:db.execute('DELETE FROM sessions WHERE digest=?',(self.digest(headers),))

    def users(self):
        with self.store.connect() as db:return [self.public(r) for r in db.execute('SELECT id,username,name,role,faculty_id,department,active,department_confirmed FROM users ORDER BY username')]

    def confirm_department(self,identity,department,service):
        """Commit the account and its linked dataset profile in one transaction."""
        import json
        from .core import load, now
        from .validation import validate_dataset
        if identity['role']!='faculty':raise Forbidden('Faculty account required')
        if not isinstance(department,str) or not department.strip() or len(department)>160:
            raise ValueError('Select a department')
        department=department.strip().upper()
        with self.store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('SELECT faculty_id,department_confirmed,active FROM users WHERE id=?',(identity['id'],)).fetchone()
            if not row or not row[2]:raise Forbidden('This account is no longer active')
            if row[1]:raise ValueError('Department is already confirmed; contact the administrator for corrections')
            data_row=db.execute("SELECT body FROM documents WHERE path='source_data.json'").fetchone()
            data=json.loads(data_row[0]) if data_row else load(service.active_data_path(),{'faculty':[],'publications':[]})
            choices={str(f.get('department','')).strip().upper() for f in data['faculty']} | {'CSE','ECE','EEE','ME','CE','IT','AI','DS'}
            if department not in choices:raise ValueError('Choose a department from the available list')
            profile=next((f for f in data['faculty'] if f['faculty_id']==row[0]),None)
            if profile is None:raise ValueError('Assigned faculty profile is unavailable')
            profile.update(department=department,department_confirmed_at=now(),department_confirmed_by=identity['username'])
            validate_dataset(data)
            db.execute("INSERT OR REPLACE INTO documents VALUES ('source_data.json',?)",(json.dumps(data,ensure_ascii=False),))
            db.execute("INSERT OR IGNORE INTO compatibility_exports VALUES ('source_data.json')")
            db.execute('UPDATE users SET department=?,department_confirmed=1 WHERE id=?',(department,identity['id']))
            db.execute('INSERT INTO account_events VALUES (?,?,?,?)',(identity['username'],'confirm_department',row[0],time.time()))
        warnings=self.store.export_pending()
        service.reload_connector()
        return {'saved':True,'department':department,'warnings':warnings}

    def disable(self,user_id,actor):
        require(actor,'accounts')
        if user_id==actor['id']:raise ValueError('You cannot disable your own account')
        with self.store.connect() as db:
            db.execute('UPDATE users SET active=0 WHERE id=?',(user_id,));db.execute('DELETE FROM sessions WHERE user_id=?',(user_id,))
            db.execute('INSERT INTO account_events VALUES (?,?,?,?)',(actor['username'],'disable',str(user_id),time.time()))

    def delete(self,user_id,actor):
        require(actor,'accounts')
        if user_id==actor['id']:raise ValueError('You cannot delete your own account')
        with self.store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            if db.execute('SELECT role,active FROM users WHERE id=?',(actor['id'],)).fetchone()!=('admin',1):raise Forbidden('Administrator access required')
            target=db.execute('SELECT username,active FROM users WHERE id=?',(user_id,)).fetchone()
            if not target:raise ValueError('Account not found')
            if target[1]:raise ValueError('Disable the account before deleting it')
            db.execute('DELETE FROM sessions WHERE user_id=?',(user_id,))
            if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='assistant_pending'").fetchone():db.execute('DELETE FROM assistant_pending WHERE user_id=?',(user_id,))
            db.execute('DELETE FROM login_attempts WHERE username=?',(target[0],))
            self.store.delete_documents(db,[f'assistant/user-{user_id}.json',f'conversations/account-{user_id}.json'])
            db.execute('DELETE FROM users WHERE id=?',(user_id,))
            db.execute('INSERT INTO account_events VALUES (?,?,?,?)',(actor['username'],'delete',str(user_id),time.time()))
        return {'deleted':True,'user_id':user_id,'warnings':self.store.export_pending()}

    def change_password(self,identity,current,replacement):
        if not isinstance(replacement,str) or not 12<=len(replacement)<=128:raise ValueError('New password must contain 12–128 characters')
        with self.store.connect() as db:
            row=db.execute('SELECT password_hash,salt FROM users WHERE id=?',(identity['id'],)).fetchone()
            if not isinstance(current,str) or len(current)>128 or not hmac.compare_digest(self.hash(current,row[1]),row[0]):raise PermissionError('Current password is incorrect')
            salt=secrets.token_hex(16)
            db.execute('UPDATE users SET password_hash=?,salt=? WHERE id=?',(self.hash(replacement,salt),salt,identity['id']))
            db.execute('DELETE FROM sessions WHERE user_id=?',(identity['id'],))
