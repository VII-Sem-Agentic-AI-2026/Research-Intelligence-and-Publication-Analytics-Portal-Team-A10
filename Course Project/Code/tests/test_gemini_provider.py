import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from publication_agent.ai_text import response_text
from publication_agent.assistant import reject_secrets, sensitive_chat_text
from publication_agent.assistant_errors import provider_error
from publication_agent.core import ResearchConnector
from publication_agent.groq_graph import GeminiLangGraphPipeline


class GeminiProviderTests(unittest.TestCase):
    def test_graph_selects_developer_api_with_explicit_key_and_model(self):
        app = SimpleNamespace(connector=ResearchConnector())
        with patch.dict(os.environ, {
            "GEMINI_API_KEY": "test-gemini-key-no-network",
            "GEMINI_MODEL": "gemini-3.5-flash-lite",
            "GOOGLE_GENAI_USE_VERTEXAI": "true",
        }), patch("publication_agent.groq_graph.ChatGoogleGenerativeAI") as model:
            GeminiLangGraphPipeline(app)
        args = model.call_args.kwargs
        self.assertEqual(args["google_api_key"], "test-gemini-key-no-network")
        self.assertEqual(args["model"], "gemini-3.5-flash-lite")
        self.assertFalse(args["vertexai"])
        self.assertNotIn("groq_api_key", args)

    def test_visible_gemini_text_blocks_exclude_thoughts(self):
        response = SimpleNamespace(content=[
            {"type": "text", "text": "Private reasoning", "thought": True},
            {"type": "text", "text": "Visible result"},
            {"type": "reasoning", "text": "Hidden reasoning"},
        ])
        self.assertEqual(response_text(response), "Visible result")
        self.assertEqual(response_text(SimpleNamespace(content="Plain text")), "Plain text")

    def test_google_quota_error_is_safe_and_preserves_429(self):
        class GoogleQuotaError(Exception):
            code = 429
        error = provider_error(GoogleQuotaError("private billing details"))
        self.assertEqual(error.status_code, 429)
        self.assertNotIn("private billing", str(error))

    def test_gemini_credentials_are_blocked_in_chat_and_model_tool_arguments(self):
        self.assertTrue(sensitive_chat_text("AIza" + "x" * 35))
        for key in ("gemini_api_key", "google_api_key"):
            with self.assertRaises(ValueError):
                reject_secrets({key: "test-secret"})


if __name__ == "__main__":
    unittest.main()
