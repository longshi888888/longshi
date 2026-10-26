from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit,parse_qs,quote
import json
import os
import secrets
import sys
import threading
import uuid
import time
from datetime import datetime
from office_agent import OfficeAgent
from business_agent import completion
from office_tools import OfficeTools
from storage import Store,RUNTIME
from hub import Hub,TERMINAL
from voice import Voice
from experience import Experience,quiet
from speech import Speech

ASSETS=Path(getattr(sys,'_MEIPASS',Path(__file__).parent))
TOOLS_ROOT=Path.home()/'.codex/tools'
BUNDLE=Path(sys.executable).parent if hasattr(sys,'_MEIPASS') else TOOLS_ROOT/'xiaolong-office-20261026/dist/小隆办公助手'
THREE=BUNDLE/'three' if (BUNDLE/'three').is_dir() else TOOLS_ROOT/'longshi-assistant-prototype/vendor/three-0.186.1/package'
MODEL=BUNDLE/'private-model/xiaolong-parts.glb' if (BUNDLE/'private-model/xiaolong-parts.glb').is_file() else TOOLS_ROOT/'longshi-assistant-prototype/private-archive-20261024-v5-public-audit/original/model-assets/xiaolong-parts.glb'
VERSION='1.2.0-continuous-office-preview'

