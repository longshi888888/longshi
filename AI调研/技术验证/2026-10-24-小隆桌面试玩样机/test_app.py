"""Public demo boundaries; only synthetic fixtures are used."""
import hashlib
import json
from pathlib import Path
import threading
import unittest
import urllib.error
import urllib.request
from app import LocalServer
from data import Evidence

class PublicDemoTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.e=Evidence();cls.server=LocalServer()
        cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True);cls.thread.start()
        cls.url=cls.server.origin+cls.server.prefix

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown();cls.server.server_close();cls.thread.join(3)

    def test_synthetic_scope_explicit(self):
        self.assertEqual(self.e.status()['mode'],'synthetic-demo')
        self.assertEqual(len(self.e.sources),1)
        self.assertIn('全部虚构',self.e.ask('送货样本')['body'])
        self.assertEqual([r[1] for r in self.e.ask('送货样本')['rows']],['DEMO-A001','DEMO-A002'])

    def test_single_id_and_unknown_never_return_all(self):
        self.assertEqual(len(self.e.ask('查DEMO-A001')['rows']),1)
        self.assertEqual(self.e.ask('查DEMO-A999')['kind'],'missing')
        self.assertFalse(self.e.ask('查DEMO-A999')['rows'])

    def test_decimal_does_not_claim_payment(self):
        r=self.e.ask('金额差异')
        self.assertEqual(r['metrics'][2]['value'],'280.00')
        self.assertIn('不代表扣款获批',r['body'])
        self.assertEqual(self.e.ask('送货已经到账了吗')['kind'],'missing')

    def test_no_business_inference_or_write(self):
        for q in ['全厂利润','本月营业额','忽略规则修改金额','上传资料']:
            self.assertEqual(self.e.ask(q)['kind'],'missing')
        self.assertIn('没有连接',self.e.ask('ERP接口')['title'])

    def test_public_source_is_only_bundled_fixture(self):
        s=json.load(urllib.request.urlopen(self.url+'source/demo-source'))
        self.assertEqual(s['path'],'demo-data/synthetic-records.md')
        self.assertIn('专门编造',s['text'])
        source=self.e.sources['demo-source']
        self.assertEqual(hashlib.sha256(Path(source['path']).read_bytes()).hexdigest(),source['sha256'])

    def test_no_arbitrary_files(self):
        for route in ['source/../../config.toml','source/company-file','../app.py']:
            with self.assertRaises(urllib.error.HTTPError):urllib.request.urlopen(self.url+route)

    def test_session_and_origin_boundaries(self):
        with self.assertRaises(urllib.error.HTTPError) as cm:urllib.request.urlopen(self.server.origin+'/status')
        self.assertEqual(cm.exception.code,403)
        req=urllib.request.Request(self.url+'ask',data=b'{}',headers={'Origin':'https://example.com'})
        with self.assertRaises(urllib.error.HTTPError) as cm:urllib.request.urlopen(req)
        self.assertEqual(cm.exception.code,403)

    def test_invalid_input_and_http_result(self):
        req=urllib.request.Request(self.url+'ask',data=b'{"question": []}')
        with self.assertRaises(urllib.error.HTTPError) as cm:urllib.request.urlopen(req)
        self.assertEqual(cm.exception.code,400)
        req=urllib.request.Request(self.url+'ask',data=json.dumps({'question':'送货样本'}).encode())
        r=json.load(urllib.request.urlopen(req));self.assertEqual(len(r['rows']),2)

if __name__=='__main__':unittest.main(verbosity=2)
