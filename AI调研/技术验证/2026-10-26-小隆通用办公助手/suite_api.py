"""Small local API surface for the expanded office workbench."""
from urllib.parse import urlsplit,parse_qs
from pathlib import Path
import base64
from datetime import datetime
from office_tools import OfficeTools
from extended_tools import provider_request,BUNDLE
from hub import TERMINAL

def handle_get(handler,path):
    server=handler.server;query=parse_qs(urlsplit(handler.path).query)
    def arg(key,default=''):return query.get(key,[default])[0]
    try:
        if path=='sessions':result={'sessions':server.hub.sessions(),'active':server.store.config['active_session'],'session':server.hub.session()};result['session'].pop('history',None)
        elif path=='tasks':result={'tasks':server.experience.tasks(arg('session_id') or None)}
        elif path=='notifications':result=server.experience.messages()
        elif path=='tts/status':result=server.speech.status(arg('id'))
        elif path.startswith('tts/audio/'):
            handler.send(200,server.speech.audio(path.rsplit('/',1)[-1]),'audio/wav');return True
        elif path=='notes':result={'notes':server.hub.memories(arg('q'),server.store.config['active_session'])}
        elif path=='approvals':result={'approvals':server.hub.pending()}
        elif path=='schedules':result={'schedules':server.hub.schedules(),'host_running_required':True}
        elif path=='features':result={'voice':server.voice.available(),'sandbox':(BUNDLE/'sandbox-runtime/python.wasm').is_file(),'network':urlsplit(server.store.config['base_url']).hostname=='api.deepseek.com' and bool(server.store.key),'long_memory':'本机持久文字检索','sessions':True,'schedules':True,'plan':True,'team':True}
        elif path=='balance':
            data=provider_request(server.store.config,server.store.key,'/user/balance')
            result={'available':bool(data.get('is_available')),'balances':[{k:str(row.get(k,''))[:50] for k in ('currency','total_balance','granted_balance','topped_up_balance')} for row in data.get('balance_infos',[])[:4]],'checked_at':datetime.now().astimezone().isoformat(timespec='seconds')}
        elif path=='preview':
            tool=OfficeTools(server.hub.context(),lambda *a:None)
            if arg('id'):result=tool.read_artifact(arg('id'),start=max(1,int(arg('start','1'))),limit=200,sheet=arg('sheet'))
            else:result=tool.read_document(arg('path'),start=max(1,int(arg('start','1'))),limit=200,sheet=arg('sheet'))
            result['content_preview']=True
        else:return False
        handler.send(200,result)
    except (ValueError,OSError,KeyError,TypeError) as error:handler.send(400,{'error':str(error)[:250] if isinstance(error,ValueError) else '本次读取没有完成，请检查文件和设置'})
    return True

def handle_post(handler,path,data):
    server=handler.server;sid=server.store.config['active_session']
    if path=='sessions/new':result=server.hub.create(data.get('title','新会话'),data.get('workspace'))
    elif path=='tasks/pause':result=server.pause_job(data.get('id'))
    elif path=='tasks/continue':result=server.continue_job(data.get('id'),data.get('supplement',''))
    elif path=='notifications/read':server.experience.read(data.get('id'));result={'ok':True}
    elif path=='tts/start':result=server.speech.start(data.get('text'))
    elif path=='tts/stop':server.speech.stop();result={'ok':True}
    elif path=='sessions/select':result=server.hub.select(data.get('id'))
    elif path=='sessions/update':
        target=data.get('id',sid)
        if data.get('workspace') is not None and any(j['session_id']==target and j['state'] not in TERMINAL for j in server.jobs.values()):raise ValueError('请先停止这个会话中的任务，再改资料目录')
        result=server.hub.update_session(target,title=data.get('title'),workspace=data.get('workspace'),plan_mode=data.get('plan_mode'))
    elif path=='notes/add':result=server.hub.memory_add(data.get('text'),sid if data.get('scope','session')=='session' else 'global')
    elif path=='notes/delete':server.hub.memory_delete(data.get('id'));result={'ok':True}
    elif path=='approvals/decide':
        item=server.hub.get_approval(data.get('id'));job=server.jobs.get(item['job_id'])
        if not job or job['state'] in TERMINAL or server.controls[item['job_id']].is_set():raise ValueError('关联任务已结束，确认无效')
        result=server.hub.decide(data.get('id'),data.get('approved'))
    elif path=='schedules/save':result=server.hub.schedule_save(data.get('session_id',sid),data.get('title'),data.get('prompt'),data.get('rule'),data.get('id'))
    elif path=='schedules/toggle':server.hub.schedule_toggle(data.get('id'),data.get('enabled'));result={'ok':True}
    elif path=='schedules/delete':server.hub.schedule_delete(data.get('id'));result={'ok':True}
    elif path=='voice/start':result=server.voice.start()
    elif path=='voice/chunk':
        try:pcm=base64.b64decode(data.get('pcm',''),validate=True)
        except ValueError:raise ValueError('音频编码无效') from None
        result=server.voice.push(data.get('id'),pcm)
    elif path=='voice/stop':result=server.voice.push(data.get('id'),final=True)
    else:return False
    if path.startswith('sessions/'):result={'id':result['id'],'title':result['title'],'workspace':result['workspace'],'plan_mode':result['plan_mode']}
    handler.send(200,result);return True
