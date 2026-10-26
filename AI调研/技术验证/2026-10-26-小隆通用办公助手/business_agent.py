"""Model routes intent; business answers always come from a validated tool."""
import json
import urllib.request
import urllib.error
import re
from urllib.parse import urlsplit
from provider import DemoProvider,TOOLS,demo_route

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):return None

def capability_answer(question,config,key):
    compact=re.sub(r'[\s，。？！?！、,.：:]','',question.lower())
    capability=re.fullmatch(r'(?:请问|那|所以)?你(?:现在|目前|都|还)?(?:能|可以|会)(?:做|干|帮我做)(?:点|些)?什么(?:事情|工作|呢|啊)?|你(?:有|具备)(?:什么|哪些)功能|你是谁|介绍一下你(?:自己)?',compact)
    connection=len(compact)<100 and re.search(r'没连上|未连接|没有连接|还没连|连上了吗|连接状态|模型.{0,5}(连接|启用)|(?:api|模型).{0,5}(没连|未连)',compact)
    if not (capability or connection):return None
    live=bool(config.get('use_model') and key)
    status='**当前模型已启用**，后续对话会通过已配置的接口请求回复。' if live else '**当前模型未启用**，现在可体验本地示例；要使用模型，请在设置中配置接口、勾选“使用模型”并保存。'
    return {'title':'小隆的当前能力','body':status+'\n\n你可以直接在这个对话里：\n\n- **聊想法、写文字**：整理思路、润色表达、讨论工作安排。\n- **读资料、找依据**：读取所选文件夹中的文档和表格，检索相关内容并列出来源。\n- **核算与整理**：计算数字、整理纪要和待办，生成Word、Excel或Markdown文件；也可以读取旧成果后另存修改稿。\n- **记住办公偏好**：明确告诉我你希望记住的报告风格或工作习惯，可随时删除。\n\n你不用切换聊天或办公模式，直接交代任务就好。公司查询目前只有虚构演示样本，未接真实ERP；当前也没有联网搜索、自动提醒、发消息或修改正式业务数据的工具。\n\n这是程序根据当前设置提供的说明，没有发起新的接口测试。若要确认服务此刻是否可用，可在设置中测试当前接口。','kind':'capabilities','engine':'程序当前状态与能力说明','sources':[],'rows':[],'metrics':[],'synthetic':False}

def completion(config,key,messages,tools=None,*,max_tokens=1200):
    base=config.get('base_url','https://api.deepseek.com').rstrip('/')
    u=urlsplit(base)
    if u.username or u.password or u.query or u.fragment:raise ValueError('API地址不能包含凭据、查询或片段')
    if u.scheme!='https' and not (u.scheme=='http' and u.hostname in ('127.0.0.1','localhost')):raise ValueError('API地址必须使用HTTPS；仅本机测试可用HTTP')
    payload={'model':config.get('model','deepseek-flash'),'messages':messages,'max_tokens':max_tokens,'temperature':0}
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
        raise ValueError({400:'API已响应，但请求参数不被接受（HTTP 400）；请核对模型ID，DeepSeek Flash请填deepseek-flash',401:'API密钥无效或无权使用（HTTP 401）',402:'API余额不足（HTTP 402）',429:'API请求过于频繁（HTTP 429）'}.get(error.code,f'API返回HTTP {error.code}；请检查接口与模型ID')) from None
    except (urllib.error.URLError,TimeoutError):raise ValueError('API连接失败或超时，请检查网络和接口地址') from None
    except (KeyError,IndexError,json.JSONDecodeError):raise ValueError('模型响应格式与兼容接口不符') from None

class Agent:
    def __init__(self):self.provider=DemoProvider()
    def run(self,question,mode,config,key,history,stage):
        if not isinstance(question,str) or not question.strip() or len(question)>2000:raise ValueError('请输入1至2000个字')
        if mode not in ('business','chat'):raise ValueError('未知对话模式')
        live=bool(config.get('use_model') and key)
        if mode=='chat':
            current=capability_answer(question,config,key)
            if current:
                stage('checking','核对当前程序能力与模型设置…')
                return current
            stage('thinking','在听你说…')
            if live:
                messages=[{'role':'system','content':'你是小隆，温和简洁的办公伙伴。程序当前事实：模型已启用，本次回复正在通过配置的模型API请求；不要说尚未连接模型或要求重新配置密钥。历史里的旧状态不能覆盖当前事实。当前模式为轻松聊聊，可交流和写文字，没有文件工具；处理资料、检索、计算、生成Word/Excel/Markdown、读取旧成果和管理偏好，请引导切换“办公助手”。“公司问答 · 演示”只有虚构样本，未接ERP。没有联网搜索、提醒、发送消息或修改正式业务数据的能力。不要编造公司事实或执行动作。称呼用户为'+config.get('nickname','你')+'。'}]
                for item in history[-6:]:
                    if item.get('mode')=='chat' and item.get('answer',{}).get('engine')=='模型陪聊':messages += [{'role':'user','content':item['question'][:2000]},{'role':'assistant','content':item['answer']['body'][:2000]}]
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
