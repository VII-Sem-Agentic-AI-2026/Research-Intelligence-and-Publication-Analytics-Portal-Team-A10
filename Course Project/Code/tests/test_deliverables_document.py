import csv
import io
import tempfile
import unittest
from tests.review_helpers import review_all
from pathlib import Path
from unittest.mock import patch

from publication_agent.core import PublicationOrchestrator
from publication_agent.web import DashboardService


class DeliverablesDocumentTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self): self.temp.cleanup()

    def test_faculty_profile_requires_consent_and_link(self):
        with patch("publication_agent.web.DEFAULT_RUNTIME", self.root):
            service = DashboardService()
            profile = {"faculty_id":"F900","name":"Dr Test","department":"CSE","consent":{"scholar":True,"scopus":False,"wos":False},"profiles":{"scholar":"https://scholar.example/F900","scopus":"","wos":""}}
            result = service.save_faculty(profile)
            self.assertEqual(result["status"], "created")
            self.assertEqual(service.faculty_profiles()[-1]["faculty_id"], "F900")
            profile["profiles"]["scholar"] = ""
            with self.assertRaises(ValueError): service.save_faculty(profile)

    def test_duplicate_proposals_include_explainable_confidence(self):
        app = PublicationOrchestrator(runtime_root=self.root)
        ctx = app.run("Create the 2026 CSE bibliometric report", selected_labs=[8])
        proposals = [p for result in ctx.faculty_results for p in result["duplicate_proposals"]]
        self.assertTrue(proposals)
        self.assertTrue(all(p["decision"] == "pending" for p in proposals))
        self.assertTrue(all(p['match_rule'] and p['reason'] for p in proposals))
        self.assertTrue(all('confidence' not in p for p in proposals))

    def test_human_approval_confirms_merges(self):
        app = PublicationOrchestrator(runtime_root=self.root)
        ctx = app.run("Create the 2026 CSE bibliometric report")
        with self.assertRaises(RuntimeError):
            app.approve(ctx.run_id, 'Research Dean', 'Research Dean')
        review_all(app, ctx)
        final = app.approve(ctx.run_id, "Research Dean", "Research Dean")
        proposals = [p for result in final["faculty_results"] for p in result["duplicate_proposals"]]
        self.assertTrue(all(p["decision"] == "confirmed" for p in proposals))
        self.assertTrue(all(p["reviewed_by"] == "Research Dean" for p in proposals))

    def test_nirf_and_naac_exports_require_approval_and_include_provenance(self):
        with patch("publication_agent.web.DEFAULT_RUNTIME", self.root):
            service = DashboardService()
            with self.assertRaises(PermissionError): service.export_report("nirf")
            ctx = service.app.run("Create the 2026 CSE bibliometric report")
            review_all(service.app, ctx)
            service.app.approve(ctx.run_id, "Dean", "Research Dean")
            rows = list(csv.DictReader(io.StringIO(service.export_report("naac").decode("utf-8-sig"))))
            self.assertTrue(rows)
            self.assertEqual(rows[0]["scheme"], "NAAC")
            self.assertIn("retrieved_dates", rows[0])
            self.assertIn("scopus", rows[0])
            self.assertIn("wos", rows[0])


if __name__ == "__main__": unittest.main(verbosity=2)
