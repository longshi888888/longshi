"""Local durable sessions, explicit memories, approvals and schedules."""
from pathlib import Path
from datetime import datetime,timedelta
from zoneinfo import ZoneInfo
import sqlite3,json,uuid,threading,re

TERMINAL={'done','error','cancelled'}
def now():return datetime.now().astimezone().isoformat(timespec='seconds')
def uid():return uuid.uuid4().hex
def bounded(value,maximum=3000):
    if not isinstance(value,str) or not value.strip() or len(value)>maximum:raise ValueError('内容为空或超过长度限制')
    if re.search(r'sk-[\w-]{16,}|-----BEGIN .+PRIVATE KEY|(?:api[_ -]?key|密码|密钥)\s*[:：=]',value,re.I):raise ValueError('请勿保存密钥或密码')
    return value.strip()

class Hub:
    def __init__(self,store):
        self.store=store;self.lock=threading.RLock();self.db=sqlite3.connect(store.folder/'assistant.db',check_same_thread=False)
        self.db.row_factory=sqlite3.Row
        self.db.executescript('''PRAGMA journal_mode=WAL;
        CREATE TABLE IF NOT EXISTS sessions(id TEXT PRIMARY KEY,title TEXT,workspace TEXT,workspace_id TEXT,history TEXT,plan_mode INTEGER,updated TEXT);
        CREATE TABLE IF NOT EXISTS memories(id TEXT PRIMARY KEY,text TEXT,scope TEXT,created TEXT);
        CREATE TABLE IF NOT EXISTS approvals(id TEXT PRIMARY KEY,job_id TEXT,session_id TEXT,kind TEXT,payload TEXT,state TEXT,created TEXT);
        CREATE TABLE IF NOT EXISTS schedules(id TEXT PRIMARY KEY,session_id TEXT,title TEXT,prompt TEXT,rule TEXT,next_run TEXT,enabled INTEGER,last_job TEXT,last_state TEXT,updated TEXT);
        CREATE TABLE IF NOT EXISTS runs(id TEXT PRIMARY KEY,session_id TEXT,state TEXT,question TEXT,updated TEXT);
        ''')
        with self.lock,self.db:
            if not self.db.execute('SELECT 1 FROM sessions LIMIT 1').fetchone():
                sid=uid();self.db.execute('INSERT INTO sessions VALUES(?,?,?,?,?,?,?)',(sid,'原有会话',store.config['workspace'],store.config['workspace_id'],json.dumps(store.history,ensure_ascii=False),0,now()))
            sid=store.config.get('active_session')
            if not self.db.execute('SELECT 1 FROM sessions WHERE id=?',(sid,)).fetchone():sid=self.db.execute('SELECT id FROM sessions ORDER BY updated DESC LIMIT 1').fetchone()[0]
            self.db.execute("UPDATE runs SET state='interrupted',updated=? WHERE state NOT IN ('done','error','cancelled','interrupted')",(now(),))
            self.db.execute("UPDATE approvals SET state='expired' WHERE state='pending'")
        self.select(sid)
    def session(self,sid=None):
        with self.lock:row=self.db.execute('SELECT * FROM sessions WHERE id=?',(sid or self.store.config.get('active_session'),)).fetchone()
        if not row:raise ValueError('没有这个会话')
        data=dict(row);data['history']=json.loads(data['history']);data['plan_mode']=bool(data['plan_mode']);return data
    def sessions(self):
        with self.lock:rows=self.db.execute('SELECT id,title,workspace,plan_mode,updated FROM sessions ORDER BY updated DESC').fetchall()
        return [dict(r) for r in rows]
    def select(self,sid):
        data=self.session(sid)
        with self.store.lock:
            self.store.config.update(active_session=sid,workspace=data['workspace'],workspace_id=data['workspace_id'])
            self.store.history=list(data['history']);self.store._write('settings.json',self.store.config)
        return data
    def create(self,title='新会话',workspace=None):
        title=bounded(title,80);workspace=workspace or self.store.config['workspace'];path=Path(workspace).resolve()
        if not path.is_dir() or path==Path(path.anchor):raise ValueError('请选择具体且存在的资料文件夹')
        sid=uid()
        with self.lock,self.db:self.db.execute('INSERT INTO sessions VALUES(?,?,?,?,?,?,?)',(sid,title,str(path),uid(),'[]',0,now()))
        return self.select(sid)
    def update_session(self,sid,*,title=None,workspace=None,plan_mode=None):
        data=self.session(sid)
        if title is not None:data['title']=bounded(title,80)
        if workspace is not None:
            path=Path(workspace).resolve()
            if not path.is_dir() or path==Path(path.anchor):raise ValueError('请选择具体且存在的资料文件夹')
            data.update(workspace=str(path),workspace_id=uid())
        if plan_mode is not None:
            if type(plan_mode)!=bool:raise ValueError('计划开关须为布尔值')
            data['plan_mode']=plan_mode
        with self.lock,self.db:self.db.execute('UPDATE sessions SET title=?,workspace=?,workspace_id=?,plan_mode=?,updated=? WHERE id=?',(data['title'],data['workspace'],data['workspace_id'],int(data['plan_mode']),now(),sid))
        if sid==self.store.config.get('active_session'):self.select(sid)
        return data
    def append(self,sid,item):
        with self.lock,self.db:
            data=self.session(sid);history=(data['history']+[item])[-100:]
            title=data['title']
            if title=='新会话':title=item['question'][:24]
            self.db.execute('UPDATE sessions SET history=?,title=?,updated=? WHERE id=?',(json.dumps(history,ensure_ascii=False),title,now(),sid))
        if sid==self.store.config.get('active_session'):
            with self.store.lock:self.store.history=history
    def clear(self,sid):
        with self.lock,self.db:self.db.execute('UPDATE sessions SET history=?,updated=? WHERE id=?',('[]',now(),sid))
        if sid==self.store.config.get('active_session'):self.store.clear()
    def context(self,sid=None):return SessionView(self,self.session(sid))
    def memory_add(self,text,scope='global'):
        text=bounded(text);mid=uid()
        if scope!='global':self.session(scope)
        with self.lock,self.db:self.db.execute('INSERT INTO memories VALUES(?,?,?,?)',(mid,text,scope,now()))
        return {'id':mid,'text':text,'scope':scope,'created':now()}
    def memories(self,query='',sid=None):
        if not isinstance(query,str) or len(query)>200:raise ValueError('搜索词过长')
        with self.lock:rows=[dict(r) for r in self.db.execute('SELECT * FROM memories WHERE scope IN (?,?) ORDER BY created DESC LIMIT 500',('global',sid or self.store.config['active_session']))]
        if not query:return rows[:100]
        terms=re.findall(r'[a-zA-Z0-9]{2,}|[\u4e00-\u9fff]{2,}',query.lower())
        terms=[t for term in terms for t in ([term]+[term[i:i+2] for i in range(len(term)-1)] if len(term)>4 else [term])]
        scored=[(sum(t in r['text'].lower() for t in set(terms)),r) for r in rows]
        return [r for score,r in sorted(scored,key=lambda x:x[0],reverse=True) if score][:15]
    def memory_delete(self,mid):
        with self.lock,self.db:self.db.execute('DELETE FROM memories WHERE id=?',(mid,))
    def approval(self,job_id,sid,kind,payload):
        aid=uid();raw=json.dumps(payload,ensure_ascii=False)
        if len(raw)>50000:raise ValueError('审批内容过长')
        with self.lock,self.db:self.db.execute('INSERT INTO approvals VALUES(?,?,?,?,?,?,?)',(aid,job_id,sid,kind,raw,'pending',now()))
        return self.get_approval(aid)
    def get_approval(self,aid):
        with self.lock:row=self.db.execute('SELECT * FROM approvals WHERE id=?',(aid,)).fetchone()
        if not row:raise ValueError('没有这个确认项')
        result=dict(row);result['payload']=json.loads(result['payload']);return result
    def decide(self,aid,approved):
        if type(approved)!=bool:raise ValueError('决定须为布尔值')
        with self.lock,self.db:
            result=self.db.execute("UPDATE approvals SET state=? WHERE id=? AND state='pending'",('approved' if approved else 'rejected',aid))
            if result.rowcount!=1:raise ValueError('确认项已处理或过期，请查看当前任务')
        return self.get_approval(aid)
    def pending(self,sid=None):
        with self.lock:rows=self.db.execute("SELECT id FROM approvals WHERE state='pending' AND (? IS NULL OR session_id=?)",(sid,sid)).fetchall()
        return [self.get_approval(r[0]) for r in rows]
    def expire(self,job_id):
        with self.lock,self.db:self.db.execute("UPDATE approvals SET state='expired' WHERE job_id=? AND state='pending'",(job_id,))
    def record_run(self,jid,sid,question,state):
        with self.lock,self.db:self.db.execute('INSERT OR REPLACE INTO runs VALUES(?,?,?,?,?)',(jid,sid,state,question[:200],now()))
    def schedule_save(self,sid,title,prompt,rule,schedule_id=None):
        self.session(sid);title=bounded(title,80);prompt=bounded(prompt,4000);next_run=next_time(rule)
        if not next_run:raise ValueError('规则没有未来运行时间')
        aid=schedule_id or uid()
        with self.lock,self.db:
            if schedule_id and not self.db.execute('SELECT 1 FROM schedules WHERE id=? AND session_id=?',(aid,sid)).fetchone():raise ValueError('没有这个会话的定时任务')
            self.db.execute('INSERT INTO schedules VALUES(?,?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET title=excluded.title,prompt=excluded.prompt,rule=excluded.rule,next_run=excluded.next_run,enabled=1,updated=excluded.updated',(aid,sid,title,prompt,json.dumps(rule),next_run,1,'','等待运行',now()))
        return self.schedule(aid)
    def schedule(self,aid):
        with self.lock:row=self.db.execute('SELECT * FROM schedules WHERE id=?',(aid,)).fetchone()
        if not row:raise ValueError('没有这个定时任务')
        result=dict(row);result['rule']=json.loads(result['rule']);return result
    def schedules(self):
        with self.lock:rows=self.db.execute('SELECT id FROM schedules ORDER BY updated DESC').fetchall()
        return [self.schedule(r[0]) for r in rows]
    def schedule_toggle(self,aid,enabled):
        if type(enabled)!=bool:raise ValueError('开关须为布尔值')
        item=self.schedule(aid);target=next_time(item['rule']) if enabled else item['next_run']
        if enabled and not target:raise ValueError('一次性时间已过去，请编辑时间后启用')
        with self.lock,self.db:self.db.execute('UPDATE schedules SET enabled=?,next_run=?,updated=? WHERE id=?',(int(enabled),target,now(),aid))
    def schedule_delete(self,aid):
        with self.lock,self.db:self.db.execute('DELETE FROM schedules WHERE id=?',(aid,))
    def due(self):
        current=datetime.now().astimezone()
        return [item for item in self.schedules() if item['enabled'] and datetime.fromisoformat(item['next_run'])<=current]
    def schedule_started(self,aid,jid):
        item=self.schedule(aid);target=None if item['rule']['kind']=='once' else next_time(item['rule'])
        with self.lock,self.db:self.db.execute('UPDATE schedules SET next_run=?,enabled=?,last_job=?,last_state=?,updated=? WHERE id=?',(target or item['next_run'],int(bool(target)),jid,'运行中',now(),aid))
    def schedule_finished(self,jid,state):
        with self.lock,self.db:self.db.execute('UPDATE schedules SET last_state=?,updated=? WHERE last_job=?',(state,now(),jid))

