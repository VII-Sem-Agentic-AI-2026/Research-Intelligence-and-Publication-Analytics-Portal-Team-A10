"""Chapter 14 acceptance tests: one explicit outcome test for every lab.

Run from the project directory with:
    python -m unittest tests.test_all_lab_outcomes -v
"""

import json
import tempfile
import unittest
from tests.review_helpers import review_all
from pathlib import Path

from publication_agent.core import (
    DEFAULT_DATA,
    AcceptanceSuite,
    FacultyWorker,
    GovernedRuntime,
    MemoryStore,
    PlanSkill,
    PlannerAgent,
    PublicationOrchestrator,
    ResearchConnector,
    SpecialistRegistry,
    compute_h_index,
    load,
)


class EveryLabOutcomeTests(unittest.TestCase):
    """Acceptance criteria derived from Chapter 14, section 14.10."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.runtime_root = Path(self.temp.name) / "runtime"
        self.app = PublicationOrchestrator(runtime_root=self.runtime_root)

    def tearDown(self):
        self.temp.cleanup()

    def test_lab_01_agent_clarifies_plans_and_revises(self):
        """A vague request must produce >=2 questions; answers must lock a plan."""
        planner = PlannerAgent()
        vague = planner.clarify("Prepare my publication report")
        self.assertFalse(vague["complete"])
        self.assertGreaterEqual(len(vague["questions"]), 2)

        answers = planner.revise(
            vague["answers"],
            {"department": "CSE", "reporting_year": 2026, "metric_pack": "bibliometric"},
        )
        plan = PlanSkill()(answers)
        self.assertEqual(plan.status, "locked")
        self.assertEqual(plan.department, "CSE")

    def test_lab_02_key_reads_and_calculations_use_typed_tools(self):
        """Data must be read through connector methods and metrics through tools."""
        events = []
        connector = ResearchConnector(audit=lambda action, inputs, outputs: events.append(action))
        faculty = connector.faculty_profiles("CSE")[0]
        scholar_records = connector.publications(faculty, "scholar")

        self.assertTrue(scholar_records)
        self.assertIn("tool.faculty_profiles", events)
        self.assertIn("tool.publications", events)
        self.assertEqual(compute_h_index([12, 8, 3, 1]), 3)

    def test_lab_03_skills_are_reusable_across_cases(self):
        """The same planning schema must work for two different cases."""
        skill = PlanSkill()
        first = skill({"department": "CSE", "reporting_year": 2026, "metric_pack": "bibliometric"})
        second = skill({"department": "ECE", "reporting_year": 2025, "metric_pack": "collaboration"})

        self.assertEqual(first.metric_pack, "bibliometric")
        self.assertEqual(second.metric_pack, "collaboration")
        self.assertNotEqual(first.department, second.department)

    def test_lab_04_run_state_is_separate_from_retrievable_history(self):
        """A live checkpoint and approved-history store must be different files."""
        ctx = self.app.run("Create the 2026 CSE bibliometric report")
        run_file = self.runtime_root / "runs" / f"{ctx.run_id}.json"
        history_file = self.runtime_root / "history.json"

        self.assertTrue(run_file.exists())
        self.assertFalse(history_file.exists(), "Draft runs must not enter approved history")

        review_all(self.app, ctx)
        final = self.app.approve(ctx.run_id, "Research Dean", "Research Dean")
        memory = MemoryStore(history_file)
        result = memory.retrieve("CSE bibliometric", {"department": "CSE"})
        self.assertEqual(result[0]["run_id"], final["run_id"])

    def test_lab_05_connector_enforces_source_consent_and_uniform_access(self):
        """A source cannot be accessed without consent; connector remains swappable."""
        connector = ResearchConnector()
        faculty = connector.faculty_profiles("CSE")[0]
        faculty["consent"]["wos"] = False
        with self.assertRaises(PermissionError):
            connector.publications(faculty, "wos")

        # The agent contract still works when the connector reads a copied source file.
        copied_data = Path(self.temp.name) / "replacement_source.json"
        copied_data.write_text(DEFAULT_DATA.read_text(encoding="utf-8"), encoding="utf-8")
        swapped = ResearchConnector(copied_data)
        self.assertEqual(len(swapped.faculty_profiles("CSE")), 2)

    def test_lab_06_runtime_logs_inputs_outputs_and_resumes_checkpoint(self):
        """Every run must have audit events and a reloadable checkpoint."""
        ctx = self.app.run("Create the 2026 CSE bibliometric report")
        restored = self.app.runtime.load_run(ctx.run_id)
        audit_file = self.runtime_root / "audit.jsonl"
        events = [json.loads(line) for line in audit_file.read_text(encoding="utf-8").splitlines()]

        self.assertEqual(restored.run_id, ctx.run_id)
        self.assertEqual(restored.status, "AWAITING_APPROVAL")
        self.assertTrue(all("inputs" in event and "outputs" in event for event in events))
        self.assertTrue(any(event["action"].startswith("tool.") for event in events))

    def test_lab_07_full_node_graph_produces_validated_end_to_end_draft(self):
        """One request must activate all core stages and yield a gated draft."""
        ctx = self.app.run("Create the 2026 CSE bibliometric report")

        self.assertEqual(ctx.status, "AWAITING_APPROVAL")
        self.assertTrue(ctx.validation["passed"])
        self.assertEqual(len(ctx.faculty_results), 2)
        self.assertTrue(ctx.report["faculty_results"])

    def test_lab_08_parallel_fan_out_merges_every_unit_deterministically(self):
        """Every faculty unit must be processed once and merged in stable order."""
        first = self.app.run("Create the 2026 CSE bibliometric report")
        second = self.app.run("Create the 2026 CSE bibliometric report")
        first_ids = [item["faculty"]["faculty_id"] for item in first.faculty_results]
        second_ids = [item["faculty"]["faculty_id"] for item in second.faculty_results]

        self.assertEqual(first_ids, ["F001", "F002"])
        self.assertEqual(first_ids, second_ids)
        self.assertEqual(first.report["summary"], second.report["summary"])

    def test_lab_09_every_publication_and_metric_is_grounded(self):
        """Each accepted item must map to in-scope source evidence."""
        ctx = self.app.run("Create the 2026 CSE bibliometric report")
        for result in ctx.faculty_results:
            evidence_ids = set(result["metrics"]["evidence_publication_ids"])
            for publication in result["publications"]:
                self.assertIn(publication["publication_id"], evidence_ids)
                self.assertTrue(publication["evidence"])
                self.assertTrue(all(e["url"] and e["retrieved"] for e in publication["evidence"]))

        broken = dict(ctx.report)
        broken["faculty_results"] = json.loads(json.dumps(ctx.report["faculty_results"]))
        broken["faculty_results"][0]["publications"][0]["evidence"] = []
        self.assertFalse(AcceptanceSuite().validate(broken).passed)

    def test_lab_10_injected_fault_is_diagnosed_and_repaired_within_budget(self):
        """Only the failing caveat must be repaired without rebuilding the run."""
        ctx = self.app.run(
            "Create the 2026 CSE bibliometric report",
            inject_fault="missing_caveat",
        )
        self.assertEqual(ctx.attempts, 1)
        self.assertTrue(ctx.validation["passed"])
        self.assertTrue(ctx.report["faculty_results"][0]["metrics"]["caveat"])
        self.assertLessEqual(ctx.attempts, self.app.max_attempts)

    def test_lab_11_acceptance_suite_blocks_non_green_artifacts(self):
        """A report cannot advance to human review unless every check is green."""
        ctx = self.app.run("Create the 2026 CSE bibliometric report")
        self.assertTrue(all(ctx.validation["checks"].values()))

        invalid = json.loads(json.dumps(ctx.report))
        invalid["status"] = "approved"
        report = AcceptanceSuite().validate(invalid)
        self.assertFalse(report.passed)
        self.assertIn("no ranking is published without review", report.failing)

    def test_lab_12_only_authorized_human_can_publish_and_rollback(self):
        """Approval must be a hard stop; releases must be reversible."""
        ctx = self.app.run("Create the 2026 CSE bibliometric report")
        self.assertFalse((self.runtime_root / "published" / "current.json").exists())
        with self.assertRaises(PermissionError):
            self.app.approve(ctx.run_id, "Student", "student")

        review_all(self.app, ctx)
        final = self.app.approve(ctx.run_id, "Dr Dean", "Research Dean")
        restored = self.app.rollback(final["version"])
        self.assertEqual(final["status"], "approved")
        self.assertEqual(restored["version"], final["version"])

    def test_lab_13_each_domain_specialist_produces_checkable_output(self):
        """Every registered metric pack must return a method and caveat."""
        connector = ResearchConnector()
        faculty = connector.faculty_profiles("CSE")[0]
        for name in SpecialistRegistry.names():
            result = FacultyWorker(connector, name).step(faculty)
            self.assertIn("method", result["metrics"], name)
            self.assertIn("caveat", result["metrics"], name)
            self.assertIsInstance(result["metrics"]["evidence_publication_ids"], list)

    def test_lab_14_complete_product_runs_approves_and_persists_outputs(self):
        """The deployed product must finish one request-to-approved-report session."""
        dashboard = Path(__file__).resolve().parents[1] / "dashboard" / "index.html"
        script = dashboard.with_name("app.js")
        self.assertTrue(dashboard.exists())
        self.assertIn("Agent conversation", dashboard.read_text(encoding="utf-8"))
        self.assertIn("/api/chat", script.read_text(encoding="utf-8"))

        ctx = self.app.run("Create the 2026 CSE bibliometric report")
        review_all(self.app, ctx)
        final = self.app.approve(ctx.run_id, "Research Dean", "Research Dean")
        current = load(self.runtime_root / "published" / "current.json")
        audit = (self.runtime_root / "audit.jsonl").read_text(encoding="utf-8")

        self.assertEqual(final["version"], 1)
        self.assertEqual(current["run_id"], ctx.run_id)
        self.assertIn("governance.publish", audit)
        self.assertEqual(list(ctx.lab_results), [f"lab{i:02d}" for i in range(1, 15)])
        self.assertTrue(all(result["acceptance"] for result in ctx.lab_results.values()))


if __name__ == "__main__":
    unittest.main(verbosity=2)
