"""Opt-in microphone PCM recognition, entirely offline."""
from pathlib import Path
import threading,json,uuid,time,os

class NativeModelPath(str):
    # The pinned Windows Vosk binary uses ANSI fopen for model paths, while
    # its Python wrapper assumes UTF-8. Respect the actual Windows code page.
    def encode(self,encoding='utf-8',errors='strict'):return str(self).encode('mbcs' if os.name=='nt' else encoding,errors)

class Voice:
    def __init__(self,model_root):self.root=Path(model_root);self.lock=threading.RLock();self.model=None;self.recognizers={}
    def available(self):return (self.root/'vosk-model-small-cn-0.22/am/final.mdl').is_file()
    def start(self):
        if not self.available():raise ValueError('本机离线中文识别模型未安装')
        from vosk import Model,KaldiRecognizer,SetLogLevel
        SetLogLevel(-1)
        with self.lock:
            self.recognizers={k:v for k,v in self.recognizers.items() if time.monotonic()-v['time']<120}
            if len(self.recognizers)>=2:raise ValueError('请先停止当前录音')
            if self.model is None:self.model=Model(NativeModelPath(str(self.root/'vosk-model-small-cn-0.22')))
            sid=uuid.uuid4().hex;self.recognizers[sid]={'recognizer':KaldiRecognizer(self.model,16000),'text':'','time':time.monotonic(),'bytes':0}
        return {'id':sid,'sample_rate':16000,'offline':True}
    def push(self,sid,pcm=b'',final=False):
        if len(pcm)>16000 or len(pcm)%2:raise ValueError('音频片段须为16kHz单声道PCM16')
        with self.lock:
            item=self.recognizers.get(sid)
            if not item:raise ValueError('录音已结束或不存在')
            item['bytes']+=len(pcm)
            if item['bytes']>16000*2*90 or time.monotonic()-item['time']>120:
                del self.recognizers[sid];raise ValueError('单次录音最多90秒')
            recognizer=item['recognizer']
            if pcm and recognizer.AcceptWaveform(pcm):item['text']+=json.loads(recognizer.Result()).get('text','').replace(' ','')
            if final:
                text=item['text']+json.loads(recognizer.FinalResult()).get('text','').replace(' ','');del self.recognizers[sid]
            else:text=item['text']+json.loads(recognizer.PartialResult()).get('partial','').replace(' ','')
        return {'text':text,'final':final,'offline':True}
