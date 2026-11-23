"""Persisted faculty consent requests and named-Dean human-review assignments."""
import json
import hashlib
import uuid
from dataclasses import asdict
from datetime import datetime,timezone,timedelta
from .accounts import require, Forbidden
from .core import load, now
from .validation import validate_dataset, validate_profile_links

class HumanWorkflow:
    def __init__(self,actions):
        self.actions=actions;self.store=actions.accounts.store;self.user=actions.user
        with self.store.connect() as db:
            db.executescript('''
            CREATE TABLE IF NOT EXISTS consent_requests(id TEXT PRIMARY KEY,faculty_id TEXT NOT NULL,requester_id INTEGER NOT NULL,requester_name TEXT NOT NULL,sources TEXT NOT NULL,links TEXT NOT NULL,message TEXT NOT NULL,status TEXT NOT NULL,created_at TEXT NOT NULL,expires_at TEXT NOT NULL,responded_by INTEGER,response_note TEXT,responded_at TEXT);
            CREATE TABLE IF NOT EXISTS dean_review_requests(id TEXT PRIMARY KEY,run_id TEXT NOT NULL,requester_id INTEGER NOT NULL,dean_id INTEGER NOT NULL,status TEXT NOT NULL,message TEXT NOT NULL,created_at TEXT NOT NULL,response_note TEXT,responded_at TEXT);
            CREATE UNIQUE INDEX IF NOT EXISTS one_active_dean_request ON dean_review_requests(run_id) WHERE status IN ('pending','accepted');
            CREATE TABLE IF NOT EXISTS workflow_events(actor_id INTEGER,action TEXT,entity_id TEXT,details TEXT,happened_at TEXT);
            ''')
            if 'batch_id' not in {r[1] for r in db.execute('PRAGMA table_info(consent_requests)')}:
                db.execute('ALTER TABLE consent_requests ADD COLUMN batch_id TEXT')

    def event(self,db,action,entity,details):
        db.execute('INSERT INTO workflow_events VALUES (?,?,?,?,?)',(self.user['id'],action,entity,json.dumps(details),now()))

    def inbox(self):
        user=self.user
        with self.store.connect() as db:
            db.row_factory=__import__('sqlite3').Row
            db.execute("UPDATE consent_requests SET status='expired' WHERE status='pending' AND expires_at<?",(now(),))
            if user['role']=='faculty':rows=db.execute('SELECT * FROM consent_requests WHERE faculty_id=? ORDER BY created_at DESC',(user['faculty_id'],)).fetchall()
            elif user['role'] in {'research_office','admin'}:rows=db.execute('SELECT * FROM consent_requests ORDER BY created_at DESC').fetchall()
            else:rows=[]
            consent=[]
            for row in rows:
                value=dict(row);value['sources']=json.loads(value['sources']);value['links']=json.loads(value['links']);consent.append(value)
            if user['role']=='dean':reviews=db.execute('SELECT * FROM dean_review_requests WHERE dean_id=? ORDER BY created_at DESC',(user['id'],)).fetchall()
            elif user['role'] in {'research_office','admin'}:reviews=db.execute('SELECT * FROM dean_review_requests ORDER BY created_at DESC').fetchall()
            else:reviews=[]
        return {'consent_requests':consent,'review_requests':[dict(r) for r in reviews]}

    def request_consent(self,body):
        require(self.user,'request_consent')
        faculty_id=body['faculty_id'];sources=body.get('sources');links=body.get('profiles',{})
        if not isinstance(sources,list) or not sources or any(s not in {'scholar','scopus','wos'} for s in sources):raise ValueError('Select one or more supported sources')
        sources=sorted(set(sources))
        if not isinstance(links,dict):raise ValueError('Profile links must be an object')
        profile=next((f for f in self.actions.service.faculty_profiles() if f['faculty_id']==faculty_id),None)
        if not profile:raise ValueError('Faculty profile not found')
        if not any(u['active'] and u['role']=='faculty' and u['faculty_id']==faculty_id for u in self.actions.accounts.users()):raise ValueError('Create an active faculty account before requesting consent')
        proposed_links={s:links.get(s,profile.get('profiles',{}).get(s,'')) for s in sources}
        validate_profile_links({'consent':{s:True for s in sources},'profiles':proposed_links})
        message=str(body.get('message','')).strip()
        if not 1<=len(message)<=2000:raise ValueError('Provide a purpose/message of 1–2000 characters')
        request_id=uuid.uuid4().hex;created=now();expires=(datetime.now(timezone.utc)+timedelta(days=7)).isoformat()
        with self.store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            pending=db.execute("SELECT sources FROM consent_requests WHERE faculty_id=? AND status='pending' AND expires_at>?",(faculty_id,created)).fetchall()
            if any(set(json.loads(row[0]))&set(sources) for row in pending):raise ValueError('A pending request already exists for one of these sources')
            db.execute('INSERT INTO consent_requests(id,faculty_id,requester_id,requester_name,sources,links,message,status,created_at,expires_at) VALUES (?,?,?,?,?,?,?,?,?,?)',(request_id,faculty_id,self.user['id'],self.user['name'],json.dumps(sources),json.dumps(proposed_links),message,'pending',created,expires))
            self.event(db,'consent.requested',request_id,{'faculty_id':faculty_id,'sources':sources})
        return {'request_id':request_id,'status':'pending','faculty_id':faculty_id}

    def _consent_batch_plan(self,db,body):
        scope=body.get('scope')
        if scope not in {'department','institution'}:raise ValueError('Choose department or institution scope')
        sources=body.get('sources')
        if not isinstance(sources,list) or not sources or any(s not in {'scholar','scopus','wos'} for s in sources):
            raise ValueError('Select one or more supported sources')
        sources=sorted(set(sources));message=str(body.get('message','')).strip()
        if not 1<=len(message)<=2000:raise ValueError('Provide a purpose/message of 1–2000 characters')
        department=str(body.get('department','')).strip()
        stored=db.execute("SELECT body FROM documents WHERE path='source_data.json'").fetchone()
        profiles=json.loads(stored[0])['faculty'] if stored else self.actions.service.faculty_profiles()
        if scope=='department':
            profiles=[f for f in profiles if f['department'].casefold()==department.casefold()]
            if not department or not profiles:raise ValueError('Choose an existing department')
        active={r[0] for r in db.execute("SELECT faculty_id FROM users WHERE active=1 AND role='faculty'")}
        pending={}
        for faculty_id,source_json in db.execute("SELECT faculty_id,sources FROM consent_requests WHERE status='pending' AND expires_at>?",(now(),)):
            pending.setdefault(faculty_id,set()).update(json.loads(source_json))
        recipients=[];skipped=[]
        for profile in profiles:
            fid=profile['faculty_id'];item={'faculty_id':fid,'name':profile['name'],'department':profile['department']}
            if fid not in active:
                skipped.append({**item,'reason':'No active faculty account'});continue
            missing=[s for s in sources if not profile.get('consent',{}).get(s)]
            if not missing:
                skipped.append({**item,'reason':'Consent already granted for selected sources'});continue
            requested=[s for s in missing if s not in pending.get(fid,set())]
            if not requested:
                skipped.append({**item,'reason':'An active request already covers these sources'});continue
            links={s:profile.get('profiles',{}).get(s,'') for s in requested}
            try:validate_profile_links({'consent':{s:True for s in requested},'profiles':links})
            except ValueError as exc:
                skipped.append({**item,'reason':'Missing or invalid saved profile link: '+str(exc)});continue
            recipients.append({**item,'sources':requested,'profiles':links})
        plan={'scope':scope,'department':department if scope=='department' else '', 'message':message,
              'sources':sources,'recipients':recipients,'skipped':skipped,'recipient_count':len(recipients),'skipped_count':len(skipped)}
        plan['preview_token']=hashlib.sha256(json.dumps(plan,sort_keys=True).encode()).hexdigest()
        return plan

    def request_consent_batch(self,body):
        require(self.user,'request_consent')
        with self.store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            plan=self._consent_batch_plan(db,body)
            if body.get('confirm') is not True:return {**plan,'status':'preview'}
            if body.get('preview_token')!=plan['preview_token']:
                raise ValueError('Recipients or request details changed. Preview the request again before sending.')
            if not plan['recipients']:raise ValueError('No eligible faculty recipients. Review the skipped reasons.')
            batch_id=uuid.uuid4().hex;created=now();expires=(datetime.now(timezone.utc)+timedelta(days=7)).isoformat()
            for recipient in plan['recipients']:
                request_id=uuid.uuid4().hex
                db.execute('INSERT INTO consent_requests(id,faculty_id,requester_id,requester_name,sources,links,message,status,created_at,expires_at,batch_id) VALUES (?,?,?,?,?,?,?,?,?,?,?)',
                    (request_id,recipient['faculty_id'],self.user['id'],self.user['name'],json.dumps(recipient['sources']),json.dumps(recipient['profiles']),plan['message'],'pending',created,expires,batch_id))
                self.event(db,'consent.requested',request_id,{'faculty_id':recipient['faculty_id'],'sources':recipient['sources'],'batch_id':batch_id})
            self.event(db,'consent.batch_requested',batch_id,{'scope':plan['scope'],'department':plan['department'],'sent':plan['recipient_count'],'skipped':plan['skipped_count']})
        return {'batch_id':batch_id,'status':'pending','sent':plan['recipient_count'],'skipped':plan['skipped_count']}

    def respond_consent(self,body):
        require(self.user,'respond_consent');decision=body.get('decision')
        if decision not in {'approved','declined'}:raise ValueError('Decision must be approved or declined')
        note=str(body.get('note','')).strip()
        if len(note)>2000:raise ValueError('Response note is too long')
        fallback=load(self.actions.service.active_data_path())
        with self.store.connect() as db:
            db.row_factory=__import__('sqlite3').Row;db.execute('BEGIN IMMEDIATE')
            row=db.execute('SELECT * FROM consent_requests WHERE id=?',(body['request_id'],)).fetchone()
            if not row or row['faculty_id']!=self.user['faculty_id']:raise Forbidden('This consent request is not assigned to you')
            if row['status']!='pending' or row['expires_at']<now():raise ValueError('Request is already answered or expired')
            if decision=='approved':
                stored=db.execute("SELECT body FROM documents WHERE path='source_data.json'").fetchone()
                data=json.loads(stored[0]) if stored else fallback
                profile=next((f for f in data['faculty'] if f['faculty_id']==self.user['faculty_id']),None)
                if not profile:raise ValueError('Faculty profile no longer exists')
                for source in json.loads(row['sources']):
                    profile.setdefault('consent',{})[source]=True
                    profile.setdefault('profiles',{})[source]=json.loads(row['links'])[source]
                profile.setdefault('consent_approvals',{})[row['id']]={'approved_by_user_id':self.user['id'],'approved_at':now(),'sources':json.loads(row['sources'])}
                validate_dataset(data)
                db.execute("INSERT OR REPLACE INTO documents VALUES ('source_data.json',?)",(json.dumps(data,ensure_ascii=False),))
                if not stored:self.store.index_publications(db,data)
                db.execute("INSERT OR IGNORE INTO compatibility_exports VALUES ('source_data.json')")
            db.execute('UPDATE consent_requests SET status=?,responded_by=?,response_note=?,responded_at=? WHERE id=?',(decision,self.user['id'],note,now(),row['id']))
            self.event(db,'consent.'+decision,row['id'],{'faculty_id':self.user['faculty_id'],'note':note})
        warnings=[]
        if decision=='approved':
            warnings=self.store.export_pending()
            self.actions.service.reload_connector()
        return {'request_id':body['request_id'],'status':decision,'warnings':warnings}

    def request_review(self,body):
        require(self.user,'request_dean_review');run=self.actions.checked_run(body['run_id'])
        if run['status']!='AWAITING_APPROVAL':raise ValueError('Only a validated pending draft can be assigned')
        dean=next((u for u in self.actions.accounts.users() if u['id']==int(body['dean_id']) and u['active'] and u['role']=='dean'),None)
        if not dean:raise ValueError('Select an active Dean account')
        request_id=uuid.uuid4().hex;message=str(body.get('message','')).strip()
        if not 1<=len(message)<=2000:raise ValueError('Provide a review request message')
        assignment={'request_id':request_id,'dean_id':dean['id'],'dean_name':dean['name'],'requester_id':self.user['id'],'requester_name':self.user['name'],'status':'pending','requested_at':now()}
        ctx=self.actions.service.app.runtime.load_run(run['run_id']);ctx.review_assignment=assignment;ctx.report['review_assignment']=assignment
        with self.store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            previous=db.execute("SELECT r.id,u.active FROM dean_review_requests r LEFT JOIN users u ON u.id=r.dean_id WHERE r.run_id=? AND r.status IN ('pending','accepted')",(run['run_id'],)).fetchone()
            if previous:
                if previous[1]:raise ValueError('This report already has an active Dean request')
                db.execute("UPDATE dean_review_requests SET status='cancelled',response_note='Reviewer account disabled; reassigned',responded_at=? WHERE id=?",(now(),previous[0]))
                self.event(db,'review.cancelled',previous[0],{'reason':'reviewer_disabled','replacement_request_id':request_id})
            db.execute('INSERT INTO dean_review_requests(id,run_id,requester_id,dean_id,status,message,created_at) VALUES (?,?,?,?,?,?,?)',(request_id,run['run_id'],self.user['id'],dean['id'],'pending',message,now()))
            db.execute('INSERT OR REPLACE INTO documents VALUES (?,?)',('runs/'+ctx.run_id+'.json',json.dumps(asdict(ctx),ensure_ascii=False)))
            self.event(db,'review.requested',request_id,{'run_id':run['run_id'],'dean_id':dean['id']})
        self.actions.service.app.runtime.checkpoint(ctx)
        return {'request_id':request_id,'status':'pending','dean_name':dean['name'],'run_id':run['run_id']}

    def respond_review(self,body):
        require(self.user,'respond_review_request');decision=body.get('decision')
        if decision not in {'accepted','declined'}:raise ValueError('Decision must be accepted or declined')
        with self.store.connect() as db:
            db.row_factory=__import__('sqlite3').Row;db.execute('BEGIN IMMEDIATE')
            row=db.execute('SELECT * FROM dean_review_requests WHERE id=?',(body['request_id'],)).fetchone()
            if not row or row['dean_id']!=self.user['id']:raise Forbidden('This review request is not assigned to you')
            if row['status']!='pending':raise ValueError('Review request has already been answered')
            stored=db.execute('SELECT body FROM documents WHERE path=?',('runs/'+row['run_id']+'.json',)).fetchone()
            if not stored:raise ValueError('Report no longer exists')
            value=json.loads(stored[0]);assignment=value.get('review_assignment',{})
            if assignment.get('request_id')!=row['id'] or value['status']!='AWAITING_APPROVAL':raise ValueError('Report assignment has changed')
            note=str(body.get('note','')).strip()
            if len(note)>2000:raise ValueError('Response note is too long')
            assignment.update(status=decision,responded_at=now());value['report']['review_assignment']=assignment
            db.execute('UPDATE dean_review_requests SET status=?,response_note=?,responded_at=? WHERE id=?',(decision,note,now(),row['id']))
            db.execute('UPDATE documents SET body=? WHERE path=?',(json.dumps(value,ensure_ascii=False),'runs/'+row['run_id']+'.json'))
            self.event(db,'review.'+decision,row['id'],{'run_id':row['run_id'],'note':note})
        ctx=self.actions.service.app.runtime.load_run(row['run_id']);self.actions.service.app.runtime.checkpoint(ctx)
        return {'request_id':row['id'],'status':decision,'run_id':row['run_id']}
