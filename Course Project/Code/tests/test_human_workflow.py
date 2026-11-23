"""Exercise consent and named-Dean assignments through authenticated HTTP."""
import unittest
from test_accounts_roles import AccountsRolesTests as Fixture, PASSWORD

class HumanWorkflowTests(unittest.TestCase):
    setUp=Fixture.setUp
    tearDown=Fixture.tearDown
    request=Fixture.request
    login=Fixture.login

    def officer(self):
        self.accounts.create({'username':'office','password':PASSWORD,'name':'Research Officer','role':'research_office'},self.accounts.users()[0])
        return self.login('office')

    def consent_request(self,office):
        status,result,_=self.request('/api/consent/request',{'faculty_id':'F001','sources':['scopus'],'message':'Please approve the annual research report.'},office)
        self.assertEqual(status,200,result)
        return result['request_id']

    def test_bulk_department_preview_and_send_through_authenticated_api(self):
        office=self.officer()
        for profile in self.service.faculty_profiles():
            if profile['department']=='CSE':
                profile['consent']['scopus']=False
                self.service.save_faculty(profile)
        body={'scope':'department','department':'CSE','sources':['scopus'],'message':'Annual department report consent request'}
        status,preview,_=self.request('/api/consent/batch',body,office)
        self.assertEqual(status,200,preview)
        self.assertGreater(preview['recipient_count'],0)
        self.assertEqual(self.request('/api/consent/batch',body,self.login('asha'))[0],403)
        status,sent,_=self.request('/api/consent/batch',{**body,'confirm':True,'preview_token':preview['preview_token']},office)
        self.assertEqual(status,200,sent)
        self.assertEqual(sent['sent'],preview['recipient_count'])
        _,workspace,_=self.request('/api/workspace',cookie=self.login('asha'))
        self.assertTrue(workspace['consent_requests'])
        self.assertTrue(all(r['faculty_id']=='F001' for r in workspace['consent_requests']))

    def test_faculty_approval_and_replay_protection(self):
        office=self.officer()
        profile=next(f for f in self.service.faculty_profiles() if f['faculty_id']=='F001')
        profile['consent']['scopus']=False
        self.service.save_faculty(profile)
        rid=self.consent_request(office)
        self.assertFalse(next(f for f in self.service.faculty_profiles() if f['faculty_id']=='F001')['consent']['scopus'])
        self.assertEqual(self.request('/api/consent/respond',{'request_id':rid,'decision':'approved'},office)[0],403)
        self.assertEqual(self.request('/api/consent/respond',{'request_id':rid,'decision':'approved'},self.login('vikram'))[0],403)
        faculty=self.login('asha')
        self.assertEqual(self.request('/api/consent/respond',{'request_id':rid,'decision':'approved'},faculty)[0],200)
        profile=next(f for f in self.service.faculty_profiles() if f['faculty_id']=='F001')
        self.assertTrue(profile['consent']['scopus'])
        self.assertIn(rid,profile['consent_approvals'])
        self.assertEqual(self.request('/api/consent/respond',{'request_id':rid,'decision':'approved'},faculty)[0],400)

    def test_decline_and_duplicate_request(self):
        office=self.officer();rid=self.consent_request(office)
        before=self.service.faculty_profiles()
        self.assertEqual(self.request('/api/consent/request',{'faculty_id':'F001','sources':['scopus'],'message':'Again'},office)[0],400)
        self.assertEqual(self.request('/api/consent/respond',{'request_id':rid,'decision':'declined'},self.login('asha'))[0],200)
        self.assertEqual(before,self.service.faculty_profiles())
        _,workspace,_=self.request('/api/workspace',cookie=self.login('vikram'))
        self.assertEqual(workspace['consent_requests'],[])

    def test_officer_cannot_grant_consent_directly(self):
        office=self.officer();profile=next(f for f in self.service.faculty_profiles() if f['faculty_id']=='F001')
        profile['consent']['scopus']=False
        self.assertEqual(self.request('/api/faculty',{'profile':profile},office)[0],200)
        profile['consent']['scopus']=True
        self.assertEqual(self.request('/api/faculty',{'profile':profile},office)[0],403)
        self.assertEqual(self.request('/api/faculty',{'profile':profile},self.login('admin'))[0],403)

    def test_assigned_dean_must_accept_and_other_reviewers_blocked(self):
        office=self.officer();ctx=self.service.app.run('2026 CSE bibliometric')
        dean=next(u for u in self.accounts.users() if u['role']=='dean')
        status,result,_=self.request('/api/review/request',{'run_id':ctx.run_id,'dean_id':dean['id'],'message':'Please independently review this draft.'},office)
        self.assertEqual(status,200,result)
        body={'run_id':ctx.run_id,'faculty_id':'F001','note':'Checked the source author identity and affiliation.'}
        self.assertEqual(self.request('/api/review-attribution',body,self.login('dean'))[0],403)
        self.assertEqual(self.request('/api/review/respond',{'request_id':result['request_id'],'decision':'accepted'},office)[0],403)
        self.assertEqual(self.request('/api/review/respond',{'request_id':result['request_id'],'decision':'accepted'},self.login('dean'))[0],200)
        self.assertEqual(self.request('/api/review-attribution',body,self.login('cse-head'))[0],403)
        self.assertEqual(self.request('/api/review-attribution',body,self.login('dean'))[0],200)
        reloaded=self.service.app.runtime.load_run(ctx.run_id)
        self.assertEqual(reloaded.review_assignment['status'],'accepted')
