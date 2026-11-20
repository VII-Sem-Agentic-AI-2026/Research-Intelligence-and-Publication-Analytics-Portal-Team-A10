"""Exercise the actual password portal and its object-level boundaries over HTTP."""
import base64
import http.client
import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
from http.server import ThreadingHTTPServer

from publication_agent import web
from publication_agent.accounts import Accounts
from publication_agent.role_web import RoleHandler

PASSWORD='Test-only password 42!'


class AccountsRolesTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)/'runtime'
        self.root_patch=patch('publication_agent.web.DEFAULT_RUNTIME',self.root);self.root_patch.start()
        self.service=web.DashboardService()
        self.service_patch=patch('publication_agent.web.SERVICE',self.service);self.service_patch.start()
        self.accounts=Accounts(self.root)
        self.accounts.create({'username':'admin','password':PASSWORD,'name':'Administrator','role':'admin'},bootstrap=True)
        admin=self.accounts.users()[0]
        for username,role,faculty,department in [('asha','faculty','F001','CSE'),('vikram','faculty','F002','CSE'),('dean','dean',None,''),('cse-head','hod',None,'CSE'),('ece-head','hod',None,'ECE')]:
            self.accounts.create({'username':username,'password':PASSWORD,'name':username,'role':role,'faculty_id':faculty,'department':department},admin)
        self.server=ThreadingHTTPServer(('127.0.0.1',0),RoleHandler)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()

    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join()
        self.service_patch.stop();self.root_patch.stop();self.temp.cleanup()

    def request(self,path,body=None,cookie=None):
        client=http.client.HTTPConnection('127.0.0.1',self.server.server_port,timeout=10)
        headers={'Content-Type':'application/json'}
        if cookie:headers['Cookie']=cookie
        client.request('GET' if body is None else 'POST',path,None if body is None else json.dumps(body),headers)
        response=client.getresponse();raw=response.read();session=response.getheader('Set-Cookie');status=response.status;client.close()
        try:value=json.loads(raw)
        except ValueError:value={}
        return status,value,session.split(';')[0] if session else None

    def login(self,name):
        status,_,cookie=self.request('/api/login',{'username':name,'password':PASSWORD})
        self.assertEqual(status,200);return cookie

    def test_passwords_and_sessions_are_hashed_and_logout_revokes(self):
        cookie=self.login('asha')
        with self.accounts.store.connect() as db:
            row=db.execute("SELECT password_hash,salt FROM users WHERE username='asha'").fetchone()
            self.assertNotIn(PASSWORD,str(row));self.assertEqual(len(row[0]),64)
            session=db.execute('SELECT digest FROM sessions').fetchone()[0]
            self.assertNotIn(cookie.split('=')[1],session)
        self.assertEqual(self.request('/api/logout',{},cookie)[0],200)
        self.assertEqual(self.request('/api/me',cookie=cookie)[0],401)

    def test_first_login_department_is_saved_and_cannot_target_another_profile(self):
        cookie=self.login('asha')
        status,me,_=self.request('/api/me',cookie=cookie)
        self.assertEqual(status,200);self.assertFalse(me['department_confirmed'])
        status,result,_=self.request('/api/onboarding',{'department':'ECE','faculty_id':'F002'},cookie)
        self.assertEqual(status,200);self.assertTrue(result['saved'])
        _,me,_=self.request('/api/me',cookie=cookie)
        self.assertTrue(me['department_confirmed']);self.assertEqual(me['department'],'ECE')
        profiles={f['faculty_id']:f for f in self.service.faculty_profiles()}
        self.assertEqual(profiles['F001']['department'],'ECE')
        self.assertEqual(profiles['F002']['department'],'CSE')
        self.assertEqual(self.request('/api/onboarding',{'department':'CSE'},cookie)[0],400)

    def test_faculty_sees_only_own_data_and_cannot_access_admin(self):
        cookie=self.login('asha');status,data,_=self.request('/api/workspace',cookie=cookie)
        self.assertEqual(status,200)
        self.assertEqual({f['faculty_id'] for f in data['faculty']},{'F001'})
        _,page,_=self.request('/api/publications',cookie=cookie)
        self.assertTrue(page['records'])
        self.assertTrue(all(p['faculty_id']=='F001' for p in page['records']))
        self.assertEqual(self.request('/api/users',cookie=cookie)[0],403)
        self.assertEqual(self.request('/api/approve',{'run_id':'anything','role':'Research Dean'},cookie)[0],403)
        self.assertEqual(self.request('/api/import',{'data':{}},cookie)[0],403)

    def test_faculty_cannot_upload_or_edit_another_faculty(self):
        cookie=self.login('asha')
        body={'faculty_id':'F002','kind':'publication','filename':'x.csv','content_base64':base64.b64encode(b'x').decode(),'source':'scholar'}
        self.assertEqual(self.request('/api/upload',body,cookie)[0],403)
        self.assertEqual(self.request('/api/faculty',{'profile':{'faculty_id':'F002'}},cookie)[0],403)
        self.assertEqual(self.request('/api/upload',body|{'faculty_id':'F001','kind':'roster'},cookie)[0],403)

    def test_admin_cannot_approve_and_dean_cannot_manage_accounts(self):
        admin=self.login('admin');dean=self.login('dean')
        self.assertEqual(self.request('/api/approve',{'run_id':'r'},admin)[0],403)
        self.assertEqual(self.request('/api/users',cookie=dean)[0],403)
        self.assertEqual(self.request('/api/users',{'username':'bad','password':PASSWORD,'name':'bad','role':'admin'},dean)[0],403)

    def test_hod_cannot_read_or_review_another_department(self):
        ctx=self.service.app.run('2026 CSE bibliometric')
        cookie=self.login('ece-head')
        status,data,_=self.request('/api/workspace',cookie=cookie)
        self.assertEqual(status,200);self.assertEqual(data['faculty'],[]);self.assertEqual(data['runs'],[])
        self.assertEqual(self.request('/api/approve',{'run_id':ctx.run_id},cookie)[0],403)

    def test_dean_approval_uses_account_identity_and_role(self):
        from tests.review_helpers import review_all
        ctx=self.service.app.run('2026 CSE bibliometric');review_all(self.service.app,ctx)
        status,data,_=self.request('/api/approve',{'run_id':ctx.run_id,'reviewer':'spoof','role':'admin'},self.login('dean'))
        self.assertEqual(status,200);self.assertEqual(data['approved_by'],'dean');self.assertEqual(data['approver_role'],'Research Dean')

    def test_faculty_report_excludes_other_faculty_and_source_snapshot(self):
        self.service.app.run('2026 CSE bibliometric')
        _,data,_=self.request('/api/workspace',cookie=self.login('asha'))
        self.assertTrue(data['runs'])
        for run in data['runs']:
            _,run,_=self.request('/api/report?run_id='+run['run_id'],cookie=self.login('asha'))
            self.assertNotIn('source_snapshot',run);self.assertNotIn('artifacts',run)
            self.assertEqual({r['faculty']['faculty_id'] for r in run['report']['faculty_results']},{'F001'})
            self.assertNotIn('groq_explanation',run['report'])

    def test_setup_is_closed_after_first_admin_and_token_login_is_rejected(self):
        self.assertFalse(self.request('/api/setup-status')[1]['needs_setup'])
        self.assertEqual(self.request('/api/setup',{'username':'other','password':PASSWORD,'name':'Other'})[0],403)
        self.assertEqual(self.request('/api/login',{'token':'old-shared-token'})[0],401)

    def test_account_disable_revokes_existing_sessions(self):
        cookie=self.login('asha');admin=self.login('admin')
        user=next(u for u in self.accounts.users() if u['username']=='asha')
        self.assertEqual(self.request('/api/users/disable',{'user_id':user['id']},admin)[0],200)
        self.assertEqual(self.request('/api/workspace',cookie=cookie)[0],401)

    def test_password_change_revokes_session_and_old_password(self):
        cookie=self.login('asha')
        self.assertEqual(self.request('/api/password',{'current_password':PASSWORD,'new_password':'A new test password 777!'},cookie)[0],200)
        self.assertEqual(self.request('/api/me',cookie=cookie)[0],401)
        self.assertEqual(self.request('/api/login',{'username':'asha','password':PASSWORD})[0],401)
        self.assertEqual(self.request('/api/login',{'username':'asha','password':'A new test password 777!'})[0],200)

    def test_chat_endpoint_uses_model_tools_and_private_history(self):
        from tests.test_assistant import ScriptedModel
        model=ScriptedModel('publications')
        with patch.dict('os.environ',{'GEMINI_API_KEY':'test-only-not-a-real-key'}),patch('publication_agent.assistant.ChatGoogleGenerativeAI',return_value=model):
            status,result,_=self.request('/api/assistant/chat',{'message':'Show my publications','role':'dean'},self.login('asha'))
        self.assertEqual(status,200);self.assertIn('reply',result);self.assertEqual(len(model.calls),2)
        cookie=self.login('vikram');status,result,_=self.request('/api/assistant/history',cookie=cookie)
        self.assertEqual(status,200);self.assertEqual(result['history'],[])

    def test_only_admin_can_configure_ai_and_key_is_not_returned(self):
        with patch.dict('os.environ',{'GEMINI_API_KEY':''}):
            body={'api_key':'test-key-should-never-be-returned'}
            self.assertEqual(self.request('/api/ai-key',body,self.login('asha'))[0],403)
            status,result,_=self.request('/api/ai-key',body,self.login('admin'))
            self.assertEqual(status,200);self.assertNotIn(body['api_key'],str(result))

    def test_chat_rate_limit_returns_safe_http_429(self):
        from tests.test_assistant import ScriptedModel
        class Limited(ScriptedModel):
            def invoke(self,messages):raise RuntimeError('Error code: 429 org_SYNTHETIC_PRIVATE billing https://example.invalid')
        with patch.dict('os.environ',{'GEMINI_API_KEY':'test-only-not-a-real-key'}),patch('publication_agent.assistant.ChatGoogleGenerativeAI',return_value=Limited()):
            status,result,_=self.request('/api/assistant/chat',{'message':'Show my publications'},self.login('asha'))
        self.assertEqual(status,429);self.assertGreater(result['retry_after'],0)
        self.assertNotIn('org_SYNTHETIC_PRIVATE',str(result));self.assertNotIn('billing',str(result))

    def test_faculty_can_withdraw_all_consent_through_http(self):
        cookie=self.login('asha');_,data,_=self.request('/api/workspace',cookie=cookie)
        profile=data['faculty'][0];profile['consent']={s:False for s in ('scholar','scopus','wos')}
        self.assertEqual(self.request('/api/faculty',{'profile':profile},cookie)[0],200)
        _,data,_=self.request('/api/workspace',cookie=cookie)
        self.assertFalse(any(data['faculty'][0]['consent'].values()))

    def test_missing_consent_upload_keeps_session_active(self):
        cookie=self.login('asha')
        self.assertEqual(self.request('/api/onboarding',{'department':'CSE'},cookie)[0],200)
        profile=next(f for f in self.service.faculty_profiles() if f['faculty_id']=='F001')
        profile['consent']['scopus']=False
        self.service.save_faculty(profile)
        encoded=base64.b64encode(b'Title,Year,Cited by\nSynthetic paper,2025,1\n').decode()
        status,result,_=self.request('/api/upload',{'kind':'publication','source':'scopus','faculty_id':'F001','filename':'x.csv','content_base64':encoded},cookie)
        self.assertEqual(status,403)
        self.assertIn('consent',result['error'])
        self.assertEqual(self.request('/api/workspace',cookie=cookie)[0],200)

    def test_unknown_citation_upload_is_rejected_atomically(self):
        cookie=self.login('asha');_,before,_=self.request('/api/workspace',cookie=cookie)
        self.assertEqual(self.request('/api/onboarding',{'department':'CSE'},cookie)[0],200)
        data=base64.b64encode(b'Title,Year,Cited by\nSynthetic unknown count,2025,unknown\n').decode()
        status,result,_=self.request('/api/upload',{'kind':'publication','source':'scopus','faculty_id':'F001','filename':'x.csv','content_base64':data},cookie)
        self.assertEqual(status,400);self.assertIn('unknown counts',result['error'])
        _,after,_=self.request('/api/workspace',cookie=cookie)
        self.assertEqual(before['publications'],after['publications'])


if __name__=='__main__':unittest.main()