class Server(ThreadingHTTPServer):
    daemon_threads=True
    def __init__(self,store=None):
        super().__init__(('127.0.0.1',0),Handler);self.prefix='/'+secrets.token_urlsafe(24)+'/'
        self.origin=f'http://127.0.0.1:{self.server_port}';self.base=self.origin+self.prefix
        self.store=store or Store();self.agent=OfficeAgent();self.jobs={};self.controls={};self.lock=threading.RLock();self.changed=threading.Condition(self.lock);self.active=None;self.panel_request=0;self.desktop_attached=False
        self.hub=Hub(self.store);self.experience=Experience(self.hub);self.voice=Voice(BUNDLE/'voice-model');self.speech=Speech(self.store.folder/'speech',ASSETS/'speech_worker.ps1');self.stopping=threading.Event();self.workers=[];self.job_workers={}
        threading.Thread(target=self.scheduler,daemon=True).start()
    def scheduler(self):
        while not self.stopping.wait(2):
            try:
                for item in self.hub.due():
                    try:
                        job=self.start_job({'question':item['prompt'],'session_id':item['session_id'],'schedule_id':item['id']})
                    except ValueError:continue
            except (OSError,ValueError):continue
    def server_close(self):
        self.stopping.set()
        self.speech.stop()
        for event in self.controls.values():event.set()
        for worker in self.workers:worker.join(2)
        self.hub.db.close();super().server_close()
    def start_job(self,payload):
        if set(payload)-{'question','mode','session_id','schedule_id','resume_id'}:raise ValueError('未知请求字段')
        q=payload.get('question','');mode=payload.get('mode','office')
        if not isinstance(q,str) or not q.strip() or len(q)>6000:raise ValueError('请输入1至6000个字')
        if mode not in ('business','chat','office'):raise ValueError('未知模式')
        context=self.hub.context(payload.get('session_id'));sid=context.session_id
        previous=self.experience.task(payload['resume_id']) if payload.get('resume_id') else None
        if previous:
            if previous['session_id']!=sid or previous.get('workspace_id')!=context.config['workspace_id']:raise ValueError('原会话或资料范围已改变，请核对后重新交代任务')
            if previous['state'] not in ('error','cancelled','interrupted'):raise ValueError('只能继续已暂停、停止、失败或中断的任务')
            context.resume_snapshot=previous;context.config['plan_mode']=True
        if payload.get('schedule_id') and self.hub.schedule(payload['schedule_id'])['session_id']!=sid:raise ValueError('定时任务会话不匹配')
        if not Path(context.config['workspace']).is_dir():raise ValueError('此会话资料目录不存在，请先更换目录')
        with self.lock:
            if any(j['session_id']==sid and j['state'] not in TERMINAL for j in self.jobs.values()):raise ValueError('此会话正在处理上一条任务，请稍等、停止或新建会话')
            if sum(j['state'] not in TERMINAL for j in self.jobs.values())>=3:raise ValueError('同时最多运行3个会话任务')
            jid=uuid.uuid4().hex;job={'id':jid,'state':'queued','message':'收到问题','question':q,'mode':mode,'session_id':sid,'workspace_id':context.config['workspace_id'],'revision':0,'stream_segments':[],'resume_id':payload.get('resume_id'),'recovery_chain':previous.get('recovery_chain',previous['id']) if previous else jid}
            context.job_id=jid
            context.experience=self.experience;context.recovery_chain=job['recovery_chain']
            self.jobs[jid]=job;self.controls[jid]=threading.Event();self.active=jid
            # Keep only bounded per-session jobs; history is separately bounded.
            if len(self.jobs)>30:
                oldest=next((key for key,value in self.jobs.items() if value['state'] in TERMINAL),None)
                if oldest:del self.jobs[oldest];self.controls.pop(oldest,None)
            self.experience.save(job,force=True)
        def stage(state,message,details=None):
            with self.lock:
                if job['state'] in ('done','error','cancelled'):return
                if self.controls[jid].is_set():job.update(state='stopping',message='正在停止后续处理…')
                else:job.update(state=state,message=message)
                if details:
                    job.update(details)
                    if 'stream_text' in details:
                        part={'round':details['stream_round'],'text':details['stream_text']}
                        if job['stream_segments'] and job['stream_segments'][-1]['round']==part['round']:job['stream_segments'][-1]=part
                        else:job['stream_segments'].append(part)
                job['revision']+=1;self.experience.save(job);self.changed.notify_all()
        def work():
            try:
                self.hub.record_run(jid,sid,q,'running')
                config=dict(context.config);key=context.key;history=list(context.history)
                result=self.agent.run(q,mode,config,key,history,stage,context,self.controls[jid])
                if result['kind'] in ('error','cancelled') and job.get('stream_text'):result['partial_body']=job['stream_text']
                if job.get('paused') and result['kind']=='cancelled':result.update(title='任务已暂停',body='已暂停后续处理。已完成步骤和成果已保存，可以补充要求后继续。')
                result['job_id']=jid;result['resumable']=result['kind'] in ('error','cancelled')
                item={'question':q,'mode':mode,'answer':result,'job_id':jid,'time':datetime.now().astimezone().isoformat(timespec='seconds')}
                self.hub.append(sid,item)
                state='cancelled' if result['kind']=='cancelled' else 'error' if result['kind']=='error' else 'done'
                with self.lock:
                    job.update(state=state,message=('已暂停' if job.get('paused') else '已停止') if state=='cancelled' else '没有全部完成' if state=='error' else '处理好了',answer=result,finished_at=datetime.now().astimezone().isoformat(timespec='seconds'))
                    job['revision']+=1;self.experience.save(job,force=True);self.changed.notify_all()
                self.hub.record_run(jid,sid,q,state);self.hub.schedule_finished(jid,state)
            except Exception as error:
                message=str(error) if isinstance(error,ValueError) else '本次处理未完成，请重试'
                # Do not echo model response bodies, credential headers or stack traces.
                with self.lock:
                    job.update(state='error',message=message,answer={'title':'这次没有完成','body':message,'kind':'error','partial_body':job.get('stream_text',''),'job_id':jid,'resumable':True,'steps':job.get('steps',[]),'artifacts':job.get('artifacts',[])},finished_at=datetime.now().astimezone().isoformat(timespec='seconds'))
                    job['revision']+=1;self.experience.save(job,force=True);self.changed.notify_all()
                self.hub.append(sid,{'question':q,'mode':mode,'answer':job['answer'],'time':datetime.now().astimezone().isoformat(timespec='seconds')})
                self.hub.record_run(jid,sid,q,'error');self.hub.schedule_finished(jid,'error')
            finally:self.hub.expire(jid)
        if payload.get('schedule_id'):self.hub.schedule_started(payload['schedule_id'],jid)
        worker=threading.Thread(target=work,daemon=True);self.workers.append(worker);self.job_workers[jid]=worker;worker.start();return {'id':jid,'session_id':sid}

    def pause_job(self,jid):
        with self.lock:
            job=self.jobs.get(jid)
            if not job:raise ValueError('任务不在运行，可从任务记录继续')
            if job['state'] not in TERMINAL:
                job.update(paused=True,state='stopping',message='正在暂停并保存已完成步骤…');self.controls[jid].set();job['revision']+=1;self.experience.save(job,force=True);self.changed.notify_all()
        return {'ok':True}

    def continue_job(self,jid,supplement=''):
        if not isinstance(supplement,str) or len(supplement)>2000:raise ValueError('补充要求最多2000字')
        if jid in self.jobs and self.jobs[jid]['state'] not in TERMINAL:self.pause_job(jid)
        worker=self.job_workers.get(jid)
        if worker:
            worker.join(8)
            if worker.is_alive():raise ValueError('正在等待当前操作安全结束，请稍后点继续；不会同时重复执行')
        task=self.experience.task(jid)
        # A continuation must not silently apply old results to changed input files.
        old=task.get('answer') or task;tools=OfficeTools(self.hub.context(task['session_id']),lambda *args:None)
        import hashlib
        for source in old.get('sources',[]):
            if source.get('workspace_id') and not source.get('artifact_id'):
                try:
                    path=tools.path(source['file'])
                    if source['workspace_id']!=tools.store.config['workspace_id'] or not path.is_file() or path.stat().st_size>20_000_000 or hashlib.sha256(path.read_bytes()).hexdigest()!=source['sha256']:raise ValueError('资料已变化')
                except (OSError,KeyError,ValueError):raise ValueError('原任务资料已变化或不可读取，请核对后重新交代任务，不能套用旧结果') from None
        question=(task.get('original_question') or task['question']).split('\n\n补充要求：')[0]
        # Keep previous supplements when continuing the same chain.
        question=task['question']+('\n\n补充要求：'+supplement.strip() if supplement.strip() else '')
        if len(question)>6000:raise ValueError('累计任务文字过长，请新建一条精简任务')
        return self.start_job({'question':question,'session_id':task['session_id'],'mode':task['mode'],'resume_id':jid})

