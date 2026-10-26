import json,tempfile,threading,time,unittest,urllib.request
from pathlib import Path
from datetime import datetime,timedelta
from unittest.mock import patch
from storage import Store,RUNTIME
from hub import Hub,next_time
from office_tools import OfficeTools
from extended_tools import ExtendedTools,BUNDLE,public_url
from sandbox import run_python
from server import Server
from test_office import ScriptedModel
from http.server import ThreadingHTTPServer
from http.server import BaseHTTPRequestHandler

class TeamModel(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def do_POST(self):
        payload=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        user=next((m['content'] for m in payload['messages'] if m['role']=='user'),'');child='只读子Agent' in str(user);has_result=any(m['role']=='tool' for m in payload['messages'])
        with self.server.guard:
            self.server.payloads.append(payload)
            if child:self.server.active+=1;self.server.peak=max(self.server.peak,self.server.active)
        if child:time.sleep(.25)
        if child and not has_result:name='read_document';args={'path':'示例会议记录.md'}
        elif not child and not has_result:name='delegate_tasks';args={'tasks':[{'role':'核查甲','task':'读取示例会议记录.md，核对负责人甲截止时间'},{'role':'核查乙','task':'读取示例会议记录.md，核对负责人乙截止时间'}]}
        else:name=None;args={}
        if name:delta={'role':'assistant','tool_calls':[{'index':0,'id':'call-'+str(time.monotonic_ns()),'type':'function','function':{'name':name,'arguments':json.dumps(args)}}]};reason='tool_calls'
        else:delta={'role':'assistant','content':'已读取虚构示例，截止时间需以来源核对。' if child else '两个只读子任务已返回，来源可核对。'};reason='stop'
        try:
            self.send_response(200);self.send_header('Content-Type','text/event-stream');self.send_header('Connection','close');self.end_headers()
            for value,finish in [(delta,None),({},reason)]:
                item={'id':'team-test','object':'chat.completion.chunk','created':1,'model':'synthetic-team','choices':[{'index':0,'delta':value,'finish_reason':finish}]}
                self.wfile.write(('data: '+json.dumps(item)+'\n\n').encode())
            usage={'id':'team-test','object':'chat.completion.chunk','created':1,'model':'synthetic-team','choices':[],'usage':{'prompt_tokens':100,'completion_tokens':30,'total_tokens':130}}
            self.wfile.write(('data: '+json.dumps(usage)+'\n\ndata: [DONE]\n\n').encode());self.wfile.flush()
        finally:
            if child:
                with self.server.guard:self.server.active-=1

class SuiteTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=RUNTIME,prefix='suite-test-');self.store=Store(self.temp.name);self.hub=Hub(self.store)
    def tearDown(self):self.hub.db.close();self.temp.cleanup()
    def tools(self,sid=None):return OfficeTools(self.hub.context(sid),lambda *a:None)
    def test_sessions_preserve_legacy_and_append_to_original_session(self):
        first=self.hub.session()['id'];second=self.hub.create('第二个项目')['id']
        item={'question':'只属于第一个项目','mode':'office','answer':{'kind':'office','body':'结果'}}
        self.hub.append(first,item)
        self.assertFalse(self.hub.session(second)['history']);self.assertEqual(self.hub.session(first)['history'][0]['question'],item['question'])
        folder=Path(self.temp.name)/'project-b';folder.mkdir();self.hub.update_session(second,workspace=str(folder))
        self.assertNotEqual(self.hub.session(first)['workspace'],self.hub.session(second)['workspace'])
        self.hub.select(first);self.assertEqual(self.store.history[0]['question'],item['question'])
    def test_memories_are_persistent_scoped_searchable_and_deletable(self):
        first=self.hub.session()['id'];item=self.hub.memory_add('报告先列结论，再附来源。',first);global_item=self.hub.memory_add('全局称呼示例老板。')
        second=self.hub.create()['id'];self.assertNotIn(item['id'],[i['id'] for i in self.hub.memories('',second)])
        self.assertIn(global_item['id'],[i['id'] for i in self.hub.memories('',second)])
        self.assertEqual(self.hub.memories('报告',first)[0]['id'],item['id']);self.hub.memory_delete(item['id']);self.assertFalse(self.hub.memories('报告',first))
        with self.assertRaises(ValueError):self.hub.memory_add('密码：SYNTHETIC')
    def test_schedule_rules_edit_pause_and_due(self):
        sid=self.hub.session()['id'];future=(datetime.now().astimezone()+timedelta(minutes=1)).isoformat()
        item=self.hub.schedule_save(sid,'合成提醒','整理合成资料',{'kind':'once','at':future,'timezone':'Asia/Shanghai'})
        self.hub.schedule_toggle(item['id'],False);self.assertFalse(self.hub.schedule(item['id'])['enabled'])
        self.hub.schedule_save(sid,'新的标题','新指令',{'kind':'interval','seconds':60},item['id']);self.assertEqual(len(self.hub.schedules()),1)
        for rule in [{'kind':'daily','time':'09:00'},{'kind':'weekly','time':'09:00','weekdays':[0,2]},{'kind':'cron','expression':'0 9 * * 1-5'}]:self.assertTrue(next_time(rule))
        with self.assertRaises(ValueError):next_time({'kind':'interval','seconds':1})
        self.hub.schedule_delete(item['id']);self.assertFalse(self.hub.schedules())
    def test_cron_uses_standard_monday_to_friday_semantics(self):
        from zoneinfo import ZoneInfo
        friday=datetime(2026,10,30,10,0,tzinfo=ZoneInfo('Asia/Shanghai'))
        target=datetime.fromisoformat(next_time({'kind':'cron','expression':'0 9 * * 1-5','timezone':'Asia/Shanghai'},friday))
        self.assertEqual(target.weekday(),0);self.assertEqual(target.hour,9)
    def test_approval_is_explicit_once_and_rejection_prevents_execution(self):
        tools=self.tools();tools.store.job_id='synthetic-job';ext=ExtendedTools(tools,dict(tools.store.config,plan_mode=True),'')
        failures=[]
        def attempt():
            try:ext.gate('生成Word')
            except ValueError as error:failures.append(str(error))
        thread=threading.Thread(target=attempt);thread.start()
        for _ in range(100):
            pending=self.hub.pending()
            if pending:break
            time.sleep(.01)
        self.hub.decide(pending[0]['id'],False);thread.join(2);self.assertTrue(failures)
        with self.assertRaises(ValueError):self.hub.decide(pending[0]['id'],True)
        with self.assertRaises(ValueError):ext.gate('再次尝试')
        self.assertFalse(self.hub.pending());self.assertFalse(tools.artifacts)
    def test_wasi_python_operates_on_copies_and_collects_real_output(self):
        tools=self.tools();source=Path(tools.root)/'source.txt';source.write_text('original',encoding='utf-8')
        script="import json\nopen('/work/input/source.txt','w').write('copy changed')\njson.dump({'total':12.5+7.25},open('/work/output/result.json','w'))\nprint('done')"
        result=run_python(script,['source.txt'],tools,BUNDLE/'sandbox-runtime')
        self.assertEqual(result['exit_code'],0);self.assertIn('done',result['stdout']);self.assertEqual(source.read_text(),'original')
        self.assertEqual(json.loads((tools.output/result['artifacts'][0]['name']).read_text())['total'],19.75)
    def test_wasi_cannot_write_runtime_or_read_host_and_times_out(self):
        tools=self.tools();runtime=BUNDLE/'sandbox-runtime';before=(runtime/'LICENSE').read_bytes()
        result=run_python("open('/runtime/LICENSE','w').write('no')",[],tools,runtime)
        self.assertNotEqual(result['exit_code'],0);self.assertEqual((runtime/'LICENSE').read_bytes(),before)
        result=run_python("import os\nprint(os.path.exists('C:/Windows/win.ini'))",[],tools,runtime)
        self.assertIn('False',result['stdout'])
        result=run_python("try:\n import socket\n socket.create_connection(('example.com',80),timeout=1)\n print('NETWORK_ALLOWED')\nexcept Exception:\n print('NETWORK_UNAVAILABLE')",[],tools,runtime)
        self.assertIn('NETWORK_UNAVAILABLE',result['stdout']);self.assertNotIn('NETWORK_ALLOWED',result['stdout'])
        with self.assertRaises(ValueError):run_python('while True: pass',[],tools,runtime,timeout=.2)
    def test_web_tools_preserve_source_and_reject_local_urls(self):
        tools=self.tools();ext=ExtendedTools(tools,{'base_url':'https://api.deepseek.com'},'SYNTHETIC')
        with patch('extended_tools.provider_request',return_value={'results':[{'title':'官方示例','url':'https://example.com','summary':'示例内容','content':'有限正文'}]}):
            result=ext.web_search('合成关键词');self.assertEqual(len(result['results']),1);self.assertIn('web:https://example.com',tools.sources)
        for url in ('file:///C:/Windows/win.ini','http://127.0.0.1','http://192.168.1.2','https://user:pass@example.com'):
            with self.assertRaises(ValueError):public_url(url)
    def test_real_sdk_delegates_parallel_readonly_children_and_merges_sources(self):
        from office_agent import OfficeAgent
        model=ThreadingHTTPServer(('127.0.0.1',0),TeamModel);model.payloads=[];model.guard=threading.Lock();model.active=0;model.peak=0
        thread=threading.Thread(target=model.serve_forever,daemon=True);thread.start()
        view=self.hub.context();view.job_id='synthetic-team-job';config=dict(view.config,base_url=f'http://127.0.0.1:{model.server_port}',model='synthetic-team',use_model=True)
        try:
            result=OfficeAgent().run('合成分工测试','office',config,'SYNTHETIC',[],lambda *a:None,view)
            self.assertEqual(result['kind'],'office');self.assertIn('两个',result['body']);self.assertTrue(result['sources']);self.assertGreaterEqual(model.peak,2)
            children=[p for p in model.payloads if any(m['role']=='user' and '只读子Agent' in str(m['content']) for m in p['messages'])]
            self.assertEqual(len(children),4)
            for payload in children:
                names=[t['function']['name'] for t in payload['tools']]
                self.assertNotIn('create_document',names);self.assertNotIn('run_python_batch',names);self.assertNotIn('delegate_tasks',names)
        finally:model.shutdown();model.server_close();thread.join(3)

class ServerSuiteTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=RUNTIME,prefix='suite-http-test-');self.store=Store(self.temp.name);self.server=Server(self.store)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
    def tearDown(self):self.server.shutdown();self.server.server_close();self.thread.join(3);self.temp.cleanup()
    def api(self,path,data=None):
        req=self.server.base+path if data is None else urllib.request.Request(self.server.base+path,data=json.dumps(data).encode(),headers={'Content-Type':'application/json'})
        return json.load(urllib.request.urlopen(req,timeout=5))
    def test_background_jobs_keep_session_ownership_and_allow_switch(self):
        first=self.api('sessions')['active'];job=self.api('ask',{'question':'列出资料清单'})
        second=self.api('sessions/new',{'title':'第二个项目'})['id'];self.assertNotEqual(first,second)
        for _ in range(100):
            if self.api('job/'+job['id'])['state'] in ('done','error'):break
            time.sleep(.01)
        self.assertFalse(self.api('history')['history']);self.api('sessions/select',{'id':first});self.assertEqual(len(self.api('history')['history']),1)
    def test_preview_real_excel_sheets_and_markdown(self):
        tool=OfficeTools(self.server.hub.context(),lambda *a:None)
        item=tool.create_workbook('预览合成表',[{'title':'甲页','columns':['项目','金额'],'rows':[['示例',12.5]]},{'title':'乙页','columns':['备注'],'rows':[['虚构']]}])
        preview=self.api('preview?id='+item['id']+'&sheet='+urllib.parse.quote('乙页'))
        self.assertEqual(preview['sheets'],['甲页','乙页']);self.assertEqual(preview['rows'][1][0]['value'],'虚构')
    def test_json_artifact_download_is_original_bytes(self):
        tool=OfficeTools(self.server.hub.context(),lambda *a:None);raw=b'{"total":19.75}'
        item=tool._save('JSON结果','.json',raw)
        with urllib.request.urlopen(self.server.base+'artifact/'+item['id']) as response:self.assertEqual(response.read(),raw)
    def test_local_plan_rejection_keeps_no_artifacts_and_is_saved(self):
        sid=self.api('sessions')['active'];self.api('sessions/update',{'id':sid,'plan_mode':True})
        jid=self.api('ask',{'question':'生成会议纪要模板'})['id']
        for _ in range(100):
            pending=self.api('approvals')['approvals']
            if pending:break
            time.sleep(.01)
        self.api('approvals/decide',{'id':pending[0]['id'],'approved':False})
        for _ in range(100):
            job=self.api('job/'+jid)
            if job['state']=='error':break
            time.sleep(.01)
        self.assertEqual(job['state'],'error');self.assertFalse(self.api('artifacts')['artifacts'])
        for _ in range(100):
            if self.api('history')['history']:break
            time.sleep(.01)
        self.assertEqual(self.api('history')['history'][-1]['answer']['kind'],'error')
    def test_due_once_schedule_runs_once_and_records_completion(self):
        item=self.api('schedules/save',{'title':'合成触发','prompt':'列出资料清单','rule':{'kind':'once','at':(datetime.now().astimezone()+timedelta(seconds=30)).isoformat()}})
        with self.server.hub.lock,self.server.hub.db:self.server.hub.db.execute('UPDATE schedules SET next_run=? WHERE id=?',((datetime.now().astimezone()-timedelta(seconds=1)).isoformat(),item['id']))
        for _ in range(100):
            current=self.server.hub.schedule(item['id'])
            if current['last_state']=='done':break
            time.sleep(.05)
        self.assertEqual(current['last_state'],'done');self.assertFalse(current['enabled']);self.assertEqual(len(self.server.jobs),1)

if __name__=='__main__':unittest.main(verbosity=2)
