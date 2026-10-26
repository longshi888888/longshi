"""Durable task receipts and a quiet local inbox; no enterprise authorization."""
import hashlib,inspect,json,time
from functools import wraps
from pathlib import Path
from hub import now

FINAL={'done','error','cancelled','interrupted'}
WRITES={'create_document','create_workbook','remember_preference','remember_note','forget_note','schedule_task','update_schedule','set_schedule_enabled','delete_schedule','run_python_batch'}

class Experience:
    def __init__(self,hub):
        self.hub=hub;self.db=hub.db;self.lock=hub.lock;self.last={}
        with self.lock,self.db:
            self.db.executescript('''CREATE TABLE IF NOT EXISTS task_snapshots(id TEXT PRIMARY KEY,session_id TEXT,state TEXT,updated TEXT,data TEXT);
            CREATE TABLE IF NOT EXISTS inbox(id TEXT PRIMARY KEY,job_id TEXT,session_id TEXT,state TEXT,title TEXT,body TEXT,created TEXT,unread INTEGER);
            CREATE TABLE IF NOT EXISTS write_receipts(chain TEXT,signature TEXT,state TEXT,data TEXT,PRIMARY KEY(chain,signature));''')
            rows=self.db.execute('SELECT data FROM task_snapshots WHERE state NOT IN (?,?,?,?)',tuple(FINAL)).fetchall()
            for row in rows:
                task=json.loads(row[0]);task.update(state='interrupted',message='上次程序关闭，任务中断；可核对已完成步骤后继续。',approval=None)
                self.save(task,force=True)
    def save(self,job,force=False):
        if not force and job['state']=='streaming' and time.monotonic()-self.last.get(job['id'],0)<.5:return
        data=json.dumps(job,ensure_ascii=False);self.last[job['id']]=time.monotonic()
        with self.lock,self.db:
            self.db.execute('INSERT OR REPLACE INTO task_snapshots VALUES(?,?,?,?,?)',(job['id'],job['session_id'],job['state'],now(),data))
            if job['state'] in FINAL|{'waiting'}:
                key=job['id']+':'+job['state'];title={'done':'已完成','error':'需要处理','cancelled':'已暂停' if job.get('paused') else '已停止','waiting':'待你确认','interrupted':'任务中断'}[job['state']]
                self.db.execute('INSERT OR IGNORE INTO inbox VALUES(?,?,?,?,?,?,?,1)',(key,job['id'],job['session_id'],job['state'],title,job['question'][:150],now()))
            if job['state']!='waiting':self.db.execute("UPDATE inbox SET unread=0 WHERE job_id=? AND state='waiting'",(job['id'],))
            self.db.execute('DELETE FROM inbox WHERE id NOT IN (SELECT id FROM inbox ORDER BY created DESC LIMIT 300)')
    def task(self,jid):
        with self.lock:row=self.db.execute('SELECT data FROM task_snapshots WHERE id=?',(jid,)).fetchone()
        if not row:raise ValueError('没有这项任务记录')
        return json.loads(row[0])
    def tasks(self,sid=None):
        with self.lock:rows=self.db.execute('SELECT data FROM task_snapshots WHERE (? IS NULL OR session_id=?) ORDER BY updated DESC,rowid DESC LIMIT 60',(sid,sid)).fetchall()
        return [json.loads(row[0]) for row in rows]
    def messages(self):
        with self.lock:rows=self.db.execute('SELECT * FROM inbox ORDER BY created DESC,rowid DESC LIMIT 150').fetchall()
        items=[dict(row) for row in rows];today=now()[:10]
        tasks=[j for j in self.tasks() if j.get('finished_at','').startswith(today)]
        return {'messages':items,'unread':sum(i['unread'] for i in items),'summary':{'done':sum(j['state']=='done' for j in tasks),'attention':sum(j['state'] in ('error','interrupted') for j in self.tasks()),'waiting':sum(j['state']=='waiting' for j in self.tasks())}}
    def read(self,mid=None):
        with self.lock,self.db:
            if mid:self.db.execute('UPDATE inbox SET unread=0 WHERE id=?',(mid,))
            else:self.db.execute('UPDATE inbox SET unread=0')
    def receipt(self,tools,function):
        if function.__name__ not in WRITES:return function
        signature=inspect.signature(function);chain=tools.store.recovery_chain
        @wraps(function)
        def call(*args,**kwargs):
            tools.check();bound=signature.bind(*args,**kwargs);bound.apply_defaults()
            key=hashlib.sha256(json.dumps([function.__name__,bound.arguments],sort_keys=True,ensure_ascii=False).encode()).hexdigest()
            with self.lock:
                row=self.db.execute('SELECT state,data FROM write_receipts WHERE chain=? AND signature=?',(chain,key)).fetchone()
            if row:
                if row['state']!='done':raise ValueError('上次同参数写入结果未确认，请先核对已有成果/记录，再调整任务，不能盲重试。')
                saved=json.loads(row['data'])
                for file in saved['artifacts']:
                    path=tools.output/file['name']
                    if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest()!=file['sha256']:raise ValueError('原已完成成果缺失或变化，无法直接复用，请核对后另行生成。')
                    if file['id'] not in {a['id'] for a in tools.artifacts}:tools.artifacts.append(file)
                step=tools.begin('复用已完成操作：'+function.__name__);tools.finish(step)
                return saved['result']
            with self.lock,self.db:self.db.execute('INSERT INTO write_receipts VALUES(?,?,?,?)',(chain,key,'pending','{}'))
            before={a['id'] for a in tools.artifacts}
            result=function(*args,**kwargs)
            # A refusal is not a successful side effect or a reusable approval.
            if isinstance(result,dict) and result.get('executed') is False:
                with self.lock,self.db:self.db.execute('DELETE FROM write_receipts WHERE chain=? AND signature=?',(chain,key))
                return result
            data={'result':result,'artifacts':[a for a in tools.artifacts if a['id'] not in before]}
            with self.lock,self.db:self.db.execute("UPDATE write_receipts SET state='done',data=? WHERE chain=? AND signature=?",(json.dumps(data,ensure_ascii=False),chain,key))
            return result
        return call

def quiet(config,current=None):
    from datetime import datetime
    if config.get('do_not_disturb'):return True
    if not config.get('quiet_hours'):return False
    minute=(current or datetime.now().astimezone()).strftime('%H:%M');start=config.get('quiet_start','22:00');end=config.get('quiet_end','08:00')
    return start<=minute<end if start<end else minute>=start or minute<end
