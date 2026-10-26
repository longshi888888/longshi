"""Model routes intent; business answers always come from a validated tool."""
import json
import urllib.request
import urllib.error
import re
from urllib.parse import urlsplit
from provider import DemoProvider,TOOLS,demo_route

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):return None

def completion(config,key,messages,tools=None):
    base=config.get('base_url','https://api.deepseek.com').rstrip('/')
    u=urlsplit(base)
    if u.username or u.password or u.query or u.fragment:raise ValueError('API地址不能包含凭据、查询或片段')
    if u.scheme!='https' and not (u.scheme=='http' and u.hostname in ('127.0.0.1','localhost')):raise ValueError('API地址必须使用HTTPS；仅本机测试可用HTTP')
    payload={'model':config.get('model','deepseek-flash'),'messages':messages,'max_tokens':1200,'temperature':0}
    if tools:payload.update(tools=tools,tool_choice='required',parallel_tool_calls=False)
    if u.hostname=='api.deepseek.com':payload['thinking']={'type':'disabled'}
    request=urllib.request.Request(base+'/chat/completions',data=json.dumps(payload,ensure_ascii=False).encode('utf-8'),
        headers={'Content-Type':'application/json','Authorization':'Bearer '+key},method='POST')
    try:
        with urllib.request.build_opener(NoRedirect()).open(request,timeout=45) as r:
            data=r.read(2_000_001)
            if len(data)>2_000_000:raise ValueError('模型响应过长')
        return json.loads(data)['choices'][0]['message']
    except urllib.error.HTTPError as error:
        raise ValueError({401:'API密钥无效或无权使用',402:'API余额不足',429:'API请求过于频繁'}.get(error.code,f'API返回HTTP {error.code}；请检查接口与模型名')) from None
    except (urllib.error.URLError,TimeoutError):raise ValueError('API连接失败或超时，请检查网络和接口地址') from None
    except (KeyError,IndexError,json.JSONDecodeError):raise ValueError('模型响应格式与兼容接口不符') from None

class Agent:
    def __init__(self):self.provider=DemoProvider()
    def run(self,question,mode,config,key,history,stage):
        if not isinstance(question,str) or not question.strip() or len(question)>2000:raise ValueError('请输入1至2000个字')
        if mode not in ('business','chat'):raise ValueError('未知对话模式')
        live=bool(config.get('use_model') and key)
        if mode=='chat':
            stage('thinking','在听你说…')
            if live:
                messages=[{'role':'system','content':'你是小隆，温和简洁的工厂桌面伙伴。当前是陪聊，不具有真实公司数据。不要编造公司事实或执行动作，业务查询请引导点查业务。称呼用户为'+config.get('nickname','你')+'。'}]
                for item in history[-6:]:
                    if item.get('mode')=='chat':messages += [{'role':'user','content':item['question'][:2000]},{'role':'assistant','content':item['answer']['body'][:2000]}]
                messages.append({'role':'user','content':question})
                message=completion(config,key,messages)
                body=message.get('content')
                if not isinstance(body,str) or not body.strip():raise ValueError('模型没有返回陪聊内容')
            else:body='我在呢。现在还没有连接聊天模型，你可以在设置里填写自己的API密钥。点“查业务”能先体验有来源的合成数据查询。'
            return {'title':'小隆陪你聊聊','body':body,'kind':'chat','sources':[],'rows':[],'metrics':[],
                'engine':'模型陪聊' if live else '本地提示（未调用模型）','synthetic':True}
        stage('routing','理解问题，选择查询…')
        if live:
            message=completion(config,key,[{'role':'system','content':'你是业务问题路由器。仅调用一个给定工具，不生成SQL，不生成业务数字。保留用户给出的单号原文；未指定单号时传空字符串。数据不足或越权的问题调用cannot_answer。所有接入数据均为虚构演示。'},
                {'role':'user','content':question}],TOOLS)
            calls=message.get('tool_calls',[])
            if len(calls)!=1:raise ValueError('模型没有返回单一受控查询；未执行业务操作')
            function=calls[0].get('function',{});name=function.get('name');raw=function.get('arguments','{}')
            if not isinstance(raw,str) or len(raw)>4000:raise ValueError('模型工具参数无效')
            try:args=json.loads(raw)
            except json.JSONDecodeError:raise ValueError('模型工具参数不是合法JSON') from None
        else:name,args=demo_route(question)
        if name=='delivery_query':
            ids=re.findall(r'DEMO-[A-Z]\d+',question.upper())
            if ids and (len(set(ids))!=1 or args.get('delivery_no','').upper()!=ids[0]):
                raise ValueError('查询单号与用户问题不一致，已停止返回记录')
        stage('querying','核对合成数据和出处…')
        result=self.provider.execute(name,args)
        result.update(engine='模型选择工具；业务工具生成结果' if live else '本地演示路由（未调用模型）',tool=name)
        stage('checking','检查金额与证据范围…')
        return result
