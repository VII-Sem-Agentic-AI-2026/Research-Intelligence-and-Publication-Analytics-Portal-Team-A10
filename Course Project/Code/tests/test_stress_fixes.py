"""Regressions for the scenario audit's five confirmed findings."""
import base64
import copy
import json
import socket
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from dataclasses import asdict
import test_accounts_roles as fixtures
from publication_agent.accounts import Accounts
from publication_agent.core import dump, load
from publication_agent.storage import Store

class StressFixesTests(unittest.TestCase):
    setUp=fixtures.AccountsRolesTests.setUp
    tearDown=fixtures.AccountsRolesTests.tearDown
    request=fixtures.AccountsRolesTests.request
    login=fixtures.AccountsRolesTests.login

    def office(self):
        self.accounts.create({'username':'office','password':fixtures.PASSWORD,'name':'Officer','role':'research_office'},self.accounts.users()[0])
        return self.login('office')

    def test_unknown_upload_kind_has_no_side_effect(self):
        before=copy.deepcopy(load(self.service.active_data_path()))
        body={'kind':'unknown-kind','faculty_id':'F001','source':'scopus','filename':'x.csv','content_base64':base64.b64encode(b'Title,Year,Cited by\nSynthetic,2025,1\n').decode()}
        status,_,_=self.request('/api/upload',body,self.login('admin'))
        self.assertEqual(status,400)
        self.assertEqual(before,load(self.service.active_data_path()))

    def test_partial_body_does_not_block_reads(self):
        cookie=self.login('asha')
        slow=socket.create_connection(('127.0.0.1',self.server.server_port))
        try:
            slow.sendall(b'POST /api/upload HTTP/1.1\r\nHost: 127.0.0.1\r\nContent-Length: 2\r\n\r\n{')
            time.sleep(.1)
            start=time.perf_counter()
            self.assertEqual(self.request('/api/me',cookie=cookie)[0],200)
            self.assertLess(time.perf_counter()-start,.8)
            slow.sendall(b'}');slow.recv(4096)
        finally:slow.close()

    def test_long_report_does_not_block_reads_or_other_users_writes(self):
        office=self.office();faculty=self.login('asha');started=threading.Event();release=threading.Event()
        def slow(*args,**kwargs):
            started.set();release.wait(5);return {'messages':[]}
        with patch.object(self.service,'chat',side_effect=slow):
            thread=threading.Thread(target=lambda:self.request('/api/chat',{'message':'2026 CSE bibliometric'},office))
            thread.start()
            try:
                self.assertTrue(started.wait(3))
                start=time.perf_counter()
                self.assertEqual(self.request('/api/me',cookie=faculty)[0],200)
                profile=copy.deepcopy(self.service.faculty_profiles()[0]);profile['consent']={s:False for s in ('scholar','scopus','wos')}
                self.assertEqual(self.request('/api/faculty',{'profile':profile},faculty)[0],200)
                self.assertLess(time.perf_counter()-start,.8)
            finally:release.set();thread.join()

    def test_committed_consent_survives_export_failure_and_retries(self):
        office=self.office();faculty=self.login('asha')
        _,r,_=self.request('/api/consent/request',{'faculty_id':'F001','sources':['scopus'],'message':'Annual report consent'},office)
        original=Path.write_text
        def fail_export(path,*args,**kwargs):
            if path.parent==self.root and path.name.startswith('source_data.json.'):raise OSError('Synthetic disk failure')
            return original(path,*args,**kwargs)
        with patch.object(Path,'write_text',fail_export):
            status,result,_=self.request('/api/consent/respond',{'request_id':r['request_id'],'decision':'approved'},faculty)
            self.assertEqual(status,200,result);self.assertEqual(result['status'],'approved');self.assertTrue(result['warnings'])
            self.assertEqual(self.service.active_data_path(),self.root/'source_data.json')
            self.assertTrue(next(f for f in self.service.faculty_profiles() if f['faculty_id']=='F001')['consent']['scopus'])
            with self.accounts.store.connect() as db:
                self.assertEqual(db.execute('SELECT count(*) FROM compatibility_exports').fetchone()[0],1)
                self.assertGreater(db.execute('SELECT count(*) FROM publications').fetchone()[0],0)
        self.service.reload_connector()
        self.assertTrue((self.root/'source_data.json').exists())
        with self.accounts.store.connect() as db:self.assertEqual(db.execute('SELECT count(*) FROM compatibility_exports').fetchone()[0],0)

    def test_disabled_accepted_dean_can_be_reassigned_and_old_request_invalidated(self):
        office=self.office();admin=self.accounts.users()[0]
        self.accounts.create({'username':'new-dean','password':fixtures.PASSWORD,'name':'New Dean','role':'dean'},admin)
        dean=next(u for u in self.accounts.users() if u['username']=='dean');replacement=next(u for u in self.accounts.users() if u['username']=='new-dean')
        run=self.service.app.run('2026 CSE bibliometric')
        _,first,_=self.request('/api/review/request',{'run_id':run.run_id,'dean_id':dean['id'],'message':'Review draft'},office)
        self.assertEqual(self.request('/api/review/respond',{'request_id':first['request_id'],'decision':'accepted'},self.login('dean'))[0],200)
        self.accounts.disable(dean['id'],admin)
        status,second,_=self.request('/api/review/request',{'run_id':run.run_id,'dean_id':replacement['id'],'message':'Replace disabled reviewer'},office)
        self.assertEqual(status,200,second)
        ctx=self.service.app.runtime.load_run(run.run_id)
        self.assertEqual(ctx.review_assignment['dean_id'],replacement['id']);self.assertEqual(ctx.review_assignment['status'],'pending')
        with self.accounts.store.connect() as db:self.assertEqual(db.execute('SELECT status FROM dean_review_requests WHERE id=?',(first['request_id'],)).fetchone()[0],'cancelled')
        self.assertEqual(self.request('/api/approve',{'run_id':run.run_id},self.login('new-dean'))[0],403)

    def test_workspace_is_compact_and_publication_pages_remain_scoped(self):
        cookie=self.login('asha')
        data=copy.deepcopy(load(self.service.active_data_path()));template=copy.deepcopy(next(p for p in data['publications'] if p['faculty_id']=='F001'))
        for i in range(125):
            p=copy.deepcopy(template);p.update(title='Synthetic page '+str(i),source_id='PAGE'+str(i));data['publications'].append(p)
        dump(self.root/'source_data.json',data)
        _,workspace,_=self.request('/api/workspace',cookie=cookie)
        self.assertEqual(workspace['publications'],[]);self.assertGreater(workspace['counts']['publications'],125)
        _,page,_=self.request('/api/publications?query=Synthetic%20page&page=2&page_size=50',cookie=cookie)
        self.assertEqual(page['total'],125);self.assertEqual(len(page['records']),50)
        self.assertTrue(all(p['faculty_id']=='F001' for p in page['records']))
        self.assertEqual(self.request('/api/publications?page_size=10000',cookie=cookie)[0],400)
        self.assertEqual(self.request('/api/publications?page=0',cookie=cookie)[0],400)
        _,other,_=self.request('/api/publications?query=Synthetic%20page',cookie=self.login('vikram'))
        self.assertEqual(other['total'],0)

    def test_report_summaries_pagination_and_authorized_detail(self):
        ctx=self.service.app.run('2026 CSE bibliometric')
        for i in range(22):
            value=asdict(ctx);value['run_id']='run-page'+str(i)
            dump(self.root/'runs'/(value['run_id']+'.json'),value)
        cookie=self.login('dean')
        _,page,_=self.request('/api/reports?page=2',cookie=cookie)
        self.assertEqual(len(page['records']),10);self.assertEqual(page['total'],23)
        self.assertNotIn('faculty_results',page['records'][0]['report'])
        _,detail,_=self.request('/api/report?run_id='+ctx.run_id,cookie=cookie)
        self.assertTrue(detail['detail_loaded']);self.assertTrue(detail['report']['faculty_results'])
        self.assertEqual(self.request('/api/report?run_id='+ctx.run_id,cookie=self.login('ece-head'))[0],403)

    def test_pending_publications_are_visible_scoped_and_unknown_values_preserved(self):
        data=copy.deepcopy(load(self.service.active_data_path()))
        data['pending_publications']=[{'faculty_id':'F001','source':'vidwan','source_id':'PENDING-1','title':'Pending metadata example','year':None,'citations':None,'url':'https://example.test/1','retrieved':'2026-10-26','record_status':'pending_review','review_reasons':['Citation count unknown']}]
        dump(self.root/'source_data.json',data)
        _,own,_=self.request('/api/publications?query=Pending',cookie=self.login('asha'))
        self.assertEqual(own['total'],1);self.assertIsNone(own['records'][0]['citations'])
        self.assertIsNone(own['records'][0]['year'])
        _,other,_=self.request('/api/publications?query=Pending',cookie=self.login('vikram'))
        self.assertEqual(other['total'],0)
        _,workspace,_=self.request('/api/workspace',cookie=self.login('asha'))
        self.assertEqual(workspace['counts']['needs_review'],1)