def next_time(rule,current=None):
    if not isinstance(rule,dict):raise ValueError('时间规则须为对象')
    timezone=ZoneInfo(rule.get('timezone','Asia/Shanghai'));current=(current or datetime.now(timezone)).astimezone(timezone)
    kind=rule.get('kind')
    if kind=='once':
        value=datetime.fromisoformat(rule['at']);value=value.replace(tzinfo=timezone) if value.tzinfo is None else value
        return value.isoformat() if value>current else None
    if kind=='interval':
        seconds=int(rule.get('seconds',0))
        if not 60<=seconds<=31_536_000:raise ValueError('间隔须为60秒至一年')
        return (current+timedelta(seconds=seconds)).isoformat()
    from apscheduler.triggers.cron import CronTrigger
    if kind in ('daily','weekly'):
        hour,minute=map(int,rule.get('time','09:00').split(':'))
        days=rule.get('weekdays',[0,1,2,3,4]) if kind=='weekly' else list(range(7))
        if not days or any(type(d)!=int or not 0<=d<=6 for d in days):raise ValueError('星期须为0至6，周一为0')
        trigger=CronTrigger(hour=hour,minute=minute,day_of_week=','.join(map(str,days)),timezone=timezone)
    elif kind=='cron':
        from croniter import croniter
        expression=bounded(rule['expression'],100)
        if len(expression.split())!=5:raise ValueError('Cron须为五个字段：分 时 日 月 星期')
        try:return croniter(expression,current).get_next(datetime).isoformat()
        except (ValueError,KeyError):raise ValueError('Cron表达式不合法') from None
    else:raise ValueError('不支持的定时规则')
    result=trigger.get_next_fire_time(None,current+timedelta(seconds=1));return result.isoformat() if result else None

class SessionView:
    def __init__(self,hub,data):
        self.hub=hub;self.parent=hub.store;self.folder=self.parent.folder;self.lock=self.parent.lock;self.session_id=data['id']
        self.config=dict(self.parent.config,workspace=data['workspace'],workspace_id=data['workspace_id'],plan_mode=data['plan_mode']);self.history=list(data['history']);self.key=self.parent.key
        self.preferences=self.parent.preferences;self.agent_depth=0;self.job_id='';self.approve=None
    def remember(self,key,value):return self.parent.remember(key,value)
    def forget(self,key):return self.parent.forget(key)
