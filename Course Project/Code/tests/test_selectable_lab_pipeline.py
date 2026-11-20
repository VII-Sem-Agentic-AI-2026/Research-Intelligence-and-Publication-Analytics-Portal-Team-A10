import tempfile
import unittest
from pathlib import Path

from publication_agent.core import PublicationOrchestrator
from publication_agent.labs.pipeline import LabPipeline


class SelectableLabPipelineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.app = PublicationOrchestrator(runtime_root=Path(self.temp.name))

    def tearDown(self):
        self.temp.cleanup()

    def test_selecting_lab_08_connects_only_its_required_chain(self):
        requested, resolved = LabPipeline.resolve([8])
        self.assertEqual(requested, [8])
        self.assertEqual(resolved, [1, 2, 3, 5, 6, 7, 8])
        self.assertNotIn(4, resolved)

    def test_partial_selection_persists_requested_and_executed_labs(self):
        ctx = self.app.run("Create the 2026 CSE bibliometric report", selected_labs=[8])
        self.assertEqual(ctx.requested_labs, ["lab08"])
        self.assertEqual(ctx.executed_labs, ["lab01", "lab02", "lab03", "lab05", "lab06", "lab07", "lab08"])
        self.assertEqual(ctx.status, "SELECTED_LABS_COMPLETED")
        self.assertEqual(list(ctx.lab_results), ctx.executed_labs)

    def test_selecting_lab_14_connects_the_complete_capstone(self):
        ctx = self.app.run("Create the 2026 CSE bibliometric report", selected_labs=[14])
        self.assertEqual(ctx.requested_labs, ["lab14"])
        self.assertEqual(ctx.executed_labs, [f"lab{i:02d}" for i in range(1, 15)])
        self.assertEqual(ctx.status, "AWAITING_APPROVAL")
        self.assertTrue(ctx.lab_results["lab14"]["acceptance"])

    def test_invalid_lab_number_is_rejected(self):
        with self.assertRaises(ValueError):
            LabPipeline.resolve([15])


if __name__ == "__main__":
    unittest.main(verbosity=2)
