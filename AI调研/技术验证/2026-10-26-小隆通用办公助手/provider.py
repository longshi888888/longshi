"""Business contract; this implementation reads synthetic fixtures only."""
from pathlib import Path
from decimal import Decimal
import hashlib
import json
import re
import sys

ASSETS = Path(getattr(sys, '_MEIPASS', Path(__file__).parent))

class DemoProvider:
    def __init__(self):
        self.file=ASSETS/'demo-data.json'
        raw=self.file.read_bytes();self.data=json.loads(raw)
        if self.data.get('synthetic') is not True:raise ValueError('只接受明确标记的合成演示数据')
        self.digest=hashlib.sha256(raw).hexdigest()

    def answer(self,title,body,*,kind='answer',rows=(),columns=(),metrics=(),location=''):
        return {'title':title,'body':body,'kind':kind,'synthetic':True,
            'rows':list(rows),'columns':list(columns),'metrics':list(metrics),
            'sources':[{'id':self.data['dataset_id'],'file':'demo-data.json','location':location,
                        'sha256':self.digest,'label':'虚构演示数据，不是公司记录'}]}

    def execute(self,name,args):
        if not isinstance(args,dict):raise ValueError('工具参数必须是对象')
        allowed={'delivery_query':{'delivery_no'},'reconciliation_query':set(),
                 'payment_evidence':set(),'system_scope':set(),'cannot_answer':{'reason'}}
        if name not in allowed or not set(args).issubset(allowed[name]):raise ValueError('未授权的查询或参数')
        if name=='delivery_query':
            number=args.get('delivery_no','')
            if not isinstance(number,str) or len(number)>80:raise ValueError('单号参数不合法')
            selected=[r for r in self.data['deliveries'] if not number or r['delivery_no'].upper()==number.upper()]
            if not selected:return self.answer('本次数据没有这个单号','这不等于真实公司没有该业务。当前只接入两行虚构记录。',kind='missing',location='deliveries')
            return self.answer('查到合成送货记录','以下日期、单号、产品与金额均为专门编造的演示数据。',
                columns=['虚构日期','合成单号','虚构产品','演示金额'],
                rows=[[r['date'],r['delivery_no'],r['product'],r['amount']] for r in selected],location='deliveries')
        if name=='reconciliation_query':
            base=sum((Decimal(r['amount']) for r in self.data['deliveries']),Decimal('0'))
            adjustment=Decimal(self.data['adjustment']);total=base+adjustment
            return self.answer('调整前后金额口径不同',f'{base:.2f} {adjustment:+.2f} = {total:.2f}。这是合成数据试算，不代表调整已经批准或已经付款。',kind='warning',
                metrics=[{'label':label,'value':f'{v:,.2f}','unit':'演示元'} for label,v in [('行金额合计',base),('合成调整',adjustment),('试算结果',total)]],location='deliveries / adjustment')
        if name=='payment_evidence':
            return self.answer('没有到账证据','这份演示数据没有收款或核销凭证，不能认定已付、未付，也不能把缺少证据当作金额为零。',kind='missing',location='payment_evidence')
        if name=='system_scope':
            return self.answer('当前是公司问答Agent的独立体验壳','数据源是公开合成样本，尚未连接ERP、生产库或企业权限服务。模型只选择受控查询；金额和结果由工具返回。以后需替换Provider、授权与业务接口。',location='dataset_id / synthetic')
        reason=args.get('reason','unsupported')
        if not isinstance(reason,str):raise ValueError('无法回答原因不合法')
        return self.answer('目前没有足够数据回答','当前合成样本不支持这个问题。不能推断全厂统计、利润、排名、实时订单进度或审批结果。可以先查询演示送货样本、金额差异或到账证据。',kind='missing',location='dataset_id')

TOOLS=[]
for name,description,properties,required in [
    ('delivery_query','查询已接入的送货明细；指定单号时精确筛选，不存在则明确返回缺失。',{'delivery_no':{'type':'string','description':'用户明确给出的完整单号；未指定则空字符串。'}},['delivery_no']),
    ('reconciliation_query','查询送货合计、调整和试算差异，不认定批准或付款。',{},[]),
    ('payment_evidence','核查是否存在到账或付款凭证，不把未知当未付。',{},[]),
    ('system_scope','说明数据范围、ERP接入和本演示的能力边界。',{},[]),
    ('cannot_answer','缺少数据、业务规则不支持或不属于以上查询时，明确无法可靠回答。',{'reason':{'type':'string'}},['reason'])]:
    TOOLS.append({'type':'function','function':{'name':name,'description':description,
        'parameters':{'type':'object','properties':properties,'required':required,'additionalProperties':False}}})

def demo_route(question):
    q=question.lower()
    if any(w in q for w in ['修改','删除','写入','忽略','sql','全厂','全公司','利润','营业额','排名','实时进度']):return 'cannot_answer',{'reason':'not_available'}
    if any(w in q for w in ['erp','接口','接入','数据范围','你能做什么']):return 'system_scope',{}
    if any(w in q for w in ['到账','收款','付款','结清','核销']):return 'payment_evidence',{}
    if any(w in q for w in ['差异','调整','扣款','300','280','合计','合共']):return 'reconciliation_query',{}
    number=re.search(r'demo-[a-z]\d+',q,re.I)
    if number or any(w in q for w in ['送货','出货样本','记录','单号']):return 'delivery_query',{'delivery_no':number.group().upper() if number else ''}
    return 'cannot_answer',{'reason':'no_demo_route'}
