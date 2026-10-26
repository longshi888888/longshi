from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit
import json
import os
import secrets
import sys
import threading
import uuid
from datetime import datetime
from agent import Agent,completion
from storage import Store,RUNTIME

ASSETS=Path(getattr(sys,'_MEIPASS',Path(__file__).parent))
TOOLS_ROOT=Path.home()/'.codex/tools'
BUNDLE=Path(sys.executable).parent if hasattr(sys,'_MEIPASS') else TOOLS_ROOT/'xiaolong-agent-20261026/dist/小隆公司问答体验'
THREE=BUNDLE/'three' if (BUNDLE/'three').is_dir() else TOOLS_ROOT/'longshi-assistant-prototype/vendor/three-0.186.1/package'
MODEL=BUNDLE/'private-model/xiaolong-parts.glb' if (BUNDLE/'private-model/xiaolong-parts.glb').is_file() else TOOLS_ROOT/'longshi-assistant-prototype/private-archive-20261024-v5-public-audit/original/model-assets/xiaolong-parts.glb'
VERSION='0.7.0-enterprise-preview'

class Server(ThreadingHTTPServer):
    daemon_threads=True
    def __init__(self,store=None):
        super().__init__(('127.0.0.1',0),Handler);self.prefix='/'+secrets.token_urlsafe(24)+'/'
        self.origin=f'http://127.0.0.1:{self.server_port}';self.base=self.origin+self.prefix
        self.store=store or Store();self.agent=Agent();self.jobs={};self.lock=threading.RLock();self.active=None;self.panel_request=0
    def start_job(self,payload):
        if set(payload)-{'question','mode'}:raise ValueError('未知请求字段')
        q=payload.get('question','');mode=payload.get('mode','business')
        if not isinstance(q,str) or not q.strip() or len(q)>2000:raise ValueError('请输入1至2000个字')
        if mode not in ('business','chat'):raise ValueError('未知模式')
        with self.lock:
            if self.active and self.jobs[self.active]['state'] not in ('done','error'):raise ValueError('正在处理上一条问题，请稍等')
            jid=uuid.uuid4().hex;job={'id':jid,'state':'queued','message':'收到问题','question':q,'mode':mode}
            self.jobs[jid]=job;self.active=jid
            # Keep only bounded per-session jobs; history is separately bounded.
            if len(self.jobs)>30:del self.jobs[next(iter(self.jobs))]
        def stage(state,message):
            with self.lock:job.update(state=state,message=message)
        def work():
            try:
                with self.store.lock:config=dict(self.store.config);key=self.store.key;history=list(self.store.history)
                result=self.agent.run(q,mode,config,key,history,stage)
                item={'question':q,'mode':mode,'answer':result,'time':datetime.now().astimezone().isoformat(timespec='seconds')}
                self.store.append(item)
                with self.lock:job.update(state='done',message='证据不足' if result['kind']=='missing' else '查好了',answer=result)
            except Exception as error:
                message=str(error) if isinstance(error,ValueError) else '本次处理未完成，请重试'
                # Do not echo model response bodies, credential headers or stack traces.
                with self.lock:job.update(state='error',message=message)
        threading.Thread(target=work,daemon=True).start();return {'id':jid}

