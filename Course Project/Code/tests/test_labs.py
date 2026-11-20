import json
import tempfile
import unittest
from tests.review_helpers import review_all
from pathlib import Path

from publication_agent.core import (AcceptanceSuite, MemoryStore, PlanSkill, PlannerAgent,
    PublicationOrchestrator, ResearchConnector, SpecialistRegistry, compute_h_index)


class Chapter14Labs(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.app = PublicationOrchestrator(runtime_root=self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def test_lab_01_clarify_plan_revise(self):
        planner = PlannerAgent(); first = planner.clarify("Make a report")
        self.assertGreaterEqual(len(first["questions"]), 2)
        revised = planner.revise(first["answers"], {"department":"CSE", "reporting_year":2026, "metric_pack":"bibliometric"})
        self.assertEqual(PlanSkill()(revised).status, "locked")

    def test_lab_02_typed_tools_and_compute(self):
        connector = ResearchConnector()
        faculty = connector.faculty_profiles("CSE")[0]
        self.assertTrue(connector.publications(faculty, "scholar"))
        self.assertEqual(compute_h_index([10, 8, 2]), 2)

    def test_lab_03_reusable_skill_two_cases(self):
        a = PlanSkill()({"department":"CSE","reporting_year":2026,"metric_pack":"bibliometric"})
        b = PlanSkill()({"department":"ECE","reporting_year":2025,"metric_pack":"collaboration"})
        self.assertNotEqual(a.department, b.department)

    def test_lab_04_memory_separate_and_retrievable(self):
        memory = MemoryStore(self.root / "history.json")
        memory.remember({"run_id":"r1","title":"CSE report","plan":{"department":"CSE","metric_pack":"bibliometric"},"summary":{}})
        self.assertEqual(memory.retrieve("CSE", {"department":"CSE"})[0]["run_id"], "r1")

    def test_lab_05_connector_enforces_consent(self):
        connector = ResearchConnector(); faculty = connector.faculty_profiles("CSE")[0]
        faculty["consent"]["wos"] = False
        with self.assertRaises(PermissionError): connector.publications(faculty, "wos")

    def test_lab_06_runtime_audit_checkpoint(self):
        ctx = self.app.run("2026 CSE bibliometric report")
        self.assertTrue((self.root / "runs" / f"{ctx.run_id}.json").exists())
        self.assertTrue((self.root / "audit.jsonl").read_text(encoding="utf-8"))

    def test_labs_07_08_graph_parallel_merge(self):
        ctx = self.app.run("2026 CSE bibliometric report")
        self.assertEqual([x["faculty"]["faculty_id"] for x in ctx.faculty_results], ["F001", "F002"])

    def test_lab_09_grounding(self):
        ctx = self.app.run("2026 CSE bibliometric report")
        pubs = [p for r in ctx.faculty_results for p in r["publications"]]
        self.assertTrue(all(p["evidence"] and p["evidence"][0]["url"] for p in pubs))

    def test_lab_10_targeted_self_healing(self):
        ctx = self.app.run("2026 CSE bibliometric report", inject_fault="missing_caveat")
        self.assertEqual(ctx.attempts, 1); self.assertTrue(ctx.validation["passed"])

    def test_lab_11_acceptance_gate(self):
        ctx = self.app.run("2026 CSE bibliometric report")
        self.assertTrue(AcceptanceSuite().validate(ctx.report).passed)

    def test_lab_12_approval_and_rollback(self):
        ctx = self.app.run("2026 CSE bibliometric report")
        with self.assertRaises(PermissionError): self.app.approve(ctx.run_id, "Student", "student")
        review_all(self.app, ctx)
        final = self.app.approve(ctx.run_id, "Dean", "Research Dean")
        self.assertEqual(final["version"], 1)
        self.assertEqual(self.app.rollback(1)["version"], 1)

    def test_lab_13_specialist_registry(self):
        self.assertEqual(set(SpecialistRegistry.names()), {"bibliometric", "collaboration", "altmetric"})

    def test_lab_14_capstone(self):
        ctx = self.app.run("2026 CSE bibliometric report")
        review_all(self.app, ctx)
        self.assertEqual(ctx.status, "AWAITING_APPROVAL")
        final = self.app.approve(ctx.run_id, "Research Dean", "Research Dean")
        self.assertEqual(final["status"], "approved")
        self.assertTrue((self.root / "published" / "current.json").exists())


if __name__ == "__main__":
    unittest.main()
