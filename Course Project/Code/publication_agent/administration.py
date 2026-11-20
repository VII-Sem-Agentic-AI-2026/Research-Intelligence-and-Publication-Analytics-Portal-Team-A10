"""Administrator deletion of report records with durable anti-restore markers."""
import json
from .accounts import require
from .core import load,now

def delete_report(actions,body):
    require(actions.user,'delete_reports')
    run=actions.checked_run(body.get('run_id'))
    if run['status']=='RUNNING':raise ValueError('Wait for the running report to finish before deleting it')
    store=actions.accounts.store;run_id=run['run_id']
    history=load(store.root/'history.json',[]) or []
    with store.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        keys={f'runs/{run_id}.json'}
        for key,raw in db.execute("SELECT path,body FROM documents WHERE path LIKE 'published/%'").fetchall():
            if json.loads(raw).get('run_id')==run_id:keys.add(key)
        for version,raw in db.execute('SELECT version,body FROM releases').fetchall():
            if json.loads(raw).get('run_id')==run_id:
                keys.add(f'published/version-{version}.json')
                db.execute('DELETE FROM releases WHERE version=?',(version,))
        # Older installations can still have compatibility-only release files.
        for path in (store.root/'published').glob('version-*.json'):
            value=load(path)
            if value and value.get('run_id')==run_id:keys.add(store.key(path))
        current=load(store.root/'published'/'current.json')
        if current and current.get('run_id')==run_id:keys.add('published/current.json')
        store.delete_documents(db,keys)
        if any(h.get('run_id')==run_id for h in history):
            filtered=[h for h in history if h.get('run_id')!=run_id]
            db.execute("INSERT OR REPLACE INTO documents VALUES ('history.json',?)",(json.dumps(filtered),))
            db.execute("INSERT OR IGNORE INTO compatibility_exports VALUES ('history.json')")
        if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='dean_review_requests'").fetchone():
            db.execute("UPDATE dean_review_requests SET status='cancelled',response_note='Report deleted by administrator',responded_at=? WHERE run_id=? AND status IN ('pending','accepted')",(now(),run_id))
        db.execute('INSERT INTO deletion_events VALUES (?,?,?,?)',(actions.user['id'],'report',run_id,now()))
    if actions.service.app.runtime.current and actions.service.app.runtime.current.run_id==run_id:actions.service.app.runtime.current=None
    return {'deleted':True,'run_id':run_id,'warnings':store.export_pending()}
