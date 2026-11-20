"""First-login assignment and ownership boundaries using isolated datasets."""
import base64
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from publication_agent import web
from publication_agent.accounts import Accounts, Forbidden
from publication_agent.actions import Actions
from publication_agent.core import load


class FacultyOnboardingTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)/'runtime'
        self.patch=patch('publication_agent.web.DEFAULT_RUNTIME',self.root)
        self.patch.start();self.addCleanup(self.patch.stop)
        self.service=web.DashboardService()
        self.accounts=Accounts(self.root)
        self.password='Initial test password 42!'
        self.accounts.create(dict(username='admin',name='Admin',password=self.password,role='admin'),bootstrap=True)
        admin=self.accounts.users()[0]
        self.accounts.create(dict(username='faculty',name='Faculty',password=self.password,role='faculty',faculty_id='F001'),admin)
        self.user=next(u for u in self.accounts.users() if u['role']=='faculty')
        self.actions=Actions(self.user,self.service,self.root,self.accounts)

    def test_department_saved_to_account_and_dataset_without_changing_publications(self):
        before=load(self.service.active_data_path())
        self.assertFalse(self.user['department_confirmed'])
        self.actions.execute('/api/onboarding',{'department':'ECE'})
        after=load(self.service.active_data_path())
        self.assertEqual(after['publications'],before['publications'])
        self.assertEqual(next(f for f in after['faculty'] if f['faculty_id']=='F001')['department'],'ECE')
        self.assertEqual(next(f for f in after['faculty'] if f['faculty_id']=='F002')['department'],'CSE')
        account=next(u for u in self.accounts.users() if u['id']==self.user['id'])
        self.assertEqual(account['department'],'ECE');self.assertTrue(account['department_confirmed'])
        with self.assertRaises(ValueError):self.actions.execute('/api/onboarding',{'department':'CSE'})

    def test_invalid_department_does_not_complete_onboarding(self):
        with self.assertRaises(ValueError):self.actions.execute('/api/onboarding',{'department':'invented department'})
        self.assertFalse(next(u for u in self.accounts.users() if u['id']==self.user['id'])['department_confirmed'])

    def test_upload_requires_department_and_cannot_target_other_faculty(self):
        body=dict(kind='publication',faculty_id='F001',source='scholar',filename='export.csv',content_base64=base64.b64encode(b'Title,Year,Cited by,URL\nMy updated paper,2025,7,https://example.test/paper\n').decode())
        with self.assertRaises(Forbidden):self.actions.execute('/api/upload',body)
        self.actions.execute('/api/onboarding',{'department':'CSE'})
        with self.assertRaises(Forbidden):self.actions.execute('/api/upload',body|{'faculty_id':'F002'})
        result=self.actions.execute('/api/upload',body)
        self.assertEqual(result['faculty_id'],'F001')
        records=load(self.service.active_data_path())['publications']
        self.assertEqual(next(p for p in records if p['title']=='My updated paper')['faculty_id'],'F001')

    def test_password_change_revokes_initial_password_and_sessions(self):
        token=self.accounts.login('faculty',self.password)
        self.accounts.change_password(self.user,self.password,'Replacement password 43!')
        with self.assertRaises(PermissionError):self.accounts.login('faculty',self.password)
        with self.assertRaises(PermissionError):self.accounts.principal({'Cookie':'portal_session='+token})
        self.assertTrue(self.accounts.login('faculty','Replacement password 43!'))
