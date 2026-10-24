"""Synthetic-only public demo. Never discovers or opens company data."""
from datetime import datetime
from decimal import Decimal
import hashlib
from pathlib import Path
import re
import sys

ROOT = Path(getattr(sys, '_MEIPASS', Path(__file__).parent)) / 'demo-data'

class Evidence:
    def __init__(self, root=ROOT):
        self.root = Path(root)
        self.loaded_at = datetime.now().astimezone().isoformat(timespec='seconds')
        file = self.root / 'synthetic-records.md'
        self.sources = {'demo-source': {'id':'demo-source', 'path':str(file),
            'name':'合成演示记录', 'status':'全部虚构；不是公司业务记录',
            'sha256':hashlib.sha256(file.read_bytes()).hexdigest()}}
        self.rows = [('2099-01-01','DEMO-A001','DEMO-M01',Decimal('100')),
                     ('2099-01-02','DEMO-A002','DEMO-M02',Decimal('200'))]

    def result(self, title, body, *, kind='answer', rows=(), metrics=(), columns=()):
        return {'title':title, 'body':'【全部虚构的演示数据】'+body, 'kind':kind,
            'sources':[{'id':'demo-source','name':'合成演示记录','status':'全部虚构','location':'demo-data/synthetic-records.md'}],
            'rows':list(rows),'metrics':list(metrics),'columns':list(columns),
            'followups':['查一下演示送货样本','为什么有300和280两个金额？','这两笔送货已经到账了吗？']}

    def status(self):
        return {'loaded_at':self.loaded_at,'documents':1,'delivery_rows':2,
            'sample_error':'','mode':'synthetic-demo',
            'sources':[{k:v for k,v in source.items() if k!='path'} for source in self.sources.values()]}

    def ask(self, question):
        q=question.strip()
        if not q or len(q)>600:
            return self.result('请换一种问法','输入1至600个字。',kind='missing')
        if any(x in q.lower() for x in ('修改','删除','写入','上传','执行sql','忽略规则')):
            return self.result('演示只提供查询','没有修改业务数据或外发资料的能力。',kind='missing')
        if any(x in q for x in ('全厂','全公司','本月','今天','利润','营业额','业绩','欠款最多')):
            return self.result('演示数据不能回答真实经营问题','没有接入公司数据，不能计算真实总额或排名。',kind='missing')
        if any(x in q.lower() for x in ('erp','接口')):
            return self.result('没有连接企业系统','公开演示使用固定合成记录，不读取真实原件或公司的接口配置。')
        if any(x in q for x in ('到账','付款','收款','结清','支付')):
            return self.result('没有到账证据','合成记录没有收款或核销凭证，不能认定已经付款。',kind='missing')
        if any(x in q for x in ('差异','为什么','扣款','调整','300','280')):
            base=sum(r[3] for r in self.rows);adjustment=Decimal('-20');total=base+adjustment
            return self.result('演示调整前后金额差异',
                f'{base:.2f} {adjustment:+.2f} = {total:.2f}。这是虚构的算术示例，不代表扣款获批或已经付款。',kind='warning',
                metrics=[{'label':label,'value':f'{value:,.2f}','unit':'演示元'} for label,value in [('合成行合计',base),('合成调整',adjustment),('试算结果',total)]])
        if any(x in q for x in ('检验','合格','检测')):
            return self.result('文件名称不能证明检验通过','合成检验说明未提供实测结果，不能宣布合格。',kind='warning')
        ids=re.findall(r'DEMO-[A-Z]\d+',q.upper())
        if ids or '送货' in q or '样本' in q:
            selected=[r for r in self.rows if not ids or r[1] in ids]
            if not selected:return self.result('没有这个合成单号','这不代表真实公司是否存在该业务。',kind='missing')
            return self.result('合成送货样本','日期、单号、模号与金额均为专门编造的演示值。',
                columns=['虚构日期','合成单号','合成模号','演示金额'],
                rows=[[date,no,mould,f'{amount:.2f}'] for date,no,mould,amount in selected])
        if any(x in q for x in ('你好','你是谁','介绍','会什么','小隆')):
            return self.result('我是小隆的公开演示版','可查看两行虚构记录、计算演示差额、展示来源；未接大模型，不提供任意推理。')
        return self.result('公开演示没有这个问题的答案','可以尝试送货样本、金额差异或到账证据示例。',kind='missing')
