"""Permanent regression cases for the 16 engineering-audit findings."""
import base64
import copy
import csv
import io
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from publication_agent import web
from publication_agent.core import ResearchConnector, AcceptanceSuite, PlanSkill, PlannerAgent, GovernedRuntime, load
from publication_agent.importers import parse_publication_export, parse_faculty_roster
from publication_agent.labs.pipeline import LabPipeline
from publication_agent.accounts import Accounts
from publication_agent.actions import Actions
from publication_agent.assistant import Assistant, safe_history
from publication_agent.assistant_errors import AssistantServiceError, provider_error
from tests.test_assistant import ScriptedModel
from tests.review_helpers import review_all

class AuditFixes(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)/'runtime'
        self.root_patch=patch('publication_agent.web.DEFAULT_RUNTIME',self.root);self.root_patch.start()
        self.service=web.DashboardService();self.service.import_data(copy.deepcopy(ResearchConnector().data))
        self.service_patch=patch('publication_agent.web.SERVICE',self.service);self.service_patch.start()
    def tearDown(self):
        self.service_patch.stop();self.root_patch.stop();self.temp.cleanup()

    def draft(self):return self.service.app.run('2026 CSE bibliometric')

    def test_all_consent_can_be_withdrawn_and_uploads_then_stop(self):
        profile=self.service.faculty_profiles()[0];profile['consent']={s:False for s in ('scholar','scopus','wos')}
        self.service.save_faculty(profile)
        payload=base64.b64encode(b'Title,Year,Cited by\nSynthetic,2025,2\n').decode()
        with self.assertRaises(PermissionError):self.service.upload_export('x.csv',payload,'publication','scopus',profile['faculty_id'])
        self.assertTrue(load(self.root/'source_data.json')['publications'],'Revoking consent must not silently delete imported data')

    def test_pending_report_cannot_publish_after_source_revocation(self):
        ctx=self.draft();review_all(self.service.app,ctx)
        profile=self.service.faculty_profiles()[0];profile['consent']['scopus']=False;self.service.save_faculty(profile)
        with self.assertRaisesRegex(PermissionError,'consent changed'):self.service.app.approve(ctx.run_id,'Dean','Research Dean')
        self.assertFalse((self.root/'published'/'current.json').exists())

    def test_arithmetic_and_evidence_references_are_recomputed(self):
        ctx=self.draft()
        for field in ('summary','evidence','metric'):
            report=copy.deepcopy(ctx.report)
            if field=='summary':report['summary']['citations']=999999
            elif field=='evidence':report['faculty_results'][0]['metrics']['evidence_publication_ids']=['NONEXISTENT']
            else:report['faculty_results'][0]['metrics']['h_index']=999
            with self.subTest(field=field):self.assertFalse(AcceptanceSuite().validate(report).passed)

    def test_publication_revalidates_even_when_saved_validation_was_green(self):
        ctx=self.draft();review_all(self.service.app,ctx);ctx=self.service.app.runtime.load_run(ctx.run_id)
        ctx.report['summary']['citations']=999999;self.service.app.runtime.checkpoint(ctx)
        with self.assertRaisesRegex(RuntimeError,'revalidation'):self.service.app.approve(ctx.run_id,'Dean','Research Dean')

    def test_profile_links_are_validated_for_profile_and_bulk_import(self):
        profile=self.service.faculty_profiles()[0];profile['profiles']['scopus']='not a URL'
        with self.assertRaises(ValueError):self.service.save_faculty(profile)
        data=copy.deepcopy(ResearchConnector().data);data['faculty'][0]['profiles']['scopus']='javascript:alert(1)'
        with self.assertRaises(ValueError):self.service.import_data(data)

    def test_csv_export_neutralizes_formula_cells(self):
        ctx=self.draft();review_all(self.service.app,ctx);ctx=self.service.app.runtime.load_run(ctx.run_id)
        ctx.report['faculty_results'][0]['publications'][0]['title']='=1+1';self.service.app.runtime.checkpoint(ctx)
        self.service.app.approve(ctx.run_id,'Dean','Research Dean')
        rows=list(csv.DictReader(io.StringIO(self.service.export_report('nirf').decode('utf-8-sig'))))
        self.assertEqual(rows[0]['title'],"'=1+1")

    def test_one_line_nested_and_quoted_bibtex(self):
        data=b'@article{demo, title={Synthetic {nested} title}, year={2025}, doi={10.0000/demo}}\n@article{other, title="A title, with comma", year=2026, citations=3}'
        rows=parse_publication_export('x.bib',data,'scopus','F001')
        self.assertEqual(len(rows),2);self.assertIn('{nested}',rows[0]['title']);self.assertEqual(rows[1]['title'],'A title, with comma')
        self.assertIsNone(rows[0]['citations'],'Missing citation counts must not become measured zero')

    def test_incomplete_roster_is_rejected_with_row_number(self):
        with self.assertRaisesRegex(ValueError,'3'):
            parse_faculty_roster('x.csv',b'Faculty ID,Full Name,Department\nONE,Synthetic One,CSE\nTWO,Synthetic Two,\n')

    def test_citation_values_are_not_silently_truncated_or_invented(self):
        with self.assertRaises(ValueError):parse_publication_export('x.json',b'[{"title":"Synthetic","year":2025,"citations":"3.5"}]','scopus','F001')
        rows=parse_publication_export('x.json',b'[{"title":"Synthetic","year":2025,"citations":"unknown"}]','scopus','F001')
        self.assertIsNone(rows[0]['citations'])

    def test_missing_doi_candidate_requires_metadata_correction(self):
        data=load(self.root/'source_data.json');data['publications'][1]['doi']='';data['publications'][1]['title']=data['publications'][0]['title'];self.service.import_data(data)
        ctx=self.draft();r=ctx.faculty_results[0];candidate=next(p for p in r['duplicate_proposals'] if p['match_rule']=='title_year_with_missing_doi')
        with self.assertRaisesRegex(ValueError,'missing DOI'):
            self.service.app.review_duplicate(ctx.run_id,'F001',candidate['group'],'confirmed','Dean')

    def test_correction_required_report_cannot_resume(self):
        ctx=self.draft();proposal=ctx.faculty_results[0]['duplicate_proposals'][0]
        self.service.app.review_duplicate(ctx.run_id,'F001',proposal['group'],'rejected','Dean')
        with self.assertRaisesRegex(RuntimeError,'corrected inputs'):self.service.app.resume(ctx.run_id)

    def test_empty_lab_selection_and_explicit_budget(self):
        with self.assertRaises(ValueError):LabPipeline.resolve([])
        self.assertEqual(len(LabPipeline.resolve(None)[0]),14)
        with patch.dict(os.environ,{'RESEARCH_TOOL_BUDGET':'200'}):
            self.assertEqual(GovernedRuntime(self.root,tool_budget=2).tool_budget,2)
            self.assertEqual(GovernedRuntime(self.root).tool_budget,200)

    def test_full_department_names_and_year_bounds(self):
        self.assertTrue(PlannerAgent().clarify('2026 Mechanical Engineering bibliometric report')['complete'])
        with self.assertRaises(ValueError):PlanSkill()({'department':'ME','reporting_year':999999,'metric_pack':'bibliometric'})

    def test_password_messages_blocked_before_model_and_storage(self):
        user={'id':999,'username':'test','name':'Synthetic','role':'admin'};model=ScriptedModel()
        agent=Assistant(Actions(user,self.service,self.root,Accounts(self.root)),llm=model)
        with self.assertRaises(ValueError):agent.chat('My password is SyntheticSecretOnly123!')
        self.assertEqual(model.calls,[]);self.assertFalse(agent.history_path.exists())
        cleaned=safe_history([{'role':'user','text':'My password is SyntheticSecretOnly123!'}])
        self.assertNotIn('SyntheticSecretOnly123!',str(cleaned))

    def test_rate_limits_expose_safe_status_and_message(self):
        error=provider_error(RuntimeError('Error code: 429 - org_SYNTHETIC billing https://example.invalid'))
        self.assertIsInstance(error,AssistantServiceError);self.assertEqual(error.status_code,429)
        self.assertNotIn('org_SYNTHETIC',str(error));self.assertNotIn('billing',str(error))

if __name__=='__main__':unittest.main()
