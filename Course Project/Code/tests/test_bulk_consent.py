import copy
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from publication_agent.accounts import Accounts, Forbidden
from publication_agent.core import dump, load
from publication_agent.human_workflow import HumanWorkflow


class BulkConsentTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.hash_patch=patch.object(Accounts,'hash',return_value='fixture-hash');self.hash_patch.start()
        self.accounts=Accounts(self.root)
        self.accounts.create({'username':'admin','name':'Admin','role':'admin','password':'fixture-password'},bootstrap=True)
        admin=self.accounts.users()[0]
        self.accounts.create({'username':'office','name':'Office','role':'research_office','password':'fixture-password'},admin)
        self.profiles=[{'faculty_id':f'F{i}','name':f'Faculty {i}','department':'CSE' if i<3 else 'ECE',
            'consent':{'scopus':False},'profiles':{'scopus':f'https://example.test/author/{i}'}} for i in range(1,4)]
        for profile in self.profiles:
            self.accounts.create({'username':'u'+profile['faculty_id'].lower(),'name':profile['name'],'role':'faculty',
                'faculty_id':profile['faculty_id'],'password':'fixture-password'},admin)
        self.path=self.root/'source_data.json'
        dump(self.path,{'faculty':self.profiles,'publications':[]})
        self.service=SimpleNamespace(active_data_path=lambda:self.path,faculty_profiles=lambda:load(self.path)['faculty'],reload_connector=lambda:None)
        self.users={u['username'].removeprefix('u'):u for u in self.accounts.users()}
        self.workflow=self.for_user('office')
        self.body={'scope':'department','department':'CSE','sources':['scopus'],'message':'Please approve data access for annual reporting.'}

    def tearDown(self):
        self.hash_patch.stop();self.temp.cleanup()

    def for_user(self,name):
        return HumanWorkflow(SimpleNamespace(user=self.users[name],accounts=self.accounts,service=self.service))

    def send(self,body=None):
        body=body or self.body;preview=self.workflow.request_consent_batch(body)
        return self.workflow.request_consent_batch({**body,'confirm':True,'preview_token':preview['preview_token']})

    def test_department_preview_does_not_send_or_grant_consent(self):
        before=copy.deepcopy(load(self.path))
        preview=self.workflow.request_consent_batch(self.body)
        self.assertEqual(preview['recipient_count'],2)
        self.assertEqual({r['faculty_id'] for r in preview['recipients']},{'F1','F2'})
        self.assertEqual(self.workflow.inbox()['consent_requests'],[])
        self.assertEqual(load(self.path),before)

    def test_institution_request_reaches_all_departments(self):
        sent=self.send({**self.body,'scope':'institution'})
        self.assertEqual(sent['sent'],3)
        self.assertEqual(len(self.workflow.inbox()['consent_requests']),3)

    def test_each_faculty_decides_independently_and_cannot_approve_for_others(self):
        self.send()
        one=self.for_user('f1');two=self.for_user('f2')
        request=one.inbox()['consent_requests'][0]
        self.assertEqual(len(one.inbox()['consent_requests']),1)
        with self.assertRaises(Forbidden):two.respond_consent({'request_id':request['id'],'decision':'approved'})
        one.respond_consent({'request_id':request['id'],'decision':'approved'})
        profiles={f['faculty_id']:f for f in load(self.path)['faculty']}
        self.assertTrue(profiles['F1']['consent']['scopus'])
        self.assertFalse(profiles['F2']['consent']['scopus'])
        self.assertEqual(two.inbox()['consent_requests'][0]['status'],'pending')

    def test_retry_does_not_duplicate_pending_requests(self):
        preview=self.workflow.request_consent_batch(self.body)
        self.workflow.request_consent_batch({**self.body,'confirm':True,'preview_token':preview['preview_token']})
        with self.assertRaisesRegex(ValueError,'Preview'):
            self.workflow.request_consent_batch({**self.body,'confirm':True,'preview_token':preview['preview_token']})
        self.assertEqual(len(self.workflow.inbox()['consent_requests']),2)
        self.assertEqual(self.workflow.request_consent_batch(self.body)['recipient_count'],0)

    def test_missing_links_and_inactive_accounts_are_explained(self):
        data=load(self.path);data['faculty'][1]['profiles']={};dump(self.path,data)
        with self.accounts.store.connect() as db:db.execute('UPDATE users SET active=0 WHERE username=?',('uf3',))
        preview=self.workflow.request_consent_batch({**self.body,'scope':'institution'})
        self.assertEqual(preview['recipient_count'],1)
        self.assertEqual(preview['skipped_count'],2)
        self.assertTrue(any('profile link' in r['reason'] for r in preview['skipped']))
        self.assertTrue(any('No active faculty account'==r['reason'] for r in preview['skipped']))

    def test_only_office_can_send_and_preview_must_match(self):
        with self.assertRaises(Forbidden):self.for_user('f1').request_consent_batch(self.body)
        preview=self.workflow.request_consent_batch(self.body)
        with self.assertRaises(ValueError):self.workflow.request_consent_batch({**self.body,'scope':'institution','confirm':True,'preview_token':preview['preview_token']})
        self.assertEqual(self.workflow.inbox()['consent_requests'],[])


if __name__=='__main__':unittest.main()