class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def send(self,status,data,mime='application/json; charset=utf-8',filename=None):
        raw=json.dumps(data,ensure_ascii=False).encode() if mime.startswith('application/json') and not isinstance(data,(bytes,bytearray)) else data
        self.send_response(status);self.send_header('Content-Type',mime);self.send_header('Content-Length',str(len(raw)))
        if filename:self.send_header('Content-Disposition',"attachment; filename*=UTF-8''"+quote(filename))
        self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('Referrer-Policy','no-referrer')
        self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; connect-src 'self' blob:; frame-ancestors 'none'; base-uri 'none'; form-action 'none'")
        self.end_headers();self.wfile.write(raw)
    def artifact(self,aid):
        import re,hashlib
        if not re.fullmatch('[a-f0-9]{32}',aid):raise ValueError('成果编号不合法')
        folder=self.server.store.folder/'outputs';meta=json.loads((folder/(aid+'.json')).read_text(encoding='utf-8'))
        if not isinstance(meta,dict) or not isinstance(meta.get('name'),str) or not isinstance(meta.get('sha256'),str):raise ValueError('成果清单不完整')
        file=(folder/meta['name']).resolve()
        if not file.is_relative_to(folder.resolve()) or file.suffix not in ('.docx','.xlsx','.md','.txt','.csv','.json'):raise ValueError('成果路径不合法')
        if hashlib.sha256(file.read_bytes()).hexdigest()!=meta['sha256']:raise ValueError('成果文件已变化，未自动打开')
        return file,meta
    def route(self):
        if self.headers.get('Host')!=urlsplit(self.server.origin).netloc:return None
        if self.headers.get('Origin') not in (None,self.server.origin):return None
        path=urlsplit(self.path).path
        return path[len(self.server.prefix):] if path.startswith(self.server.prefix) else None
    def do_GET(self):
        path=self.route()
        if path is None:return self.send(403,{'error':'无效的本机会话'})
        from suite_api import handle_get
        if handle_get(self,path):return
        if path.startswith('events/'):
            jid=path.split('/')[-1]
            with self.server.lock:
                if jid not in self.server.jobs:return self.send(404,{'error':'本会话没有这个任务'})
            self.send_response(200);self.send_header('Content-Type','text/event-stream; charset=utf-8');self.send_header('Cache-Control','no-cache, no-transform');self.send_header('X-Content-Type-Options','nosniff');self.send_header('Connection','close');self.end_headers()
            revision=-1
            try:
                while True:
                    with self.server.changed:
                        job=self.server.jobs.get(jid)
                        if job is None:return
                        if job['revision']==revision:
                            self.server.changed.wait(timeout=10)
                            job=self.server.jobs.get(jid)
                            if job is None:return
                        snapshot=json.dumps(job,ensure_ascii=False);revision=job['revision'];terminal=job['state'] in ('done','error','cancelled')
                    self.wfile.write(('id: '+str(revision)+'\ndata: '+snapshot+'\n\n').encode('utf-8'));self.wfile.flush()
                    if terminal:return
                    time.sleep(.04)
            except (BrokenPipeError,ConnectionResetError,OSError):return
        files={'pet.html':'text/html; charset=utf-8','panel.html':'text/html; charset=utf-8',
                'pet.js':'text/javascript; charset=utf-8','panel.js':'text/javascript; charset=utf-8','panel.css':'text/css; charset=utf-8','suite.js':'text/javascript; charset=utf-8','suite.css':'text/css; charset=utf-8','quick.html':'text/html; charset=utf-8','quick.js':'text/javascript; charset=utf-8','experience.js':'text/javascript; charset=utf-8','experience.css':'text/css; charset=utf-8','speech.js':'text/javascript; charset=utf-8','hat.html':'text/html; charset=utf-8','hat.js':'text/javascript; charset=utf-8'}
        if path in files:return self.send(200,(ASSETS/path).read_bytes(),files[path])
        if path=='vendor/markdown-it.min.js':return self.send(200,(BUNDLE/'ui-vendor/markdown-it.min.js').read_bytes(),'text/javascript; charset=utf-8')
        vendor={'vendor/three.module.js':'build/three.module.js','vendor/three.core.js':'build/three.core.js',
            'vendor/GLTFLoader.js':'examples/jsm/loaders/GLTFLoader.js','vendor/OrbitControls.js':'examples/jsm/controls/OrbitControls.js',
            'vendor/RoomEnvironment.js':'examples/jsm/environments/RoomEnvironment.js',
            'utils/BufferGeometryUtils.js':'examples/jsm/utils/BufferGeometryUtils.js','utils/SkeletonUtils.js':'examples/jsm/utils/SkeletonUtils.js'}
        if path in vendor:return self.send(200,(THREE/vendor[path]).read_bytes(),'text/javascript; charset=utf-8')
        if path=='model.glb':
            return self.send(200,MODEL.read_bytes(),'model/gltf-binary') if MODEL.is_file() else self.send(404,{'error':'私有角色素材不在本机'})
        if path=='status':
            with self.server.lock:
                running=[j for j in self.server.jobs.values() if j['state'] not in TERMINAL]
                job=dict(max(running,key=lambda j:2 if j['state']=='waiting' else 1) if running else self.server.jobs.get(self.server.active,{}))
            return self.send(200,{'version':VERSION,'settings':self.server.store.public(),'quiet':quiet(self.server.store.config),'active':job,'jobs':[dict(j) for j in self.server.jobs.values()],'session_id':self.server.store.config['active_session'],'synthetic':self.server.store.public()['workspace_is_demo'],'panel_request':self.server.panel_request,'desktop_attached':self.server.desktop_attached})
        if path=='history':
            try:return self.send(200,{'history':self.server.hub.session(parse_qs(urlsplit(self.path).query).get('session_id',[None])[0])['history']})
            except ValueError:return self.send(400,{'error':'没有这个会话'})
        if path=='memory':return self.send(200,{'preferences':self.server.store.preferences})
        if path=='artifacts':
            folder=self.server.store.folder/'outputs';items=[]
            if folder.is_dir():
                for file in sorted(folder.glob('*.json'),key=lambda p:p.stat().st_mtime,reverse=True)[:50]:
                    try:items.append(self.artifact(file.stem)[1])
                    except (OSError,ValueError,KeyError):pass
            return self.send(200,{'artifacts':items})
        if path=='artifact-preview':
            try:
                query=parse_qs(urlsplit(self.path).query);aid=query.get('id',[''])[0]
                tool=OfficeTools(self.server.store,lambda *args:None);result=tool.read_artifact(aid)
                return self.send(200,{'name':result['source']['file'],'text':result.get('text') or json.dumps(result.get('rows'),ensure_ascii=False,indent=2),'sha256':result['source']['sha256']})
            except (OSError,ValueError,KeyError):return self.send(409,{'error':'这份成果不存在或已变化'})
        if path.startswith('artifact/'):
            try:
                file,meta=self.artifact(path.split('/')[-1])
                import mimetypes
                return self.send(200,file.read_bytes(),mimetypes.guess_type(file.name)[0] or 'application/octet-stream',file.name)
            except (OSError,ValueError,KeyError):return self.send(404,{'error':'成果不存在或已变化'})
        if path=='source':
            query=parse_qs(urlsplit(self.path).query)
            if 'path' in query:
                try:
                    if query.get('workspace_id',[''])[0]!=self.server.store.config['workspace_id']:raise ValueError('工作文件夹已经切换，请在原范围重新查询')
                    tool=OfficeTools(self.server.store,lambda *args:None)
                    preview=tool.read_document(query['path'][0],limit=120)
                    if query.get('sha',[''])[0]!=preview['source']['sha256']:raise ValueError('来源已经变化，请重新读取')
                    return self.send(200,{'name':query['path'][0],'text':preview.get('text') or json.dumps(preview.get('rows'),ensure_ascii=False,indent=2),'sha256':preview['source']['sha256'],'synthetic':False})
                except (OSError,ValueError,KeyError):return self.send(409,{'error':'当前范围无法复核这份来源，可能目录或文件已变化'})
            provider=self.server.agent.provider;raw=provider.file.read_bytes()
            import hashlib
            if hashlib.sha256(raw).hexdigest()!=provider.digest:return self.send(409,{'error':'合成来源已变化，请重启后再读'})
            return self.send(200,{'name':'demo-data.json','text':raw.decode('utf-8'),'sha256':provider.digest,'synthetic':True})
        if path.startswith('job/'):
            with self.server.lock:job=self.server.jobs.get(path.split('/')[-1])
            if not job:
                try:job=self.server.experience.task(path.split('/')[-1])
                except ValueError:pass
            return self.send(200,job) if job else self.send(404,{'error':'本会话没有这个任务'})
        return self.send(404,{'error':'没有这个资源'})
    def do_POST(self):
        path=self.route()
        if path is None:return self.send(403,{'error':'无效的本机会话'})
        try:
            size=int(self.headers.get('Content-Length','0'))
            if not 0<size<=32768:raise ValueError('请求长度不合法')
            data=json.loads(self.rfile.read(size))
            if not isinstance(data,dict):raise ValueError('请求必须是对象')
            from suite_api import handle_post
            if handle_post(self,path,data):return
            if path=='ask':return self.send(200,self.server.start_job(data))
            if path=='settings':return self.send(200,self.server.store.save(data))
            if path=='workspace':
                with self.server.lock:
                    sid=self.server.store.config['active_session']
                    if any(j['session_id']==sid and j['state'] not in TERMINAL for j in self.server.jobs.values()):raise ValueError('请先等待或停止当前会话任务，再切换资料范围')
                    self.server.store.choose_workspace(data.get('path',''));self.server.hub.update_session(sid,workspace=data['path'])
                    return self.send(200,self.server.store.public())
            if path=='memory/delete':self.server.store.forget(data.get('key',''));return self.send(200,{'ok':True})
            if path=='cancel':
                jid=data.get('id')
                with self.server.lock:
                    if jid not in self.server.controls:raise ValueError('没有这个运行中的任务')
                    self.server.controls[jid].set()
                    if self.server.jobs[jid]['state'] not in ('done','error','cancelled'):self.server.jobs[jid].update(state='stopping',message='正在停止后续处理…')
                    self.server.jobs[jid]['revision']+=1;self.server.changed.notify_all()
                return self.send(200,{'ok':True})
            if path=='artifact/open':
                file,meta=self.artifact(data.get('id',''));os.startfile(str(file));return self.send(200,{'ok':True})
            if path=='outputs/open':
                folder=self.server.store.folder/'outputs';folder.mkdir(parents=True,exist_ok=True);os.startfile(str(folder));return self.send(200,{'ok':True})
            if path=='clear':self.server.hub.clear(self.server.store.config['active_session']);return self.send(200,{'ok':True})
            if path=='open-panel':
                self.server.panel_request+=1;return self.send(200,{'ok':True})
            if path=='check-model':
                store=self.server.store
                config,key=store.model_settings(data)
                if not key:raise ValueError('请在软件中填写自己的API密钥后测试')
                result=completion(config,key,[{'role':'user','content':'你好，请只回复：连接成功。'}],max_tokens=64)
                if not isinstance(result.get('content'),str) or not result['content'].strip():raise ValueError('API响应没有文字内容')
                return self.send(200,{'ok':True,'model':config['model'],'message':'当前填写的接口已连通（'+config['model']+'）。测试未保存设置；请点击保存。要在日常任务中调用模型，还需勾选“使用模型”。'})
            if path=='quit':
                self.send(200,{'ok':True});threading.Thread(target=self.server.shutdown,daemon=True).start();return
            return self.send(404,{'error':'没有这个操作'})
        except (ValueError,TypeError,json.JSONDecodeError) as error:return self.send(400,{'error':str(error)[:250]})
        except Exception:return self.send(500,{'error':'处理未完成，没有更改业务数据'})

