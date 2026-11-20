import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from publication_agent.api_secrets import (
    forget_gemini_key, key_path, restore_gemini_key, save_gemini_key,
)
from publication_agent.actions import Actions


@unittest.skipUnless(os.name == "nt", "Windows DPAPI")
class SavedGeminiKeyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.env = patch.dict(os.environ, {"GEMINI_API_KEY": ""})
        self.env.start()
        self.addCleanup(self.env.stop)

    def test_save_is_encrypted_and_restored_in_a_new_process(self):
        import subprocess
        import sys
        key = "test-only-gemini-secret-that-is-not-a-real-key"
        save_gemini_key(self.root, key)
        self.assertNotIn(key.encode(), key_path(self.root).read_bytes())
        script = (
            "import os,sys; from publication_agent.api_secrets import restore_gemini_key; "
            "assert restore_gemini_key(sys.argv[1]); "
            "assert os.environ['GEMINI_API_KEY'] == sys.stdin.read()"
        )
        result = subprocess.run([sys.executable, "-B", "-c", script, str(self.root)],
                                input=key, text=True, capture_output=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_disable_removes_saved_key_and_prevents_reload(self):
        actions = Actions({"role": "admin"}, None, self.root, None)
        saved = actions.execute("/api/ai-key", {"api_key": "test-only-secret-that-is-long-enough"})
        self.assertTrue(saved["remembered"])
        actions.execute("/api/ai-disable", {})
        self.assertFalse(key_path(self.root).exists())
        self.assertFalse(restore_gemini_key(self.root))
        self.assertNotIn("GEMINI_API_KEY", os.environ)

    def test_corrupt_saved_key_does_not_stop_local_dashboard(self):
        key_path(self.root).write_bytes(b"invalid-ciphertext")
        with self.assertWarnsRegex(RuntimeWarning, "could not be unlocked"):
            self.assertFalse(restore_gemini_key(self.root))
        self.assertEqual(os.environ["GEMINI_API_KEY"], "")

    def test_environment_key_takes_precedence(self):
        save_gemini_key(self.root, "saved-test-key")
        os.environ["GEMINI_API_KEY"] = "environment-test-key"
        self.assertTrue(restore_gemini_key(self.root))
        self.assertEqual(os.environ["GEMINI_API_KEY"], "environment-test-key")
        forget_gemini_key(self.root)
