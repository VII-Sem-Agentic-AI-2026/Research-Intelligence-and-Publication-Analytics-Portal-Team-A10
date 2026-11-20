"""One authorization gateway shared by dashboard buttons and LLM tools."""
import os
from dataclasses import asdict
from .accounts import require, Forbidden, ROLE_LABELS, PERMISSIONS
from .core import PublicationOrchestrator, load


class Actions:
    def __init__(self,user,service,root,accounts):
        self.user,self.service,self.root,self.accounts=user,service,root,accounts

    def workspace(self,compact=False):
        from . import web as W
        from .role_web import allowed_department, visible_run
        user=self.user
        data=load(self.service.active_data_path(),{'faculty':[],'publications':[]})
        faculty=[f for f in data['faculty'] if (user['role']!='faculty' or f['faculty_id']==user['faculty_id']) and allowed_department(user,f['department'])]
        ids={f['faculty_id'] for f in faculty}
        from .human_workflow import HumanWorkflow
        workflow=HumanWorkflow(self).inbox()
        publications=[p for p in data['publications']+data.get('pending_publications',[]) if p['faculty_id'] in ids]
        runs=[v for r in W.all_runs() if (v:=visible_run(r,user)) is not None]
        active_deans={u['id'] for u in self.accounts.users() if u['role']=='dean' and u['active']}
        for run in runs:
            if run.get('review_assignment'):
                run['review_assignment']['reviewer_active']=run['review_assignment'].get('dean_id') in active_deans
        counts={'publications':len(publications),'distinct_publications':len({p.get('doi') or (p['title'],p['year']) for p in publications}),'reports':len(runs)}
        counts.update(report_eligible=sum(p.get('record_status')!='pending_review' for p in publications),needs_review=sum(p.get('record_status')=='pending_review' for p in publications))
        return {'user':user,'permissions':sorted(PERMISSIONS[user['role']]),'faculty':faculty,
                'publications':[] if compact else publications,
                'runs':[self.run_summary(r) for r in runs[:10]] if compact else runs,
                'counts':counts,
                'departments':sorted({str(f.get('department','')).strip().upper() for f in data['faculty'] if f.get('department')} | {'CSE','ECE','EEE','ME','CE','IT','AI','DS'}),
                'groq_configured':bool(os.getenv('GEMINI_API_KEY')),
                **workflow,'reviewers':[{'id':u['id'],'name':u['name']} for u in self.accounts.users() if u['role']=='dean' and u['active']] if 'request_dean_review' in PERMISSIONS[user['role']] else []}

    @staticmethod
    def run_summary(run):
        return {**run,'report':{k:v for k,v in run.get('report',{}).items() if k in {'title','summary','version','status'}},'detail_loaded':False}

    def publications_page(self,page=1,page_size=50,query='',year=None):
        from .role_web import allowed_department
        page=int(page);page_size=int(page_size)
        if page<1 or not 1<=page_size<=100:raise ValueError('Invalid page or page size')
        data=load(self.service.active_data_path(),{'faculty':[],'publications':[]})
        ids={f['faculty_id'] for f in data['faculty'] if (self.user['role']!='faculty' or f['faculty_id']==self.user['faculty_id']) and allowed_department(self.user,f['department'])}
        rows=[p for p in data['publications']+data.get('pending_publications',[]) if p['faculty_id'] in ids and (not year or p['year']==int(year)) and str(query).casefold() in p['title'].casefold()]
        start=(page-1)*page_size
        fields={'faculty_id','title','year','source','citations','doi','source_id','record_status','review_reasons','citation_count_origin'}
        return {'records':[{k:v for k,v in p.items() if k in fields} for p in rows[start:start+page_size]],'total':len(rows),'page':page,'page_size':page_size}

    def reports_page(self,page=1,page_size=10):
        from . import web as W
        from .role_web import visible_run
        page=int(page);page_size=int(page_size)
        if page<1 or not 1<=page_size<=20:raise ValueError('Invalid page or page size')
        rows=[v for r in W.all_runs() if (v:=visible_run(r,self.user)) is not None]
        start=(page-1)*page_size
        return {'records':[self.run_summary(r) for r in rows[start:start+page_size]],'total':len(rows),'page':page,'page_size':page_size}

    def checked_run(self,run_id):
        from .role_web import allowed_department
        if not isinstance(run_id,str) or not __import__('re').fullmatch(r'[a-zA-Z0-9_-]+',run_id):raise ValueError('Invalid report ID')
        run=self.service.report(run_id)
        if not allowed_department(self.user,run.get('plan',{}).get('department')):raise Forbidden('Report belongs to another department')
        return run

    def execute(self,path,body):
        from . import web as W
        from .storage import locked
        # Model/report work has its own orchestrator and never holds the mutation lock.
        if path in {'/api/chat','/api/personal-report','/api/resume'}:
            import copy
            with locked(self.root/'operations'/str(self.user['id'])):
                current=next((u for u in self.accounts.users() if u['id']==self.user['id'] and u['active']),None)
                if not current:raise Forbidden('This account is no longer active')
                service=copy.copy(self.service)
                service.reload_connector()
                return Actions(self.user,service,self.root,self.accounts)._execute(path,body)
        if path=='/api/users/delete':
            with locked(self.root/'operations'/str(int(body['user_id']))):
                return self._mutate(path,body)
        return self._mutate(path,body)

    def _mutate(self,path,body):
        from . import web as W
        from .storage import locked
        with W.REQUEST_LOCK,locked(self.root):
            if self.accounts is not None:
                current=next((u for u in self.accounts.users() if u['id']==self.user['id'] and u['active']),None)
                if not current:raise Forbidden('This account is no longer active')
            return self._execute(path,body)

    def _execute(self,path,body):
        user=self.user;service=self.service
        if path=='/api/onboarding':
            return self.accounts.confirm_department(user,body.get('department'),service)
        workflow_routes={'/api/consent/request':'request_consent','/api/consent/respond':'respond_consent','/api/review/request':'request_review','/api/review/respond':'respond_review'}
        if path in workflow_routes:
            from .human_workflow import HumanWorkflow
            return getattr(HumanWorkflow(self),workflow_routes[path])(body)
        if path=='/api/users':
            require(user,'accounts')
            if body.get('role')=='faculty' and not any(f['faculty_id']==body.get('faculty_id') for f in service.faculty_profiles()):raise ValueError('Select an existing faculty profile')
            return self.accounts.create(body,user)
        if path=='/api/users/disable':
            require(user,'accounts');self.accounts.disable(int(body['user_id']),user);return {'disabled':True}
        if path=='/api/users/delete':
            require(user,'accounts')
            if body.get('confirm') is not True:raise ValueError('Explicit deletion confirmation is required')
            return self.accounts.delete(int(body['user_id']),user)
        if path=='/api/reports/delete':
            require(user,'delete_reports')
            if body.get('confirm') is not True:raise ValueError('Explicit deletion confirmation is required')
            from .administration import delete_report
            return delete_report(self,body)
        if path=='/api/ai-disable':
            require(user,'accounts')
            from .api_secrets import forget_gemini_key
            forget_gemini_key(self.root)
            os.environ.pop('GEMINI_API_KEY',None)
            return {'configured':False,'disabled':True,'message':'AI disabled. The saved key and in-memory key were removed; the Gemini account key was not revoked.'}
        if path=='/api/ai-key':
            require(user,'accounts')
            key=str(body.get('api_key','')).strip()
            if len(key)<20 or len(key)>512:raise ValueError('Enter a valid Gemini API key')
            from .api_secrets import save_gemini_key
            save_gemini_key(self.root,key)
            os.environ['GEMINI_API_KEY']=key
            return {'configured':True,'storage':'Windows account-encrypted local storage','remembered':True}
        if path=='/api/faculty':
            profile=body['profile']
            if user['role']=='faculty':
                require(user,'self_profile')
                if profile.get('faculty_id')!=user['faculty_id']:raise Forbidden('You can update only your own profile')
                existing=next(f for f in service.faculty_profiles() if f['faculty_id']==user['faculty_id'])
                profile=existing|{k:profile[k] for k in ('consent','profiles') if k in profile}
            else:
                require(user,'profile')
                old=next((f for f in service.faculty_profiles() if f['faculty_id']==profile.get('faculty_id')),None)
                for source in ('scholar','scopus','wos'):
                    proposed=profile.get('consent',{}).get(source,False)
                    if proposed and (not old or not old.get('consent',{}).get(source) or profile.get('profiles',{}).get(source)!=old.get('profiles',{}).get(source)):
                        raise Forbidden('Faculty approval is required to grant consent or change an approved source link. Research Office must send a consent request.')
            return service.save_faculty(profile)
        if path=='/api/upload':
            if user['role']=='faculty':
                require(user,'self_upload')
                if body.get('kind')!='publication' or body.get('faculty_id')!=user['faculty_id']:raise Forbidden('Upload publications only for your assigned faculty profile')
                if self.accounts is not None:
                    current=next((u for u in self.accounts.users() if u['id']==user['id']),{})
                    if not current.get('department_confirmed'):raise Forbidden('Select your department on first login before uploading publications')
            else:require(user,'import')
            return service.upload_export(body['filename'],body['content_base64'],body['kind'],body.get('source'),body.get('faculty_id'))
        if path=='/api/personal-report':
            require(user,'self_read')
            data=self.workspace();profile=next((f for f in data['faculty'] if f['faculty_id']==user['faculty_id']),None)
            if not profile:raise ValueError('Assigned faculty profile is unavailable')
            answers={'department':profile['department'],'reporting_year':int(body['year']),'metric_pack':body.get('metric_pack','bibliometric'),'scope':body.get('scope','cumulative_through_year')}
            app=PublicationOrchestrator(data_path=service.active_data_path(),runtime_root=self.root,use_groq=service.use_groq)
            app.connector.data={'faculty':[profile],'publications':[p for p in data['publications'] if p.get('record_status')!='pending_review']}
            return asdict(app.run('Personal publication report',answers,selected_labs=[14]))
        if path=='/api/chat':
            require(user,'run')
            from .role_web import allowed_department
            if user['role']=='hod':
                planned=service.app.make_plan(body.get('message',''))
                if not planned.get('complete') or not allowed_department(user,planned['plan']['department']):raise Forbidden('Enter a complete request for your assigned department')
            return service.chat('account-'+str(user['id']),body.get('message',''),body.get('selected_labs'),body.get('scope','cumulative_through_year'))
        required={'/api/approve':'publish','/api/review-duplicate':'review','/api/review-attribution':'review','/api/resume':'run'}
        if path in required:
            require(user,required[path]);run=self.checked_run(body['run_id']);app=service.app
            assignment=run.get('review_assignment',{})
            if path!='/api/resume' and assignment:
                if user['role']!='dean' or user['id']!=assignment.get('dean_id') or assignment.get('status')!='accepted':
                    raise Forbidden('Only the assigned Dean may review or publish this report after accepting the request')
            if path=='/api/approve':
                if assignment:return app.approve(body['run_id'],user['name'],ROLE_LABELS[user['role']],body.get('edits'),reviewer_id=user['id'])
                return app.approve(body['run_id'],user['name'],ROLE_LABELS[user['role']],body.get('edits'))
            if path=='/api/review-duplicate':return app.review_duplicate(body['run_id'],body['faculty_id'],body['group'],body['decision'],user['name'])
            if path=='/api/review-attribution':return app.review_attribution(body['run_id'],body['faculty_id'],body['note'],user['name'])
            return asdict(app.resume(body['run_id']))
        if path=='/api/rollback':
            require(user,'rollback');return service.app.rollback(int(body['version']))
        if path=='/api/import':
            require(user,'import')
            old={f['faculty_id']:f for f in service.faculty_profiles()}
            for profile in body.get('data',{}).get('faculty',[]):
                existing=old.get(profile.get('faculty_id'),{})
                for source in ('scholar','scopus','wos'):
                    if profile.get('consent',{}).get(source) and (not existing.get('consent',{}).get(source) or profile.get('profiles',{}).get(source)!=existing.get('profiles',{}).get(source)):
                        raise Forbidden('Bulk import cannot grant faculty consent; use the faculty approval workflow')
            return service.import_data(body['data'])
        raise ValueError('Unknown dashboard action')