def main():
    import argparse,subprocess
    p=argparse.ArgumentParser();p.add_argument('--no-window',action='store_true');p.add_argument('--synthetic-profile',action='store_true');args=p.parse_args()
    runtime=RUNTIME/'synthetic-profile' if args.synthetic_profile else RUNTIME;runtime.mkdir(parents=True,exist_ok=True)
    pointer=runtime/'current.json'
    if not args.no_window and pointer.is_file():
        reuse_stage='read-local-session'
        try:
            import urllib.request
            old=json.loads(pointer.read_text(encoding='utf-8'))
            if not old['url'].startswith('http://127.0.0.1:'):raise ValueError('Invalid local session')
            reuse_stage='read-status'
            with urllib.request.urlopen(old['url']+'status',timeout=2) as response:status=json.load(response)
            if status.get('version')==VERSION and status.get('desktop_attached'):
                reuse_stage='open-existing-panel'
                urllib.request.urlopen(urllib.request.Request(old['url']+'open-panel',data=b'{}',headers={'Content-Type':'application/json'}),timeout=2).read();return
        except (OSError,ValueError,KeyError) as error:
            (runtime/'last-reuse-error.json').write_text(json.dumps({'stage':reuse_stage,'type':type(error).__name__,'code':getattr(error,'code',None),'reason':str(getattr(error,'reason',''))[:250]}),encoding='utf-8')
            import traceback
            (runtime/'reuse-diagnostic.txt').write_text(traceback.format_exc(),encoding='utf-8')
    server=Server(Store(runtime))
    pointer.write_text(json.dumps({'url':server.base,'pid':os.getpid(),'version':VERSION}),encoding='utf-8')
    process=None
    if not args.no_window:
        electron=BUNDLE/'desktop-runtime/electron.exe'
        if not electron.is_file():electron=TOOLS_ROOT/'xiaolong-agent-20261026/vendor/electron/electron.exe'
        if not electron.is_file():raise ValueError('桌面运行组件未准备完成')
        env=dict(os.environ);env.pop('ELECTRON_RUN_AS_NODE',None)
        process=subprocess.Popen([str(electron),str(ASSETS/'desktop/main.cjs'),'--xl-url='+server.base,'--xl-runtime='+str(runtime)],env=env,
            creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        server.desktop_attached=True
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
