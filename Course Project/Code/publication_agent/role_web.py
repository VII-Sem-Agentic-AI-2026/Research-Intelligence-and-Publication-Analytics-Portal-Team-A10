"""Role-specific API; faculty isolation is enforced here, not just in the UI."""
import copy
import json
import uuid
from urllib.parse import urlparse,parse_qs
from . import web as W
from .accounts import Accounts, AuthenticationError, Forbidden, require, ROLE_LABELS, PERMISSIONS
from .core import load, now
from .actions import Actions
from .assistant_errors import AssistantServiceError, provider_error


def allowed_department(identity,department):
    return identity['role']!='hod' or identity['department']==str(department).upper()


def visible_run(run,identity):
    if identity['role']=='hod' and not allowed_department(identity,run.get('plan',{}).get('department')):return None
    report=copy.deepcopy(run.get('report',{}))
    if identity['role']=='faculty':
        results=[r for r in report.get('faculty_results',[]) if r['faculty']['faculty_id']==identity['faculty_id']]
        if not results:return None
        # Do not expose institutional narrative, totals, or another faculty's work.
        report={k:report[k] for k in ('title','status','approved_by','approved_at','version','citation_basis','scope') if k in report}
        report['faculty_results']=results
        pubs={p['publication_id']:p for r in results for p in r.get('publications',[])}
        report['summary']={'faculty':1,'publications':len(pubs),'citations':sum(p['citations'] for p in pubs.values() if p.get('verified'))}
    from .report_insights import report_insights
    report['insights']=report_insights({**report,'plan':run.get('plan',{})})
    return {k:copy.deepcopy(run.get(k)) for k in ('run_id','status','plan','validation','created_at')}|{'report':report}|({'review_assignment':copy.deepcopy(run.get('review_assignment',{}))} if identity['role']!='faculty' else {})


