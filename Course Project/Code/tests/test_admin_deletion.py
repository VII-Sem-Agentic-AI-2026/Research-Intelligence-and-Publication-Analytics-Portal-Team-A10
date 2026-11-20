"""Administrator-only record deletion and anti-resurrection regressions."""
import json
import unittest
from pathlib import Path
from unittest.mock import patch
import test_accounts_roles as fixtures
from publication_agent.core import dump,load
from publication_agent.storage import Store
from tests.review_helpers import review_all

class AdminDeletionTests(unittest.TestCase):
    setUp=fixtures.AccountsRolesTests.setUp
    tearDown=fixtures.AccountsRolesTests.tearDown
    request=fixtures.AccountsRolesTests.request
    login=fixtures.AccountsRolesTests.login

    def test_account_must_be_disabled_and_admin_cannot_delete_self(self):
        admin=self.login('admin');user=next(u for u in self.accounts.users() if u['username']=='asha')
        self.assertEqual(self.request('/api/users/delete',{'user_id':user['id'],'confirm':True},admin)[0],400)
        own=self.accounts.users()[0]
        self.assertEqual(self.request('/api/users/delete',{'user_id':own['id'],'confirm':True},admin)[0],400)
        self.assertEqual(self.request('/api/users/delete',{'user_id':user['id'],'confirm':True},self.login('dean'))[0],403)

    def test_disabled_account_deleted_without_reusing_identity_or_deleting_faculty(self):
        admin=self.login('admin');cookie=self.login('asha');user=next(u for u in self.accounts.users() if u['username']=='asha')
        dump(self.root/'assistant'/f"user-{user['id']}.json",[{'role':'user','text':'Private synthetic history'}])
        before=self.service.faculty_profiles()
        self.assertEqual(self.request('/api/users/disable',{'user_id':user['id']},admin)[0],200)
        self.assertEqual(self.request('/api/users/delete',{'user_id':user['id']},admin)[0],400)
        status,result,_=self.request('/api/users/delete',{'user_id':user['id'],'confirm':True},admin)
        self.assertEqual(status,200,result);self.assertTrue(result['deleted'])
        self.assertNotIn(user['id'],{u['id'] for u in self.accounts.users()})
        self.assertEqual(self.request('/api/me',cookie=cookie)[0],401)
        self.assertFalse((self.root/'assistant'/f"user-{user['id']}.json").exists())
        self.assertEqual(self.service.faculty_profiles(),before)
        self.accounts.create({'username':'replacement','password':fixtures.PASSWORD,'role':'faculty','faculty_id':'F001','name':'Replacement'},self.accounts.users()[0])
        new=next(u for u in self.accounts.users() if u['username']=='replacement')
        self.assertGreater(new['id'],user['id'])

    def test_highest_deleted_user_id_is_never_reused(self):
        admin=self.accounts.users()[0]
        self.accounts.create({'username':'highest','password':fixtures.PASSWORD,'role':'dean','name':'Highest'},admin)
        user=next(u for u in self.accounts.users() if u['username']=='highest')
        self.accounts.disable(user['id'],admin);self.accounts.delete(user['id'],admin)
        self.accounts.create({'username':'next-user','password':fixtures.PASSWORD,'role':'dean','name':'Next'},admin)
        self.assertGreater(next(u for u in self.accounts.users() if u['username']=='next-user')['id'],user['id'])

    def test_report_deletion_is_admin_only_confirmed_and_source_data_remains(self):
        run=self.service.app.run('2026 CSE bibliometric');before=load(self.service.active_data_path());admin=self.login('admin')
        for role in ['asha','dean','cse-head']:
            self.assertEqual(self.request('/api/reports/delete',{'run_id':run.run_id,'confirm':True},self.login(role))[0],403)
        self.assertEqual(self.request('/api/reports/delete',{'run_id':run.run_id},admin)[0],400)
        status,result,_=self.request('/api/reports/delete',{'run_id':run.run_id,'confirm':True},admin)
        self.assertEqual(status,200,result)
        self.assertFalse((self.root/'runs'/(run.run_id+'.json')).exists())
        self.assertEqual(self.request('/api/report?run_id='+run.run_id,cookie=admin)[0],400)
        self.assertEqual(self.request('/api/reports',cookie=admin)[1]['total'],0)
        self.assertEqual(load(self.service.active_data_path()),before)

    def test_published_report_versions_history_and_current_removed_without_resurrection(self):
        run=self.service.app.run('2026 CSE bibliometric');review_all(self.service.app,run)
        published=self.service.app.approve(run.run_id,'Dean','Research Dean')
        admin=self.login('admin');version=published['version']
        self.assertEqual(self.request('/api/reports/delete',{'run_id':run.run_id,'confirm':True},admin)[0],200)
        with self.accounts.store.connect() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM releases').fetchone()[0],0)
            self.assertEqual(db.execute('SELECT count(*) FROM deletion_events WHERE target=?',(run.run_id,)).fetchone()[0],1)
        self.assertIsNone(load(self.root/'published'/'current.json'))
        self.assertFalse(load(self.root/'history.json',[]))
        self.assertEqual(self.request('/api/export/nirf.csv',cookie=admin)[0],403)
        with self.assertRaises(FileNotFoundError):self.service.app.rollback(version)
        # Simulate an old compatibility file reappearing; migration and rollback must ignore it.
        path=self.root/'published'/f'version-{version}.json';path.write_text(json.dumps(published),encoding='utf-8')
        Store(self.root).migrate()
        self.assertIsNone(load(path))
        with self.assertRaises(FileNotFoundError):self.service.app.rollback(version)
        with self.assertRaises(ValueError):Store(self.root).release(dict(published))
        with self.assertRaises(ValueError):dump(self.root/'published'/'current.json',published)
        other=self.service.app.run('2026 CSE bibliometric');review_all(self.service.app,other)
        final=self.service.app.approve(other.run_id,'Dean','Research Dean')
        self.assertGreater(final['version'],version)
        self.assertEqual(load(self.root/'published'/'current.json')['run_id'],other.run_id)

    def test_cleanup_failure_keeps_deleted_record_hidden_and_retries(self):
        run=self.service.app.run('2026 CSE bibliometric');admin=self.login('admin')
        original=Path.unlink
        def fail(path,*args,**kwargs):
            if path.name==run.run_id+'.json':raise OSError('Synthetic cleanup failure')
            return original(path,*args,**kwargs)
        with patch.object(Path,'unlink',fail):
            status,result,_=self.request('/api/reports/delete',{'run_id':run.run_id,'confirm':True},admin)
            self.assertEqual(status,200,result);self.assertTrue(result['warnings'])
            self.assertEqual(self.request('/api/reports',cookie=admin)[1]['total'],0)
        Store(self.root).export_pending()
        self.assertFalse((self.root/'runs'/(run.run_id+'.json')).exists())

    def test_assistant_account_deletion_requires_explicit_confirmation(self):
        from publication_agent.actions import Actions
        from publication_agent.assistant import Assistant,confirm
        from tests.test_assistant import ScriptedModel
        admin=self.accounts.users()[0];target=next(u for u in self.accounts.users() if u['username']=='dean')
        self.accounts.disable(target['id'],admin)
        actions=Actions(admin,self.service,self.root,self.accounts)
        agent=Assistant(actions,llm=ScriptedModel())
        result=agent.tool('delete_account',{'user_id':target['id']})
        self.assertEqual(result['status'],'awaiting_user_confirmation')
        self.assertIn(target['id'],{u['id'] for u in self.accounts.users()})
        pending=agent.ui[-1]['id'];confirm(actions,pending)
        self.assertNotIn(target['id'],{u['id'] for u in self.accounts.users()})
        with self.assertRaises(PermissionError):confirm(actions,pending)
