import json
import tempfile
import threading
import unittest
import urllib.request
import urllib.error
from pathlib import Path
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from agent import Agent
from provider import DemoProvider
from server import Server
from storage import Store,RUNTIME

class ModelStub(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def do_POST(self):
        self.server.last=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        message={'content':'模型捏造数字999999，这段文字必须被业务模式丢弃。',
                 'tool_calls':[{'id':'stub','type':'function','function':{'name':self.server.tool,'arguments':json.dumps(self.server.arguments)}}]}
        raw=json.dumps({'choices':[{'message':message}]}).encode();self.send_response(200);self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)

class AgentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        RUNTIME.mkdir(parents=True,exist_ok=True)
        cls.temp=tempfile.TemporaryDirectory(prefix='synthetic-test-',dir=RUNTIME)
        cls.model=ThreadingHTTPServer(('127.0.0.1',0),ModelStub);cls.model.tool='reconciliation_query';cls.model.arguments={}
        cls.model_thread=threading.Thread(target=cls.model.serve_forever,daemon=True);cls.model_thread.start()
        cls.config={'base_url':f'http://127.0.0.1:{cls.model.server_port}','model':'synthetic-stub','use_model':True}
        cls.agent=Agent();cls.server=Server(Store(Path(cls.temp.name)/'server'))
        cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True);cls.thread.start();cls.url=cls.server.base
    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown();cls.server.server_close();cls.thread.join(3)
        cls.model.shutdown();cls.model.server_close();cls.model_thread.join(3);cls.temp.cleanup()
    def run_agent(self,q,config=None,key=''):
        return self.agent.run(q,'business',config or {},key,[],lambda *args:None)
    def test_demo_calculation_and_missing_payment(self):
        r=self.run_agent('300和280的金额差异');self.assertEqual(r['metrics'][2]['value'],'280.00');self.assertTrue(r['sources']);self.assertTrue(r['synthetic'])
        self.assertEqual(self.run_agent('已到账了吗')['kind'],'missing')
    def test_id_filter_and_unknown(self):
        self.assertEqual(len(self.run_agent('查询DEMO-A001')['rows']),1)
        self.assertFalse(self.run_agent('查DEMO-A999')['rows'])
    def test_unsupported_and_writes(self):
        for q in ['全厂利润','删除数据','订单实时进度']:self.assertEqual(self.run_agent(q)['kind'],'missing')
    def test_tool_allowlist(self):
        with self.assertRaises(ValueError):DemoProvider().execute('run_sql',{'sql':'select *'})
        with self.assertRaises(ValueError):DemoProvider().execute('delivery_query',{'path':'outside'})
    def test_model_routes_but_cannot_generate_business_numbers(self):
        self.model.tool='reconciliation_query';self.model.arguments={}
        r=self.run_agent('金额为什么不同',self.config,'synthetic-test-token')
        self.assertEqual(r['metrics'][2]['value'],'280.00');self.assertNotIn('999999',json.dumps(r))
        self.assertEqual(self.model.last['tool_choice'],'required')
    def test_model_cannot_change_an_explicit_id(self):
        self.model.tool='delivery_query';self.model.arguments={'delivery_no':''}
        with self.assertRaises(ValueError):self.run_agent('查DEMO-A999',self.config,'synthetic-test-token')
    def test_key_encryption_and_destination_binding(self):
        store=Store(Path(self.temp.name)/'key');key='synthetic-local-test-credential'
        store.save(dict(self.config,api_key=key));self.assertNotIn(key,json.dumps(store.public()))
        self.assertNotIn(key.encode(),(store.folder/'credential.bin').read_bytes())
        self.assertEqual(Store(store.folder).key,key)
        with self.assertRaises(ValueError):store.save({'base_url':'https://example.com'})
        self.assertEqual(Store(store.folder).key,key)
        store.save({'clear_key':True,'use_model':False});self.assertFalse(store.key)
    def test_missing_key_does_not_claim_live_model(self):
        r=self.run_agent('送货样本');self.assertIn('未调用模型',r['engine'])
    def test_http_session_and_origin(self):
        with self.assertRaises(urllib.error.HTTPError):urllib.request.urlopen(self.server.origin+'/status')
        req=urllib.request.Request(self.url+'ask',data=b'{}',headers={'Origin':'https://example.com'})
        with self.assertRaises(urllib.error.HTTPError) as result:urllib.request.urlopen(req)
        self.assertEqual(result.exception.code,403)
    def test_no_arbitrary_source(self):
        with self.assertRaises(urllib.error.HTTPError):urllib.request.urlopen(self.url+'source/../../config.toml')
        source=json.load(urllib.request.urlopen(self.url+'source'));self.assertTrue(source['synthetic'])
        self.assertNotIn('Users',source['text'])
    def test_history_and_no_key_readback(self):
        store=Store(Path(self.temp.name)/'history');store.append({'mode':'chat','question':'合成问题','answer':{'body':'合成回复'}})
        self.assertEqual(len(Store(store.folder).history),1);store.clear();self.assertEqual(Store(store.folder).history,[])
        status=json.load(urllib.request.urlopen(self.url+'status'));self.assertNotIn('api_key',json.dumps(status))

if __name__=='__main__':unittest.main(verbosity=2)
