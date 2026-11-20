"""Independent cases for the engineering review's failure scenarios."""
import base64
import copy
import json
import os
import tempfile
import unittest
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

from publication_agent.core import PublicationOrchestrator, FacultyWorker, ResearchConnector, deduplicate, dump, load
from publication_agent.storage import Store
from publication_agent.accounts import Accounts
from tests.review_helpers import review_all


class ReviewRegressions(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.root=Path(self.temp.name)/'runtime'

    def tearDown(self):
        self.temp.cleanup()

    def app(self, data=None, **kwargs):
        app=PublicationOrchestrator(runtime_root=self.root, **kwargs)
        if data is not None: app.connector.data=data
        return app

    def test_reporting_window_and_current_snapshot_are_explicit(self):
        app=self.app()
        ctx=app.run('2026 CSE bibliometric', {'scope':'publication_year'})
        self.assertEqual(ctx.report['summary']['publications'],0)
        self.assertIn('not citations received',ctx.report['citation_basis'])
        self.assertTrue(ctx.validation['passed'])

    def test_shared_publication_counted_once_with_two_faculty_associations(self):
        data=copy.deepcopy(ResearchConnector().data)
        data['publications']=[p for p in data['publications'] if p['faculty_id']=='F001']
        other=copy.deepcopy(data['publications'])
        for p in other:p['faculty_id']='F002'
        data['publications']+=other
        ctx=self.app(data).run('2026 CSE bibliometric')
        self.assertEqual(ctx.report['summary']['publications'],2)
        self.assertEqual(ctx.report['summary']['citations'],27)
        self.assertEqual(sum(len(r['publications']) for r in ctx.faculty_results),4)

    def test_twenty_faculty_fit_budget_and_partial_consent_is_supported(self):
        original=ResearchConnector().data
        data={'faculty':[], 'publications':[]}
        for i in range(20):
            faculty=copy.deepcopy(original['faculty'][0]);faculty['faculty_id']=f'F{i:03}'
            faculty['consent']={'scholar':True,'scopus':False,'wos':False}
            data['faculty'].append(faculty)
            pub=copy.deepcopy(original['publications'][0]);pub['faculty_id']=faculty['faculty_id']
            data['publications'].append(pub)
        ctx=self.app(data).run('2026 CSE bibliometric')
        self.assertEqual(len(ctx.faculty_results),20)
        self.assertEqual(ctx.tool_calls,21)
        self.assertTrue(all(r['coverage']==['scholar'] for r in ctx.faculty_results))

    def test_source_corroboration_does_not_claim_author_identity(self):
        pubs,_=deduplicate(ResearchConnector().data['publications'])
        self.assertTrue(pubs[0]['verified'])
        self.assertEqual(pubs[0]['attribution_status'],'unreviewed')

    def test_individual_review_is_required_and_rejection_blocks_publish(self):
        app=self.app();ctx=app.run('2026 CSE bibliometric')
        with self.assertRaises(RuntimeError):app.approve(ctx.run_id,'Dean','Research Dean')
        r=ctx.faculty_results[0];p=r['duplicate_proposals'][0]
        app.review_duplicate(ctx.run_id,r['faculty']['faculty_id'],p['group'],'rejected','Dean')
        with self.assertRaises(RuntimeError):app.approve(ctx.run_id,'Dean','Research Dean')

    def test_sqlite_migration_retains_json_and_publication_associations(self):
        self.root.mkdir()
        path=self.root/'source_data.json'
        data=ResearchConnector().data
        path.write_text(json.dumps(data),encoding='utf-8')
        store=Store(self.root);store.migrate()
        self.assertEqual(json.loads(path.read_text(encoding='utf-8')),data)
        self.assertEqual(store.read(path)[1],data)
        with store.connect() as db:
            self.assertGreater(db.execute('SELECT count(*) FROM faculty_publications').fetchone()[0],0)

    def test_concurrent_release_ids_are_unique(self):
        store=Store(self.root)
        with ThreadPoolExecutor(max_workers=4) as pool:
            versions=list(pool.map(lambda i:store.release({'title':str(i)})['version'],range(8)))
        self.assertEqual(len(set(versions)),8)

    def test_invalid_password_and_missing_session_are_denied(self):
        accounts=Accounts(self.root)
        accounts.create({'username':'admin','password':'A test password 123!','name':'Admin','role':'admin'},bootstrap=True)
        with self.assertRaises(PermissionError):accounts.login('admin','wrong')
        with self.assertRaises(PermissionError):accounts.principal({})
        token=accounts.login('admin','A test password 123!')
        self.assertEqual(accounts.principal({'Cookie':f'portal_session={token}'})['role'],'admin')

    def test_resuming_saved_artifacts_does_not_repeat_completed_reads(self):
        app=self.app();ctx=app.run('2026 CSE bibliometric',selected_labs=[8])
        ctx.status='FAILED'
        # Simulate a crash after persisted Lab 08, before remaining labs.
        ctx.requested_labs=['lab14'];app.runtime.checkpoint(ctx)
        app=self.app();restored=app.resume(ctx.run_id)
        self.assertEqual(restored.status,'AWAITING_APPROVAL')
        self.assertEqual(restored.tool_calls,ctx.tool_calls)

    def test_upload_same_source_id_for_two_faculty_preserves_both(self):
        from publication_agent.web import DashboardService
        with patch('publication_agent.web.DEFAULT_RUNTIME',self.root):
            service=DashboardService()
            payload=base64.b64encode(b'Title,Year,DOI,Cited by,EID\nShared work,2025,10.5/shared,7,SAME\n').decode()
            for faculty in ('F001','F002'):
                service.upload_export('source.csv',payload,'publication','scopus',faculty)
            records=load(self.root/'source_data.json')['publications']
            self.assertEqual(len([p for p in records if p['source_id']=='SAME']),2)
            with Store(self.root).connect() as db:
                self.assertEqual(db.execute('SELECT count(*) FROM imports').fetchone()[0],2)

    def test_http_rejects_anonymous_access_and_ignores_forged_reviewer_role(self):
        import threading
        import http.client
        from types import SimpleNamespace
        from unittest.mock import Mock
        from http.server import ThreadingHTTPServer
        from publication_agent.role_web import RoleHandler as Handler
        approve=Mock(return_value={'status':'approved'})
        service=SimpleNamespace(app=SimpleNamespace(approve=approve),report=lambda run_id:{'plan':{'department':'CSE'}})
        accounts=Accounts(self.root)
        accounts.create({'username':'admin','password':'A test password 123!','name':'Admin','role':'admin'},bootstrap=True)
        accounts.create({'username':'reviewer','password':'A test password 123!','name':'Authenticated reviewer','role':'research_office'},accounts.users()[0])
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
        client=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=5)
        try:
            with patch('publication_agent.web.SERVICE',service), patch('publication_agent.web.DEFAULT_RUNTIME',self.root), patch.dict(os.environ,{'PORTAL_REVIEW_TOKEN':'x'*32,'PORTAL_REVIEWER':'Authenticated reviewer'}):
                client.request('GET','/api/runs');response=client.getresponse();response.read()
                self.assertEqual(response.status,401)
                client.request('POST','/api/login',json.dumps({'username':'reviewer','password':'A test password 123!'}),{'Content-Type':'application/json'})
                response=client.getresponse();response.read();cookie=response.getheader('Set-Cookie').split(';')[0]
                self.assertEqual(response.status,200)
                client.request('POST','/api/approve',json.dumps({'run_id':'r1','reviewer':'Imposter','role':'Research Dean'}),{'Content-Type':'application/json','Cookie':cookie})
                response=client.getresponse();response.read()
                self.assertEqual(response.status,200)
                approve.assert_called_once_with('r1','Authenticated reviewer','Research Office',None)
                client.request('POST','/api/approve','{}',{'Cookie':cookie,'Origin':'http://untrusted.example'})
                response=client.getresponse();response.read();self.assertEqual(response.status,403)
        finally:
            client.close();server.shutdown();server.server_close();worker.join()

    def test_groq_tools_read_each_source_once_and_narrative_numbers_are_checked(self):
        from tests.test_framework_integration import FakeGeminiChatModel
        from types import SimpleNamespace
        class BadNarrative(FakeGeminiChatModel):
            def invoke(self,messages):return SimpleNamespace(content='There are 999999 citations.')
        app=self.app(use_groq=True,llm=BadNarrative())
        ctx=app.run('2026 CSE bibliometric')
        events=[json.loads(line) for line in (self.root/'audit.jsonl').read_text(encoding='utf-8').splitlines()]
        reads=[e for e in events if e['action']=='tool.publications']
        self.assertEqual(len(reads),6)
        self.assertIn('withheld',ctx.report['groq_explanation'])
        self.assertTrue(ctx.framework_evidence['langgraph'])

    def test_invalid_import_types_and_negative_counts_are_rejected(self):
        from publication_agent.validation import validate_dataset
        data=copy.deepcopy(ResearchConnector().data)
        data['publications'][0]['citations']=-1
        with self.assertRaises(ValueError):validate_dataset(data)
        data['publications'][0]['citations']=1
        data['faculty'][0]['consent']['scholar']='true'
        with self.assertRaises(ValueError):validate_dataset(data)


if __name__=='__main__':unittest.main()
