"""No-network tests of the real tool loop, data scope and confirmed actions."""
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from langchain_core.messages import AIMessage, ToolMessage, SystemMessage
from publication_agent import web
from publication_agent.accounts import Accounts, Forbidden
from publication_agent.actions import Actions
from publication_agent.assistant import Assistant, confirm
from tests.review_helpers import review_all


class ScriptedModel:
    def __init__(self,action=None,parameters=None):
        self.action=action;self.parameters=parameters or {};self.calls=[];self.bound=[]
    def bind_tools(self,tools):self.bound=tools;return self
    def invoke(self,messages):
        self.calls.append(list(messages))
        if len(self.calls)==1 and self.action:
            return AIMessage(content='',tool_calls=[{'name':'portal_action','args':{'action':self.action,'parameters':self.parameters},'id':'tool-1','type':'tool_call'}])
        return AIMessage(content='I checked your authorized workspace. See the action result.')


class AssistantTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)/'runtime'
        self.root_patch=patch('publication_agent.web.DEFAULT_RUNTIME',self.root);self.root_patch.start()
        self.service=web.DashboardService()
        self.service_patch=patch('publication_agent.web.SERVICE',self.service);self.service_patch.start()
        self.accounts=Accounts(self.root)
        password='Test account password 123!'
        self.accounts.create({'username':'admin','password':password,'name':'Admin','role':'admin'},bootstrap=True)
        admin=self.accounts.users()[0]
        for username,role,faculty,dept in [('asha','faculty','F001','CSE'),('dean','dean',None,''),('ece-head','hod',None,'ECE')]:
            self.accounts.create({'username':username,'password':password,'name':username,'role':role,'faculty_id':faculty,'department':dept},admin)
        self.users={u['username']:u for u in self.accounts.users()}

    def tearDown(self):
        self.service_patch.stop();self.root_patch.stop();self.temp.cleanup()

    def gateway(self,user):return Actions(self.users[user],self.service,self.root,self.accounts)
    def assistant(self,user,model=None):return Assistant(self.gateway(user),llm=model or ScriptedModel())

    def test_groq_tool_loop_only_supplies_faculty_authorized_data(self):
        model=ScriptedModel('publications');agent=self.assistant('asha',model)
        reply=agent.chat('Show my publications')
        self.assertTrue(model.bound)
        self.assertTrue(reply['reply'])
        for message in model.calls[-1]:
            if isinstance(message,(ToolMessage,SystemMessage)):
                self.assertNotIn('F002',message.content)
                self.assertNotIn('Vikram Sen',message.content)
        self.assertTrue((self.root/'assistant'/f'user-{self.users["asha"]["id"]}.json').exists())

    def test_faculty_can_generate_personal_report_without_department_access(self):
        agent=self.assistant('asha',ScriptedModel('generate_report',{'year':2026}))
        reply=agent.chat('Generate my 2026 bibliometric report')
        runs=self.gateway('asha').workspace()['runs']
        self.assertEqual(len(runs),1)
        self.assertEqual({r['faculty']['faculty_id'] for r in runs[0]['report']['faculty_results']},{'F001'})
        self.assertIn('reply',reply)
        self.assertIn('imported citations',reply['reply'])
        self.assertEqual(reply['actions'][0]['type'],'open_report')
        self.assertEqual(len(agent.llm.calls),1)

    def test_model_cannot_promote_faculty_or_publish(self):
        agent=self.assistant('asha')
        with self.assertRaises(Forbidden):agent.tool('approve_report',{'run_id':'anything','role':'dean'})
        with self.assertRaises(Forbidden):agent.tool('create_account',{'username':'intruder','role':'admin'})
        with self.assertRaises(Forbidden):agent.tool('list_accounts',{})

    def test_hod_cannot_inspect_another_department_report(self):
        run=self.service.app.run('2026 CSE bibliometric')
        agent=self.assistant('ece-head')
        with self.assertRaises(Forbidden):agent.tool('report_detail',{'run_id':run.run_id})
        with self.assertRaises(Forbidden):agent.tool('approve_report',{'run_id':run.run_id})

    def test_approval_requires_user_confirmation_and_is_not_replayable(self):
        run=self.service.app.run('2026 CSE bibliometric');review_all(self.service.app,run)
        agent=self.assistant('dean')
        first=agent.tool('approve_report',{'run_id':run.run_id})
        agent.tool('approve_report',{'run_id':run.run_id})
        self.assertEqual(first['status'],'awaiting_user_confirmation')
        self.assertEqual(len(agent.ui),1)
        self.assertEqual(self.service.app.runtime.load_run(run.run_id).status,'AWAITING_APPROVAL')
        pending_id=agent.ui[0]['id']
        with self.assertRaises(Forbidden):confirm(self.gateway('admin'),pending_id)
        self.assertEqual(confirm(self.gateway('dean'),pending_id)['status'],'completed')
        self.assertEqual(self.service.app.runtime.load_run(run.run_id).status,'PUBLISHED')
        with self.assertRaises(Forbidden):confirm(self.gateway('dean'),pending_id)

    def test_secure_credentials_and_file_contents_are_not_tool_arguments(self):
        agent=self.assistant('admin')
        for payload in [{'password':'not-to-model'},{'api_key':'not-to-model'},{'content_base64':'not-to-model'}]:
            with self.assertRaises(ValueError):agent.tool('create_account',payload)
        count=len(self.accounts.users())
        result=agent.tool('create_account',{'username':'future-user','role':'faculty','faculty_id':'F001'})
        self.assertEqual(result['status'],'waiting_for_user')
        self.assertEqual(len(self.accounts.users()),count)
        self.assertEqual(agent.ui[-1]['form'],'create_account')

    def test_each_accounts_history_is_private(self):
        self.assistant('asha').chat('My personal question')
        model=ScriptedModel();self.assistant('dean',model).chat('What reports can I review?')
        self.assertNotIn('My personal question',str(model.calls))

    def test_missing_key_is_explicit_and_api_keys_are_not_sent_in_chat(self):
        with patch.dict(os.environ,{'GEMINI_API_KEY':''}):
            with self.assertRaisesRegex(RuntimeError,'Gemini is not configured'):Assistant(self.gateway('admin'))
        model=ScriptedModel();agent=self.assistant('admin',model)
        with self.assertRaises(ValueError):agent.chat('gsk_'+'a'*35)
        self.assertEqual(model.calls,[])

    def test_gemini_assistant_uses_developer_api_and_keeps_key_out_of_history(self):
        with patch.dict(os.environ,{'GEMINI_API_KEY':'test-gemini-secret-not-a-real-key'}),patch('publication_agent.assistant.ChatGoogleGenerativeAI') as model:
            Assistant(self.gateway('admin'))
        self.assertEqual(model.call_args.kwargs['google_api_key'],'test-gemini-secret-not-a-real-key')
        self.assertFalse(model.call_args.kwargs['vertexai'])

    def test_faculty_upload_form_is_bound_to_own_profile(self):
        agent=self.assistant('asha')
        agent.tool('upload',{'kind':'roster','faculty_id':'F002'})
        self.assertEqual(agent.ui[-1]['defaults']['faculty_id'],'F001')
        self.assertEqual(agent.ui[-1]['defaults']['kind'],'publication')

    def test_first_vague_report_request_asks_for_year_without_tools(self):
        model=ScriptedModel('generate_report')
        reply=self.assistant('asha',model).chat('make report')
        self.assertIn('Which reporting year',reply['reply'])
        self.assertEqual(model.calls,[])
        self.assertEqual(reply['actions'],[])
        self.assertEqual(self.gateway('asha').workspace()['runs'],[])

    def test_repeated_tool_calls_stop_without_repeating_secure_form(self):
        class RepeatingModel(ScriptedModel):
            def invoke(self,messages):
                self.calls.append(list(messages))
                return AIMessage(content='',tool_calls=[{'name':'portal_action',
                    'args':{'action':'upload','parameters':{}},
                    'id':f'tool-{len(self.calls)}','type':'tool_call'}])
        model=RepeatingModel()
        reply=self.assistant('asha',model).chat('Upload my publications')
        self.assertEqual(len(model.calls),2)
        self.assertEqual(len(reply['actions']),1)
        self.assertIn('displayed form',reply['reply'])
        self.assertNotIn('action limit',reply['reply'])


if __name__=='__main__':unittest.main()
