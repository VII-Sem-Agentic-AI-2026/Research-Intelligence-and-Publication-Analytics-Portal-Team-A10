import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from publication_agent.accounts import Accounts, Forbidden


class AccountDesignationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.root=Path(self.temp.name)
        self.hash_patch=patch.object(Accounts,'hash',return_value='fixture-hash')
        self.hash_patch.start()
        self.accounts=Accounts(self.root)
        self.accounts.create({'username':'admin','name':'Admin','role':'admin','password':'fixture-password'},bootstrap=True)
        self.admin=self.accounts.users()[0]

    def tearDown(self):
        self.hash_patch.stop()
        self.temp.cleanup()

    def faculty(self,designation=''):
        self.accounts.create({'username':'faculty','name':'Faculty','role':'faculty','faculty_id':'F1',
            'password':'fixture-password','designation':designation},self.admin)
        return next(u for u in self.accounts.users() if u['role']=='faculty')

    def test_designation_is_saved_without_changing_access(self):
        faculty=self.faculty('Assistant Professor')
        self.accounts.set_designation(faculty['id'],'Associate Professor',self.admin)
        updated=next(u for u in self.accounts.users() if u['id']==faculty['id'])
        self.assertEqual(updated['designation'],'Associate Professor')
        self.assertEqual(updated['role'],'faculty')
        self.assertEqual(updated['faculty_id'],'F1')
        self.assertNotIn('password_hash',updated)

    def test_unsupported_designation_is_rejected(self):
        with self.assertRaises(ValueError):self.faculty('Lecturer')
        self.assertEqual(len(self.accounts.users()),1)
        with self.assertRaises(ValueError):self.accounts.set_designation(self.admin['id'],'Lecturer',self.admin)

    def test_only_active_administrators_can_change_designation(self):
        faculty=self.faculty()
        with self.assertRaises(Forbidden):self.accounts.set_designation(faculty['id'],'Professor',faculty)
        with self.accounts.store.connect() as db:db.execute('UPDATE users SET active=0 WHERE id=?',(self.admin['id'],))
        with self.assertRaises(Forbidden):self.accounts.set_designation(faculty['id'],'Professor',self.admin)

    def test_reopening_accounts_preserves_existing_records(self):
        faculty=self.faculty('Professor')
        reopened=Accounts(self.root)
        self.assertEqual(next(u for u in reopened.users() if u['id']==faculty['id'])['designation'],'Professor')

    def test_hod_defaults_to_head_designation(self):
        self.accounts.create({'username':'head','name':'Head','role':'hod','department':'CSE','password':'fixture-password'},self.admin)
        self.assertEqual(next(u for u in self.accounts.users() if u['role']=='hod')['designation'],'Prof. & Head')


if __name__=='__main__':unittest.main()
