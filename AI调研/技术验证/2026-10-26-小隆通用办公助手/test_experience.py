import json,tempfile,threading,time,unittest,wave,io
from datetime import datetime
from pathlib import Path
from http.server import ThreadingHTTPServer
from storage import Store,RUNTIME
from hub import Hub
from office_tools import OfficeTools
from experience import Experience,quiet
from server import Server
from speech import Speech
from test_office import ScriptedModel

class ExperienceTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=RUNTIME,prefix='experience-test-');self.store=Store(self.temp.name);self.hub=Hub(self.store);self.exp=Experience(self.hub)
    def tearDown(self):self.hub.db.close();self.temp.cleanup()
    def job(self,state='working'):
        session=self.hub.session();return {'id':'test-job','session_id':session['id'],'workspace_id':session['workspace_id'],'state':state,'question':'合成任务','mode':'office','steps':[{'label':'已读合成资料','state':'done'}],'revision':1}
    def test_interrupted_snapshot_and_deduplicated_readable_inbox_survive_reopen(self):
        job=self.job();self.exp.save(job);self.hub.db.close();self.hub=Hub(self.store);self.exp=Experience(self.hub)
        saved=self.exp.task(job['id']);self.assertEqual(saved['state'],'interrupted');self.assertEqual(saved['steps'][0]['state'],'done');self.exp.save(saved,force=True)
        messages=self.exp.messages();self.assertEqual(messages['unread'],1);self.assertEqual(len(messages['messages']),1);self.exp.read();self.assertEqual(self.exp.messages()['unread'],0)
    def test_waiting_message_becomes_read_after_resolution_and_terminal_once(self):
        job=self.job('waiting');self.exp.save(job);self.exp.save(job);self.assertEqual(self.exp.messages()['unread'],1)
        job['state']='done';job['finished_at']=datetime.now().astimezone().isoformat();self.exp.save(job);self.exp.save(job)
        data=self.exp.messages();self.assertEqual(data['unread'],1);self.assertEqual(len(data['messages']),2);self.assertEqual(data['summary']['done'],1)
    def tools(self):
        store=self.hub.context();store.recovery_chain='chain-1';return OfficeTools(store,lambda *a:None)
    def test_exact_successful_write_is_reused_and_changed_output_is_refused(self):
        tools=self.tools();write=self.exp.receipt(tools,tools.create_document);first=write('合成文档','合成标题','仅测试',format='md')
        tools2=self.tools();second=self.exp.receipt(tools2,tools2.create_document)('合成文档','合成标题','仅测试','md')
        self.assertEqual(first['id'],second['id']);self.assertEqual(len(list(tools.output.glob('*.md'))),1)
        (tools.output/first['name']).write_text('changed',encoding='utf-8')
        with self.assertRaisesRegex(ValueError,'变化'):self.exp.receipt(self.tools(),tools.create_document)('合成文档','合成标题','仅测试','md')
    def test_unknown_write_is_not_blindly_replayed(self):
        calls=[]
        def create_document(name):calls.append(name);raise RuntimeError('synthetic interruption')
        safe=self.exp.receipt(self.tools(),create_document)
        with self.assertRaises(RuntimeError):safe('合成')
        with self.assertRaisesRegex(ValueError,'未确认'):safe('合成')
        self.assertEqual(calls,['合成'])
    def test_quiet_hours_cross_midnight_and_settings_validation(self):
        c={'quiet_hours':True,'quiet_start':'22:00','quiet_end':'08:00'}
        self.assertTrue(quiet(c,datetime(2099,1,1,23)));self.assertTrue(quiet(c,datetime(2099,1,1,7)));self.assertFalse(quiet(c,datetime(2099,1,1,12)));self.assertTrue(quiet({'do_not_disturb':True}))
        with self.assertRaises(ValueError):self.store.save({'quiet_start':'25:00'})
        with self.assertRaises(ValueError):self.store.save({'do_not_disturb':'true'})
    def test_continuation_refuses_changed_source_before_starting_a_new_job(self):
        server=Server(Store(self.temp.name))
        try:
            tools=OfficeTools(server.hub.context(),lambda *a:None);ref=tools.read_document('示例会议记录.md')['source'];task=self.job('cancelled');task['sources']=[ref];server.experience.save(task,force=True)
            (tools.root/'示例会议记录.md').write_text('合成内容已更正',encoding='utf-8')
            with self.assertRaisesRegex(ValueError,'资料已变化'):server.continue_job(task['id'])
            self.assertFalse(server.jobs)
        finally:server.server_close()
    def test_real_model_tool_continuation_reuses_file_and_applies_supplement(self):
        model=ThreadingHTTPServer(('127.0.0.1',0),ScriptedModel);model.count=0;model.payloads=[];model.delay=.03;model.chunk_delay=.025
        args={'name':'续办合成文档','title':'虚构标题','content':'虚构内容','format':'md'};model.script=[('create_document',args)]
        threading.Thread(target=model.serve_forever,daemon=True).start();self.store.save({'base_url':f'http://127.0.0.1:{model.server_port}','model':'synthetic','api_key':'SYNTHETIC-RESUME','use_model':True})
        # Use another isolated store DB connection owned by the actual server.
        server=Server(Store(self.temp.name))
        try:
            jid=server.start_job({'question':'生成合成文档并给结论'})['id']
            for _ in range(300):
                job=server.jobs[jid]
                if job.get('artifacts') and job['state']=='streaming':break
                time.sleep(.02)
            else:self.fail('No streamed checkpoint after successful write')
            aid=job['artifacts'][0]['id'];server.pause_job(jid);server.job_workers[jid].join(5);self.assertEqual(server.jobs[jid]['state'],'cancelled');self.assertTrue(server.jobs[jid]['paused'])
            model.count=0;model.script=[('create_document',args),('calculate',{'expression':'12.5+7.25'})]
            resumed=server.continue_job(jid,'只核对这个月的虚构数据')['id']
            for _ in range(500):
                for approval in server.hub.pending():server.hub.decide(approval['id'],True)
                if server.jobs[resumed]['state'] in ('done','error','cancelled'):break
                time.sleep(.02)
            result=server.jobs[resumed];self.assertEqual(result['state'],'done',result);self.assertEqual(result['answer']['artifacts'][0]['id'],aid);self.assertEqual(len(list((Path(self.temp.name)/'outputs').glob('*.md'))),1)
            self.assertIn('这个月',result['question']);self.assertTrue(any('复用已完成' in s['label'] for s in result['answer']['steps']))
            session=server.hub.session();server.hub.update_session(session['id'],workspace=session['workspace'])
            with self.assertRaisesRegex(ValueError,'范围'):server.continue_job(jid)
        finally:server.server_close();model.shutdown();model.server_close()
    def test_local_chinese_speech_wave_and_cancel(self):
        speech=Speech(Path(self.temp.name)/'speech',Path(__file__).with_name('speech_worker.ps1'))
        try:
            job=speech.start('小隆在这里，合成测试完成。')
            for _ in range(250):
                status=speech.status(job['id'])
                if status['state']!='generating':break
                time.sleep(.1)
            self.assertEqual(status['state'],'ready',status)
            with wave.open(io.BytesIO(speech.audio(job['id']))) as audio:self.assertGreater(audio.getnframes(),1000)
            speech.stop();self.assertEqual(speech.status(job['id'])['state'],'cancelled')
            job=speech.start('停止测试。'*100);speech.stop();self.assertEqual(speech.status(job['id'])['state'],'cancelled')
        finally:speech.stop()

if __name__=='__main__':unittest.main()
