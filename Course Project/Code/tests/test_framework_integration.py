import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from publication_agent.core import PublicationOrchestrator, ResearchConnector


class _StructuredResponse:
    def __init__(self, schema):
        self.schema = schema

    def invoke(self, messages):
        return self.schema(
            objective="Produce a governed publication analytics report",
            steps=["Read consented records", "Validate evidence", "Await review"],
            risks=["Source coverage can differ"],
        )


class FakeGeminiChatModel:
    """Network-free test double for the two external model calls."""

    def with_structured_output(self, schema):
        return _StructuredResponse(schema)

    def invoke(self, messages):
        return SimpleNamespace(
            content="The supplied verified records were summarized without changing metrics."
        )


class FrameworkIntegrationTests(unittest.TestCase):
    def test_langchain_publication_tool_uses_governed_connector_contract(self):
        from publication_agent.langchain_tools import build_research_tools

        connector = ResearchConnector()
        tool = build_research_tools(connector)["publications_for_faculty"]
        records = tool.invoke(
            {"faculty_id": "F001", "sources": ["scholar", "scopus", "wos"]}
        )
        self.assertTrue(records)
        self.assertEqual({item["source"] for item in records}, {"scholar", "scopus", "wos"})

    def test_compiled_langgraph_runs_with_injected_groq_compatible_model(self):
        with tempfile.TemporaryDirectory() as temp:
            app = PublicationOrchestrator(
                runtime_root=Path(temp),
                use_groq=True,
                llm=FakeGeminiChatModel(),
            )
            ctx = app.run("Create the 2026 CSE bibliometric report")

        self.assertEqual(ctx.status, "AWAITING_APPROVAL")
        self.assertTrue(ctx.framework_evidence["langchain"])
        self.assertTrue(ctx.framework_evidence["langgraph"])
        self.assertTrue(ctx.framework_evidence["mcp"]["connected"])
        self.assertEqual(ctx.framework_evidence["mcp"]["transport"], "stdio")
        self.assertEqual(ctx.framework_evidence["llm_provider"], "Gemini")
        self.assertEqual(ctx.framework_evidence["completed_labs"], ctx.executed_labs)
        self.assertIn("groq_plan", ctx.lab_results["lab01"])
        self.assertIn("groq_explanation", ctx.report)
        self.assertEqual(
            ctx.lab_results["lab05"]["langchain_tool"]["name"],
            "publications_for_faculty",
        )

    def test_dashboard_mode_requires_environment_key_without_injected_model(self):
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, {}, clear=True):
            app = PublicationOrchestrator(runtime_root=Path(temp), use_groq=True)
            with self.assertRaisesRegex(RuntimeError, "GEMINI_API_KEY"):
                app.run("Create the 2026 CSE bibliometric report")


if __name__ == "__main__":
    unittest.main(verbosity=2)
