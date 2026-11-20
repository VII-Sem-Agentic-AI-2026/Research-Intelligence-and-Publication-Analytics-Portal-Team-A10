import os
import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch
from publication_agent.actions import Actions
from publication_agent.accounts import Forbidden

class AIControlsTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)

    def action(self,role):return Actions({'role':role},None,self.root,None)

    def test_disable_removes_local_key_without_calling_provider(self):
        with patch.dict(os.environ,{'GEMINI_API_KEY':'test-only-key'}):
            result=self.action('admin').execute('/api/ai-disable',{})
            self.assertNotIn('GEMINI_API_KEY',os.environ)
            self.assertFalse(result['configured']);self.assertTrue(result['disabled'])

    def test_other_roles_cannot_disable_shared_ai(self):
        for role in ('faculty','hod','dean','research_office'):
            with self.subTest(role=role),patch.dict(os.environ,{'GEMINI_API_KEY':'test-only-key'}):
                with self.assertRaises(Forbidden):self.action(role).execute('/api/ai-disable',{})
                self.assertEqual(os.environ['GEMINI_API_KEY'],'test-only-key')

    def test_disable_is_idempotent_and_can_be_reconfigured(self):
        with patch.dict(os.environ,{'GEMINI_API_KEY':''}):
            for _ in range(2):self.action('admin').execute('/api/ai-disable',{})
            result=self.action('admin').execute('/api/ai-key',{'api_key':'test-only-key-that-is-long-enough'})
            self.assertTrue(result['configured'])

if __name__=='__main__':unittest.main()
