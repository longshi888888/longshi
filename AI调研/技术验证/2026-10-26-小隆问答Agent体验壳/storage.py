"""Private runtime files; secrets never enter the project or read-back API."""
from pathlib import Path
import ctypes
from ctypes import wintypes
import json
import os
import threading

RUNTIME=Path.home()/'.codex/tools/xiaolong-agent-20261026/runtime'
class Blob(ctypes.Structure):
    _fields_=[('size',wintypes.DWORD),('data',ctypes.POINTER(ctypes.c_ubyte))]

def protect(raw,decrypt=False):
    if os.name!='nt':raise ValueError('当前密钥保管实现仅支持Windows')
    buffer=ctypes.create_string_buffer(raw);source=Blob(len(raw),ctypes.cast(buffer,ctypes.POINTER(ctypes.c_ubyte)));dest=Blob()
    crypt=ctypes.WinDLL('crypt32',use_last_error=True)
    fn=crypt.CryptUnprotectData if decrypt else crypt.CryptProtectData
    fn.argtypes=[ctypes.POINTER(Blob),ctypes.c_void_p if decrypt else ctypes.c_wchar_p,ctypes.c_void_p,ctypes.c_void_p,ctypes.c_void_p,wintypes.DWORD,ctypes.POINTER(Blob)]
    fn.restype=wintypes.BOOL
    if decrypt:ok=fn(ctypes.byref(source),None,None,None,None,1,ctypes.byref(dest))
    else:ok=fn(ctypes.byref(source),'Xiaolong API credential',None,None,None,1,ctypes.byref(dest))
    if not ok:raise ValueError('Windows密钥保管失败')
    try:return ctypes.string_at(dest.data,dest.size)
    finally:
        free=ctypes.WinDLL('kernel32').LocalFree;free.argtypes=[ctypes.c_void_p];free(ctypes.cast(dest.data,ctypes.c_void_p))

class Store:
    def __init__(self,folder=RUNTIME):
        self.folder=Path(folder);self.folder.mkdir(parents=True,exist_ok=True);self.lock=threading.RLock()
        self.config={'base_url':'https://api.deepseek.com','model':'deepseek-flash','use_model':False,'nickname':'你'}
        self.history=[];self.key=''
        try:self.config.update(json.loads((self.folder/'settings.json').read_text(encoding='utf-8')))
        except (OSError,ValueError):pass
        try:self.history=json.loads((self.folder/'history.json').read_text(encoding='utf-8'))[-20:]
        except (OSError,ValueError):pass
        try:
            credential=json.loads(protect((self.folder/'credential.bin').read_bytes(),True).decode('utf-8'))
            if credential['base_url'].rstrip('/')==self.config['base_url'].rstrip('/'):self.key=credential['api_key']
        except (OSError,ValueError,UnicodeDecodeError,KeyError,TypeError):pass
    def _write(self,name,obj):
        dest=self.folder/name;temp=dest.with_suffix('.tmp')
        temp.write_text(json.dumps(obj,ensure_ascii=False,indent=2),encoding='utf-8');temp.replace(dest)
    def public(self):return dict({k:self.config[k] for k in ('base_url','model','nickname','use_model')},key_configured=bool(self.key))
    def save(self,payload):
        with self.lock:
            if not isinstance(payload,dict):raise ValueError('设置必须是对象')
            config=dict(self.config)
            for field,maximum in [('base_url',300),('model',100),('nickname',40)]:
                if field in payload:
                    value=payload[field]
                    if not isinstance(value,str) or not value.strip() or len(value)>maximum:raise ValueError('设置字段不合法')
                    config[field]=value.strip()
            if 'use_model' in payload:
                if not isinstance(payload['use_model'],bool):raise ValueError('模型开关必须是布尔值')
                config['use_model']=payload['use_model']
            # Validate the address before retaining a credential for it.
            from urllib.parse import urlsplit
            url=urlsplit(config['base_url'])
            if url.scheme!='https' and not (url.scheme=='http' and url.hostname in ('127.0.0.1','localhost')):raise ValueError('API地址必须使用HTTPS')
            if not url.hostname or url.username or url.password or url.query or url.fragment:raise ValueError('API地址格式不合法')
            key=self.key
            if payload.get('clear_key'):
                key=''
            elif payload.get('api_key'):
                if not isinstance(payload['api_key'],str) or len(payload['api_key'])>1000:raise ValueError('密钥格式不合法')
                key=payload['api_key'].strip()
            elif config['base_url'].rstrip('/')!=self.config['base_url'].rstrip('/') and key:
                raise ValueError('更换API地址时请重新填写密钥，避免把旧密钥发送给新服务')
            if config['use_model'] and not key:raise ValueError('启用模型前请在软件中填写自己的API密钥')
            # Bind the encrypted key to its destination; interrupted disk writes cannot
            # silently reuse a credential with a different provider on the next launch.
            if key:
                encrypted=protect(json.dumps({'api_key':key,'base_url':config['base_url']}).encode())
                temp=self.folder/'credential.tmp';temp.write_bytes(encrypted);temp.replace(self.folder/'credential.bin')
            self._write('settings.json',config)
            if not key:(self.folder/'credential.bin').unlink(missing_ok=True)
            self.config=config;self.key=key
        return self.public()
    def append(self,item):
        with self.lock:self.history=(self.history+[item])[-20:];self._write('history.json',self.history)
    def clear(self):
        with self.lock:self.history=[];self._write('history.json',[])
