from __future__ import annotations
import base64, csv, io, json, os, re, uuid, hashlib
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse
from .core import DEFAULT_DATA, DEFAULT_RUNTIME, PublicationOrchestrator, compute_h_index, deduplicate, dump, load, now
from .importers import parse_faculty_roster, parse_publication_export
from .storage import Store, locked, single_server
from .validation import validate_dataset, validate_profile_links

REQUEST_LOCK = threading.RLock()

ROOT = Path(__file__).resolve().parents[1]
def conversation_path(s): return DEFAULT_RUNTIME/'conversations'/f"{re.sub(r'[^a-zA-Z0-9_-]','',s)}.json"
def all_runs():
    f=DEFAULT_RUNTIME/'runs'; return [v for p in sorted(f.glob('*.json'),reverse=True) if (v:=load(p))] if f.exists() else []

class DashboardService:
    def __init__(self, use_groq=False):
        self.use_groq=use_groq
        self.reload_connector()
    def active_data_path(self):
        p=DEFAULT_RUNTIME/'source_data.json'
        return p if p.exists() or Store(DEFAULT_RUNTIME).read(p)[0] else DEFAULT_DATA
    def reload_connector(self):
        Store(DEFAULT_RUNTIME).export_pending()
        self.app=PublicationOrchestrator(
            data_path=self.active_data_path(),
            runtime_root=DEFAULT_RUNTIME,
            use_groq=self.use_groq,
        )
    def chat(self,session_id,message,selected_labs=None,scope='cumulative_through_year'):
        self.reload_connector()
        path=conversation_path(session_id); state=load(path,{'session_id':session_id,'answers':{},'messages':[],'run_id':None})
        state['messages'].append({'role':'user','agent':'Human','text':message,'time':now()}); a=state['answers']
        a['scope']=scope
        from .core import resolve_department
        d=resolve_department(message); y=re.search(r'\b(20\d{2})\b',message)
        pack=next((x for x in ('bibliometric','collaboration','altmetric') if x in message.lower()),None)
        if d:a['department']=d
        if y:a['reporting_year']=int(y.group(1))
        if pack:a['metric_pack']=pack
        planned=self.app.make_plan(message,a)
        if not planned['complete']:
            state['messages'].append({'role':'agent','agent':'AURA Coordinator','text':'I need more information before I can lock the plan: '+' '.join(planned['questions']),'time':now()})
        else:
            state['messages'].append({'role':'agent','agent':'AURA Coordinator','text':'Plan locked. Starting the governed agent graph.','time':now()})
            ctx=self.app.run(message,a,selected_labs=selected_labs); state['run_id']=ctx.run_id
            state['requested_labs']=ctx.requested_labs; state['executed_labs']=ctx.executed_labs
            state['messages'].append({'role':'agent','agent':'AURA Coordinator','text':'Requested: '+', '.join(ctx.requested_labs)+'. Connected execution chain: '+', '.join(ctx.executed_labs)+'.','time':now()})
            state['messages'] += [{'role':'lab','agent':key.replace('lab','Lab '),'text':value['outcome'],'time':now()} for key,value in ctx.lab_results.items()]
            if ctx.report.get('groq_explanation'):
                state['messages'].append({'role':'agent','agent':'Gemini Research Analyst','text':ctx.report['groq_explanation'],'time':now()})
            final_text = 'The selected labs completed successfully.' if ctx.status == 'SELECTED_LABS_COMPLETED' else 'The full draft is waiting for an authorized human decision. I cannot publish it myself.'
            state['messages'].append({'role':'agent','agent':'AURA Coordinator','text':final_text,'time':now()})
            state['lab_results'] = ctx.lab_results
        dump(path,state); return state
    def import_data(self,value):
        validate_dataset(value)
        faculty=value.get('faculty') if isinstance(value,dict) else None; pubs=value.get('publications') if isinstance(value,dict) else None
        if not isinstance(faculty,list) or not isinstance(pubs,list): raise ValueError('Data must contain faculty and publications arrays')
        for x in faculty:
            if not all(k in x for k in ('faculty_id','name','department','consent')): raise ValueError('Every faculty record needs faculty_id, name, department and consent')
        for x in pubs:
            if not all(k in x for k in ('source_id','faculty_id','source','title','year','citations','url','retrieved')): raise ValueError('A publication record is missing provenance fields')
            if x['source'] not in {'scholar','scopus','wos'}: raise ValueError('Only chapter-defined sources are accepted')
        dump(DEFAULT_RUNTIME/'source_data.json',value); self.reload_connector(); return {'faculty':len(faculty),'publications':len(pubs),'status':'imported'}
    def faculty_profiles(self):
        return load(self.active_data_path(), {'faculty': []}).get('faculty', [])
    def save_faculty(self, profile):
        required=('faculty_id','name','department','consent','profiles')
        if not isinstance(profile,dict) or not all(k in profile for k in required): raise ValueError('Faculty profile is incomplete')
        consent=profile.get('consent',{}); links=profile.get('profiles',{})
        validate_profile_links(profile)
        for source in ('scholar','scopus','wos'):
            if consent.get(source) and not links.get(source): raise ValueError(f'{source} profile link is required when consent is granted')
        data=load(self.active_data_path(),{'faculty':[],'publications':[]}); existing=next((x for x in data['faculty'] if x.get('faculty_id')==profile['faculty_id']),None)
        action='updated' if existing else 'created'
        if existing: existing.update(profile)
        else: data['faculty'].append(profile)
        validate_dataset(data)
        dump(DEFAULT_RUNTIME/'source_data.json',data); self.reload_connector()
        return {'status':action,'profile':profile}
    def upload_export(self, filename, encoded, kind, source=None, faculty_id=None):
        if kind not in {'roster','publication'}:raise ValueError('Upload kind must be roster or publication')
        try: content=base64.b64decode(encoded,validate=True)
        except Exception as exc: raise ValueError('Invalid uploaded file encoding') from exc
        if not content: raise ValueError('Uploaded file is empty')
        if len(content) > 10 * 1024 * 1024: raise ValueError('Upload exceeds 10 MB')
        data=load(self.active_data_path(),{'faculty':[],'publications':[]})
        if kind=='roster':
            profiles=parse_faculty_roster(filename,content); existing={x['faculty_id']:x for x in data['faculty']}
            created=updated=0
            for profile in profiles:
                if profile['faculty_id'] in existing:
                    existing[profile['faculty_id']].update({k:v for k,v in profile.items() if k in ('name','department')}); updated+=1
                else: data['faculty'].append(profile); created+=1
            count=len(profiles); detail={'created':created,'updated':updated}
        else:
            if source not in {'scholar','scopus','wos'}: raise ValueError('Select Scholar, Scopus or WoS')
            faculty=next((x for x in data['faculty'] if x.get('faculty_id')==faculty_id),None)
            if not faculty: raise ValueError('Faculty ID was not found in the roster')
            if not faculty.get('consent',{}).get(source): raise PermissionError(f'{source} consent must be enabled in the faculty profile first')
            records=parse_publication_export(filename,content,source,faculty_id)
            for record in records:
                record['import_sha256']=hashlib.sha256(content).hexdigest()
                record['date_basis']='upload_date; original source retrieval date unavailable'
            if not records: raise ValueError('No publication records could be parsed')
            by_id={(x['faculty_id'],x['source'],x['source_id']):x for x in data['publications']}; created=updated=0
            for record in records:
                key=(record['faculty_id'],record['source'],record['source_id'])
                if key in by_id: by_id[key].update(record); updated+=1
                else: data['publications'].append(record); by_id[key]=record; created+=1
            count=len(records); detail={'created':created,'updated':updated,'faculty_id':faculty_id,'source':source}
        validate_dataset(data)
        dump(DEFAULT_RUNTIME/'source_data.json',data); events=load(DEFAULT_RUNTIME/'live_events.json',[]); events.append({'time':now(),'action':'file_import','source':source or 'roster','source_id':filename,'title':f'{count} records imported','citations':0}); dump(DEFAULT_RUNTIME/'live_events.json',events[-500:]); self.reload_connector()
        digest=Store(DEFAULT_RUNTIME).archive(filename,content)
        return {'status':'imported','filename':filename,'sha256':digest,'records':count,**detail}
    def report(self, run_id):
        path=DEFAULT_RUNTIME/'runs'/f'{re.sub(r"[^a-zA-Z0-9_-]","",run_id)}.json'; value=load(path)
        if not value: raise FileNotFoundError('Run not found')
        return value
    def export_report(self, scheme):
        report=load(DEFAULT_RUNTIME/'published'/'current.json')
        if not report or report.get('status')!='approved': raise PermissionError('An approved report is required before export')
        output=io.StringIO(); fields=['scheme','version','faculty_id','faculty_name','department','title','year','doi','citations','scholar','scopus','wos','retrieved_dates']
        writer=csv.DictWriter(output,fieldnames=fields); writer.writeheader()
        for result in report.get('faculty_results',[]):
            faculty=result['faculty']
            for publication in result.get('publications',[]):
                sources=set(publication.get('verified_sources',[])); dates=sorted({e.get('retrieved','') for e in publication.get('evidence',[])})
                row={'scheme':scheme.upper(),'version':report['version'],'faculty_id':faculty['faculty_id'],'faculty_name':faculty['name'],'department':faculty['department'],'title':publication['title'],'year':publication['year'],'doi':publication.get('doi',''),'citations':publication['citations'],'scholar':'yes' if 'scholar' in sources else 'no','scopus':'yes' if 'scopus' in sources else 'no','wos':'yes' if 'wos' in sources else 'no','retrieved_dates':';'.join(dates)}
                writer.writerow({k:("'"+v if isinstance(v,str) and (v.lstrip().startswith(('=','+','-','@')) or v.startswith(('\t','\r','\n'))) else v) for k,v in row.items()})
        return output.getvalue().encode('utf-8-sig')
    def live_snapshot(self):
        data=load(self.active_data_path(),{'faculty':[],'publications':[]}); pubs=data.get('publications',[]); merged,_=deduplicate(pubs); verified=[p for p in merged if p.get('verified')]
        sources={s:{'records':sum(p.get('source')==s for p in pubs),'last_retrieved':max((p.get('retrieved','') for p in pubs if p.get('source')==s),default=None)} for s in ('scholar','scopus','wos')}
        events=load(DEFAULT_RUNTIME/'live_events.json',[])
        return {'updated_at':now(),'faculty':len(data.get('faculty',[])),'raw_records':len(pubs),'deduplicated_publications':len(merged),'verified_publications':len(verified),'total_citations':sum(int(p.get('citations',0)) for p in verified),'h_index':compute_h_index(p.get('citations',0) for p in verified),'sources':sources,'recent_events':events[-10:][::-1]}
    def ingest_live_record(self,record):
        required=('source_id','faculty_id','source','title','year','citations','url','retrieved')
        if not isinstance(record,dict) or not all(k in record for k in required): raise ValueError('Live record is missing required provenance fields')
        if record['source'] not in {'scholar','scopus','wos'}: raise ValueError('Only scholar, scopus and wos records are accepted')
        data=load(self.active_data_path(),{'faculty':[],'publications':[]}); faculty=next((f for f in data.get('faculty',[]) if f.get('faculty_id')==record['faculty_id']),None)
        if not faculty: raise ValueError('Faculty profile must exist before publication ingestion')
        if not faculty.get('consent',{}).get(record['source']): raise PermissionError('Faculty consent is missing for this source')
        pubs=data.setdefault('publications',[]); old=next((p for p in pubs if (p.get('faculty_id'),p.get('source'),p.get('source_id'))==(record['faculty_id'],record['source'],record['source_id'])),None); action='updated' if old else 'created'
        if old: old.update(record)
        else: pubs.append(record)
        validate_dataset(data)
        dump(DEFAULT_RUNTIME/'source_data.json',data); events=load(DEFAULT_RUNTIME/'live_events.json',[]); events.append({'time':now(),'action':action,'source':record['source'],'source_id':record['source_id'],'title':record['title'],'citations':record['citations']}); dump(DEFAULT_RUNTIME/'live_events.json',events[-500:]); self.reload_connector()
        return {'status':action,'snapshot':self.live_snapshot()}

