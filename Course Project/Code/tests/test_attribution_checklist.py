import tempfile
import unittest
from pathlib import Path

from publication_agent.core import PublicationOrchestrator, RunContext


class AttributionChecklistTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.app=PublicationOrchestrator(runtime_root=Path(self.temp.name))
        self.ctx=RunContext('run-checklist','Fixture',{},status='AWAITING_APPROVAL',report={
            'faculty_results':[{'faculty':{'faculty_id':'F1'},'publications':[{}]}]})
        self.app.runtime.checkpoint(self.ctx)
        self.checks={'identity_checked':True,'publications_matched':True,'conflicts_resolved':True}

    def tearDown(self):
        self.temp.cleanup()

    def test_checklist_records_decisions_identity_and_time_without_typing(self):
        result=self.app.review_attribution('run-checklist','F1','','Dean',checks=self.checks)
        review=result['report']['faculty_results'][0]['attribution_review']
        self.assertEqual(review['checks'],self.checks)
        self.assertEqual(review['reviewer'],'Dean')
        self.assertTrue(review['time'])
        self.assertTrue(review['note'].startswith('Reviewer checklist:'))
        restored=self.app.runtime.load_run('run-checklist')
        self.assertEqual(restored.report['faculty_results'][0]['attribution_status'],'reviewer_confirmed')

    def test_incomplete_or_non_boolean_checks_do_not_confirm(self):
        for checks in [{},dict(self.checks,conflicts_resolved=False),dict(self.checks,identity_checked='true')]:
            with self.subTest(checks=checks),self.assertRaisesRegex(ValueError,'three attribution checks'):
                self.app.review_attribution('run-checklist','F1','','Dean',checks=checks)
        self.assertNotIn('attribution_status',self.app.runtime.load_run('run-checklist').report['faculty_results'][0])

    def test_historical_note_based_clients_still_work(self):
        result=self.app.review_attribution('run-checklist','F1','Profile and publications checked by reviewer','Dean')
        self.assertEqual(result['report']['faculty_results'][0]['attribution_status'],'reviewer_confirmed')


if __name__=='__main__':
    unittest.main()