class RoleHandler(W.Handler):
    @property
    def accounts(self):return Accounts(W.DEFAULT_RUNTIME)

    def cookie_json(self,value,token=None):
        payload=json.dumps(value).encode()
        self.send_response(200);self.send_header('Content-Type','application/json')
        self.send_header('Cache-Control','no-store')
        from .tunnel_access import secure_cookie
        secure='; Secure' if secure_cookie(self.headers,W.DEFAULT_RUNTIME) else ''
        self.send_header('Set-Cookie',f'portal_session={token or ""}; HttpOnly; SameSite=Strict; Path=/; Max-Age={3600 if token else 0}{secure}')
        self.send_header('Content-Length',str(len(payload)));self.end_headers();self.wfile.write(payload)

    def send_json(self,value,status=200):
        payload=json.dumps(value,ensure_ascii=False).encode()
        self.send_response(status);self.send_header('Content-Type','application/json; charset=utf-8')
        self.send_header('Cache-Control','no-store');self.send_header('Content-Length',str(len(payload)))
        self.end_headers();self.wfile.write(payload)

    def checked_run(self,run_id,identity):
        run=W.SERVICE.report(run_id)
        if not allowed_department(identity,run.get('plan',{}).get('department')):raise Forbidden('Report belongs to another department')
        return run

    def get_request(self):
        path=urlparse(self.path).path
        static={'/':'portal.html','/portal.js':'portal.js','/portal.css':'portal.css','/assistant-widget.js':'assistant-widget.js','/chat-format.js':'chat-format.js'}
        if path in static:
            types={'.html':'text/html','.js':'text/javascript','.css':'text/css'}
            filename=W.ROOT/'dashboard'/static[path]
            return self.send_file(filename,types[filename.suffix]+'; charset=utf-8')
        if path=='/api/setup-status':return self.send_json({'needs_setup':self.accounts.needs_setup()})
        if path=='/api/health':
            import hashlib
            return self.send_json({'service':'research-portal','tunnel_support':True,'instance':hashlib.sha256(str(W.ROOT.resolve()).encode()).hexdigest()[:16]})
        user=self.accounts.principal(self.headers)
        if path=='/api/me':return self.send_json(user|{'permissions':sorted(PERMISSIONS[user['role']])})
        if path=='/api/users':
            require(user,'accounts');return self.send_json(self.accounts.users())
        if path=='/api/workspace':
            return self.send_json(Actions(user,W.SERVICE,W.DEFAULT_RUNTIME,self.accounts).workspace(compact=True))
        if path in {'/api/publications','/api/reports','/api/report'}:
            actions=Actions(user,W.SERVICE,W.DEFAULT_RUNTIME,self.accounts)
            query={k:v[0] for k,v in parse_qs(urlparse(self.path).query).items()}
            if path=='/api/publications':
                return self.send_json(actions.publications_page(query.get('page',1),query.get('page_size',50),query.get('query',''),query.get('year')))
            if path=='/api/reports':
                return self.send_json(actions.reports_page(query.get('page',1),query.get('page_size',10)))
            run=visible_run(actions.checked_run(query.get('run_id')),user)
            if run is None:raise Forbidden('This report is not in your workspace')
            return self.send_json({**run,'detail_loaded':True})
        if path=='/api/assistant/history':
            from .assistant import safe_history
            return self.send_json({'history':safe_history(load(W.DEFAULT_RUNTIME/'assistant'/f'user-{user["id"]}.json',[]))})
        if path.startswith('/api/export/'):
            require(user,'read')
            current=load(W.DEFAULT_RUNTIME/'published'/'current.json',{}) or {}
            if not allowed_department(user,current.get('plan',{}).get('department')):raise Forbidden('Published report belongs to another department')
            scheme=path.rsplit('/',1)[-1].split('.')[0]
            if scheme not in {'nirf','naac'}:raise ValueError('Unknown export')
            return self.send_download(W.SERVICE.export_report(scheme),'research_'+scheme+'.csv')
        self.send_error(404)

    def post_request(self):
        path=urlparse(self.path).path
        try:
            from .tunnel_access import validate_request
            validate_request(self.headers,W.DEFAULT_RUNTIME)
            body=self.body()
            if path=='/api/setup':
                self.accounts.create(body|{'role':'admin'},bootstrap=True)
                token=self.accounts.login(body['username'],body['password'],self.client_address[0])
                return self.cookie_json({'authenticated':True},token)
            if path=='/api/login':
                token=self.accounts.login(body.get('username',''),body.get('password',''),self.client_address[0])
                return self.cookie_json({'authenticated':True},token)
            user=self.accounts.principal(self.headers)
            if path=='/api/logout':
                self.accounts.logout(self.headers);return self.cookie_json({'authenticated':False})
            if path=='/api/password':
                self.accounts.change_password(user,body.get('current_password'),body.get('new_password'))
                return self.cookie_json({'changed':True})
            if path=='/api/onboarding':
                return self.send_json(Actions(user,W.SERVICE,W.DEFAULT_RUNTIME,self.accounts).execute(path,body))
            if path=='/api/assistant/chat':
                from .assistant import Assistant
                from .storage import locked
                with locked(W.DEFAULT_RUNTIME/'operations'/str(user['id'])):
                    return self.send_json(Assistant(Actions(user,W.SERVICE,W.DEFAULT_RUNTIME,self.accounts)).chat(body.get('message','')))
            if path=='/api/assistant/confirm':
                from .assistant import confirm
                return self.send_json(confirm(Actions(user,W.SERVICE,W.DEFAULT_RUNTIME,self.accounts),body.get('pending_id','')))
            if path in {'/api/users','/api/users/disable','/api/users/designation','/api/ai-key','/api/ai-disable','/api/faculty','/api/upload','/api/personal-report','/api/chat','/api/approve','/api/review-duplicate','/api/review-attribution','/api/resume','/api/rollback','/api/import','/api/consent/request','/api/consent/batch','/api/consent/respond','/api/review/request','/api/review/respond'}:
                return self.send_json(Actions(user,W.SERVICE,W.DEFAULT_RUNTIME,self.accounts).execute(path,body))
            if path in {'/api/users/delete','/api/reports/delete'}:
                return self.send_json(Actions(user,W.SERVICE,W.DEFAULT_RUNTIME,self.accounts).execute(path,body))
            self.send_error(404)
        except AssistantServiceError as e:self.send_json({'error':str(e),'retry_after':e.retry_after},e.status_code)
        except Forbidden as e:self.send_json({'error':str(e)},403)
        except AuthenticationError as e:self.send_json({'error':str(e)},401)
        except PermissionError as e:self.send_json({'error':str(e)},403)
        except Exception as e:
            safe=provider_error(e)
            self.send_json({'error':str(safe or e),'retry_after':safe.retry_after if safe else None},safe.status_code if safe else 400)

    def do_GET(self):
        try:
            self.get_request()
        except Forbidden as e:self.send_json({'error':str(e)},403)
        except AuthenticationError as e:self.send_json({'error':str(e)},401)
        except PermissionError as e:self.send_json({'error':str(e)},403)
        except Exception as e:self.send_json({'error':str(e)},400)