SERVICE=DashboardService(use_groq=True)
class Handler(BaseHTTPRequestHandler):
    def body(self):
        size=int(self.headers.get('Content-Length',0))
        if not 0 <= size <= 15 * 1024 * 1024: raise ValueError('Request too large')
        previous=self.connection.gettimeout()
        self.connection.settimeout(10)
        try:
            raw=self.rfile.read(size)
            if len(raw)!=size:raise ValueError('Incomplete request body')
            body=json.loads(raw or b'{}')
            if not isinstance(body,dict):raise ValueError('Request body must be a JSON object')
            return body
        finally:self.connection.settimeout(previous)
    def send_json(self,v,status=200):
        b=json.dumps(v,indent=2,ensure_ascii=False).encode(); self.send_response(status); self.send_header('Content-Type','application/json; charset=utf-8'); self.send_header('Content-Length',str(len(b))); self.end_headers(); self.wfile.write(b)
    def send_file(self,p,typ):
        b=p.read_bytes(); self.send_response(200); self.send_header('Content-Type',typ); self.send_header('Content-Length',str(len(b))); self.end_headers(); self.wfile.write(b)
    def send_download(self,body,name):
        self.send_response(200); self.send_header('Content-Type','text/csv; charset=utf-8'); self.send_header('Content-Disposition',f'attachment; filename="{name}"'); self.send_header('Content-Length',str(len(body))); self.end_headers(); self.wfile.write(body)
    def do_POST(self):
        self.post_request()
    def log_message(self,*args): pass
def serve(port=8000):
    from .role_web import RoleHandler
    with single_server(DEFAULT_RUNTIME):
        Store(DEFAULT_RUNTIME).migrate()
        from .api_secrets import restore_gemini_key
        restore_gemini_key(DEFAULT_RUNTIME)
        print(f'Standalone dashboard: http://127.0.0.1:{port}',flush=True)
        ThreadingHTTPServer(('127.0.0.1',port),RoleHandler).serve_forever()