class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def send(self,status,data,mime='application/json; charset=utf-8'):
        raw=json.dumps(data,ensure_ascii=False).encode() if mime.startswith('application/json') else data
        self.send_response(status);self.send_header('Content-Type',mime);self.send_header('Content-Length',str(len(raw)))
        self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('Referrer-Policy','no-referrer')
        self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; connect-src 'self' blob:; frame-ancestors 'none'; base-uri 'none'; form-action 'none'")
        self.end_headers();self.wfile.write(raw)
    def route(self):
        if self.headers.get('Host')!=urlsplit(self.server.origin).netloc:return None
        if self.headers.get('Origin') not in (None,self.server.origin):return None
        path=urlsplit(self.path).path
        return path[len(self.server.prefix):] if path.startswith(self.server.prefix) else None
    def do_GET(self):
        path=self.route()
        if path is None:return self.send(403,{'error':'无效的本机会话'})
        files={'pet.html':'text/html; charset=utf-8','panel.html':'text/html; charset=utf-8',
               'pet.js':'text/javascript; charset=utf-8','panel.js':'text/javascript; charset=utf-8'}
        if path in files:return self.send(200,(ASSETS/path).read_bytes(),files[path])
        vendor={'vendor/three.module.js':'build/three.module.js','vendor/three.core.js':'build/three.core.js',
            'vendor/GLTFLoader.js':'examples/jsm/loaders/GLTFLoader.js','vendor/OrbitControls.js':'examples/jsm/controls/OrbitControls.js',
            'vendor/RoomEnvironment.js':'examples/jsm/environments/RoomEnvironment.js',
            'utils/BufferGeometryUtils.js':'examples/jsm/utils/BufferGeometryUtils.js','utils/SkeletonUtils.js':'examples/jsm/utils/SkeletonUtils.js'}
        if path in vendor:return self.send(200,(THREE/vendor[path]).read_bytes(),'text/javascript; charset=utf-8')
        if path=='model.glb':
            return self.send(200,MODEL.read_bytes(),'model/gltf-binary') if MODEL.is_file() else self.send(404,{'error':'私有角色素材不在本机'})
        if path=='status':
            with self.server.lock:job=dict(self.server.jobs.get(self.server.active,{}))
            return self.send(200,{'version':VERSION,'settings':self.server.store.public(),'active':job,'synthetic':True,'panel_request':self.server.panel_request})
        if path=='history':return self.send(200,{'history':self.server.store.history})
        if path=='source':
            provider=self.server.agent.provider;raw=provider.file.read_bytes()
            import hashlib
            if hashlib.sha256(raw).hexdigest()!=provider.digest:return self.send(409,{'error':'合成来源已变化，请重启后再读'})
            return self.send(200,{'name':'demo-data.json','text':raw.decode('utf-8'),'sha256':provider.digest,'synthetic':True})
        if path.startswith('job/'):
            with self.server.lock:job=self.server.jobs.get(path.split('/')[-1])
            return self.send(200,job) if job else self.send(404,{'error':'本会话没有这个任务'})
        return self.send(404,{'error':'没有这个资源'})
    def do_POST(self):
        path=self.route()
        if path is None:return self.send(403,{'error':'无效的本机会话'})
        try:
            size=int(self.headers.get('Content-Length','0'))
            if not 0<size<=16384:raise ValueError('请求长度不合法')
            data=json.loads(self.rfile.read(size))
            if not isinstance(data,dict):raise ValueError('请求必须是对象')
            if path=='ask':return self.send(200,self.server.start_job(data))
            if path=='settings':return self.send(200,self.server.store.save(data))
            if path=='clear':self.server.store.clear();return self.send(200,{'ok':True})
            if path=='open-panel':
                self.server.panel_request+=1;return self.send(200,{'ok':True})
            if path=='check-model':
                store=self.server.store
                if not store.key:raise ValueError('请先保存自己的API密钥')
                result=completion(store.config,store.key,[{'role':'user','content':'你好，请只回复：连接成功。'}])
                if not isinstance(result.get('content'),str):raise ValueError('API响应没有文字内容')
                return self.send(200,{'ok':True,'message':'API请求已返回；业务工具路由还需实际提问验证'})
            if path=='quit':
                self.send(200,{'ok':True});threading.Thread(target=self.server.shutdown,daemon=True).start();return
            return self.send(404,{'error':'没有这个操作'})
        except (ValueError,TypeError,json.JSONDecodeError) as error:return self.send(400,{'error':str(error)[:250]})
        except Exception:return self.send(500,{'error':'处理未完成，没有更改业务数据'})

def main():
    import argparse,subprocess
    p=argparse.ArgumentParser();p.add_argument('--no-window',action='store_true');args=p.parse_args()
    runtime=RUNTIME;runtime.mkdir(parents=True,exist_ok=True)
    pointer=runtime/'current.json'
    if not args.no_window and pointer.is_file():
        reuse_stage='read-local-session'
        try:
            import urllib.request
            old=json.loads(pointer.read_text(encoding='utf-8'))
            if not old['url'].startswith('http://127.0.0.1:'):raise ValueError('Invalid local session')
            reuse_stage='read-status'
            with urllib.request.urlopen(old['url']+'status',timeout=2) as response:status=json.load(response)
            if status.get('version')==VERSION:
                reuse_stage='open-existing-panel'
                urllib.request.urlopen(urllib.request.Request(old['url']+'open-panel',data=b'{}',headers={'Content-Type':'application/json'}),timeout=2).read();return
        except (OSError,ValueError,KeyError) as error:
            (runtime/'last-reuse-error.json').write_text(json.dumps({'stage':reuse_stage,'type':type(error).__name__,'code':getattr(error,'code',None),'reason':str(getattr(error,'reason',''))[:250]}),encoding='utf-8')
            import traceback
            (runtime/'reuse-diagnostic.txt').write_text(traceback.format_exc(),encoding='utf-8')
    server=Server()
    pointer.write_text(json.dumps({'url':server.base,'pid':os.getpid(),'version':VERSION}),encoding='utf-8')
    process=None
    if not args.no_window:
        electron=BUNDLE/'desktop-runtime/electron.exe'
        if not electron.is_file():electron=TOOLS_ROOT/'xiaolong-agent-20261026/vendor/electron/electron.exe'
        if not electron.is_file():raise ValueError('桌面运行组件未准备完成')
        env=dict(os.environ);env.pop('ELECTRON_RUN_AS_NODE',None)
        process=subprocess.Popen([str(electron),str(ASSETS/'desktop/main.cjs'),'--xl-url='+server.base],env=env,
            creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        def watch():process.wait();server.shutdown()
        threading.Thread(target=watch,daemon=True).start()
    try:server.serve_forever(poll_interval=.2)
    finally:
        server.server_close()
        if process and process.poll() is None:process.terminate()
        try:
            if json.loads(pointer.read_text())['pid']==os.getpid():pointer.unlink()
        except (OSError,ValueError,KeyError):pass

if __name__=='__main__':main()
