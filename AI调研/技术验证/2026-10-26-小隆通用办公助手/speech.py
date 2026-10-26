"""Local Windows voice rendering through a fixed worker, never shell interpolation."""
from pathlib import Path
import json,os,subprocess,threading,uuid

class Speech:
    def __init__(self,folder,worker):
        self.folder=Path(folder);self.folder.mkdir(parents=True,exist_ok=True);self.worker=Path(worker);self.lock=threading.RLock();self.jobs={};self.processes={}
        for path in self.folder.glob('*.wav'):
            try:path.unlink()
            except OSError:pass
    def start(self,text):
        if not isinstance(text,str) or not text.strip() or len(text)>1800:raise ValueError('朗读文字须为1至1800字')
        self.stop()
        jid=uuid.uuid4().hex;dest=self.folder/(jid+'.wav')
        with self.lock:
            item={'id':jid,'state':'generating','message':'正在准备本机朗读音频'};self.jobs[jid]=item
            if len(self.jobs)>20:self.jobs.pop(next(iter(self.jobs)))
        def render():
            process=None
            try:
                executable=Path(os.environ.get('SystemRoot','C:/Windows'))/'System32/WindowsPowerShell/v1.0/powershell.exe'
                with self.lock:
                    if item['state']=='cancelled':return
                    process=subprocess.Popen([str(executable),'-NoLogo','-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass','-File',str(self.worker)],stdin=subprocess.PIPE,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0));self.processes[jid]=process
                process.communicate(json.dumps({'text':text,'output':str(dest)},ensure_ascii=False).encode('utf-8'),timeout=40)
                with self.lock:
                    if item['state']=='cancelled':return
                    if process.returncode or not dest.exists() or dest.stat().st_size<100:raise ValueError('没有可用的本机中文音色，请检查Windows语音设置')
                    item.update(state='ready',message='本机音频已准备好',url='tts/audio/'+jid)
            except Exception as error:
                if process and process.poll() is None:process.kill();process.wait()
                with self.lock:
                    if item['state']!='cancelled':item.update(state='error',message=str(error) if isinstance(error,ValueError) else '本机朗读未能生成，请检查Windows中文音色')
            finally:
                with self.lock:self.processes.pop(jid,None)
                if item['state']!='ready':dest.unlink(missing_ok=True)
        threading.Thread(target=render,daemon=True).start();return dict(item)
    def status(self,jid):
        with self.lock:
            if jid not in self.jobs:raise ValueError('没有这次朗读')
            return dict(self.jobs[jid])
    def audio(self,jid):
        item=self.status(jid)
        if item['state']!='ready':raise ValueError('音频尚未准备好')
        return (self.folder/(jid+'.wav')).read_bytes()
    def stop(self):
        with self.lock:
            for item in self.jobs.values():
                if item['state'] in ('generating','ready'):item.update(state='cancelled',message='朗读已停止')
            for process in self.processes.values():
                if process.poll() is None:process.terminate()
