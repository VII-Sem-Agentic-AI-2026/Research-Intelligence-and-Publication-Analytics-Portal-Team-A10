"""Regression for the source-coverage hallucination found with live Gemini."""
import copy
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from publication_agent.core import PublicationOrchestrator, ResearchConnector
from publication_agent.narrative import actual_source_coverage, unsupported_source_mentions
from tests.test_framework_integration import FakeGeminiChatModel
from tests.review_helpers import review_all

class SummaryModel(FakeGeminiChatModel):
    def __init__(self,text):self.text=text;self.messages=[]
    def invoke(self,messages):
        self.messages=messages
        return SimpleNamespace(content=self.text)

class SourceNarrativeTests(unittest.TestCase):
    def setUp(self):self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)/'runtime'
    def tearDown(self):self.temp.cleanup()
    def run_report(self,text,wos_consent=False,wos_records=True):
        model=SummaryModel(text)
        app=PublicationOrchestrator(runtime_root=self.root,use_groq=True,llm=model)
        data=copy.deepcopy(ResearchConnector().data)
        for faculty in data['faculty']:faculty['consent']['wos']=wos_consent
        if not wos_records:data['publications']=[p for p in data['publications'] if p['source']!='wos']
        app.connector.data=data
        return app,app.run('2026 CSE bibliometric'),model

    def test_prompt_does_not_include_planned_but_unused_sources(self):
        _,ctx,model=self.run_report('Google Scholar and Scopus contributed the records.')
        payload=model.messages[-1][1]
        self.assertIn('actual_source_coverage',payload)
        self.assertNotIn("'sources':",payload)
        self.assertNotIn("'wos'",payload)
        self.assertEqual(ctx.plan['sources'],('scholar','scopus','wos'))
        self.assertEqual(ctx.report['actual_source_coverage']['queried_sources'],['scholar','scopus'])

    def test_unused_wos_claim_is_withheld_and_flagged(self):
        _,ctx,_=self.run_report('This report combines Scholar, Scopus and Web of Science.')
        validation=ctx.report['groq_explanation_validation']
        self.assertFalse(validation['passed']);self.assertEqual(validation['unexpected_sources'],['wos'])
        self.assertIn('Narrative withheld',ctx.report['groq_explanation'])
        self.assertNotIn('Web of Science',ctx.report['groq_explanation'])
        self.assertTrue(validation['fallback_used'])

    def test_valid_source_claim_is_kept(self):
        _,ctx,_=self.run_report('Google Scholar and Scopus contributed the records.')
        self.assertTrue(ctx.report['groq_explanation_validation']['passed'])
        self.assertNotIn('withheld',ctx.report['groq_explanation'])

    def test_source_aliases_are_detected(self):
        coverage={'sources_with_in_scope_records':['scholar','scopus']}
        for name in ('WoS','WOS','Web of Science','Web-of-Science','Web\u2011of\u2011Science'):
            with self.subTest(name=name):self.assertEqual(unsupported_source_mentions(name,coverage),['wos'])
        self.assertEqual(unsupported_source_mentions('PubMed',coverage),['pubmed'])

    def test_queried_source_without_records_cannot_be_claimed_as_contributing(self):
        _,ctx,_=self.run_report('Web of Science contributed records.',wos_consent=True,wos_records=False)
        coverage=ctx.report['actual_source_coverage']
        self.assertIn('wos',coverage['queried_sources'])
        self.assertNotIn('wos',coverage['sources_with_in_scope_records'])
        self.assertFalse(ctx.report['groq_explanation_validation']['passed'])

    def test_wos_is_allowed_when_it_really_contributes(self):
        _,ctx,_=self.run_report('Scholar, Scopus and Web of Science contributed records.',wos_consent=True)
        self.assertTrue(ctx.report['groq_explanation_validation']['passed'])

    def test_coverage_comes_from_results_not_plan_or_stored_summary(self):
        report={'plan':{'sources':['scholar','scopus','wos']},'actual_source_coverage':{'sources_with_in_scope_records':['wos']},
                'faculty_results':[{'faculty':{'faculty_id':'DEMO'},'coverage':['scopus'],'publications':[{'evidence':[{'source':'scopus'}]}]}]}
        coverage=actual_source_coverage(report)
        self.assertEqual(coverage['sources_with_in_scope_records'],['scopus'])

    def test_old_misleading_draft_is_blocked_at_publication(self):
        app,ctx,_=self.run_report('Scholar and Scopus contributed records.')
        review_all(app,ctx);ctx=app.runtime.load_run(ctx.run_id)
        ctx.report['groq_explanation']='Scholar, Scopus and Web of Science contributed records.'
        app.runtime.checkpoint(ctx)
        with self.assertRaisesRegex(RuntimeError,'narrative source claims'):
            app.approve(ctx.run_id,'Synthetic reviewer','Research Dean')

if __name__=='__main__':unittest.main()
