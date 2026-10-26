"""Private runtime files; secrets never enter the project or read-back API."""
from pathlib import Path
import ctypes
from ctypes import wintypes
import json
import os
import threading
import shutil
import uuid
from office_tools import prepare_demo,MEMORY_KEYS

RUNTIME=Path.home()/'.codex/tools/xiaolong-office-20261026/runtime'
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
        if self.folder==RUNTIME and not (self.folder/'settings.json').exists():
            legacy=Path.home()/'.codex/tools/xiaolong-agent-20261026/runtime'
            for name in ('settings.json','credential.bin','history.json'):
                if (legacy/name).is_file():shutil.copy2(legacy/name,self.folder/name)
        self.config={'base_url':'https://api.deepseek.com','model':'deepseek-flash','use_model':False,'nickname':'你','notifications':True,'pet_sound':False,'pet_size':100,'pet_activity':'normal','reduce_motion':False,'do_not_disturb':False,'quiet_hours':False,'quiet_start':'22:00','quiet_end':'08:00','auto_read':False}
        self.history=[];self.key=''
        try:self.config.update(json.loads((self.folder/'settings.json').read_text(encoding='utf-8')))
        except (OSError,ValueError):pass
        try:self.history=json.loads((self.folder/'history.json').read_text(encoding='utf-8'))[-20:]
        except (OSError,ValueError):pass
        try:
            credential=json.loads(protect((self.folder/'credential.bin').read_bytes(),True).decode('utf-8'))
            if credential['base_url'].rstrip('/')==self.config['base_url'].rstrip('/'):self.key=credential['api_key']
        except (OSError,ValueError,UnicodeDecodeError,KeyError,TypeError):pass
        self.preferences={}
        try:
            loaded=json.loads((self.folder/'preferences.json').read_text(encoding='utf-8'))
            self.preferences={k:v for k,v in loaded.items() if k in MEMORY_KEYS and isinstance(v,str) and len(v)<=500}
        except (OSError,ValueError,TypeError,AttributeError):pass
        demo=self.folder/'demo-workspace';prepare_demo(demo)
        needs_setup='workspace' not in self.config or 'workspace_id' not in self.config
        if not Path(self.config.get('workspace',str(demo))).is_dir():self.config['workspace']=str(demo)
        self.config.setdefault('workspace',str(demo));self.config.setdefault('workspace_id',uuid.uuid4().hex)
        if needs_setup:self._write('settings.json',self.config)
    def _write(self,name,obj):
        dest=self.folder/name;temp=dest.with_suffix('.tmp')
        temp.write_text(json.dumps(obj,ensure_ascii=False,indent=2),encoding='utf-8');temp.replace(dest)
    def public(self):return dict({k:self.config[k] for k in ('base_url','model','nickname','use_model','notifications','pet_sound','pet_size','pet_activity','reduce_motion','do_not_disturb','quiet_hours','quiet_start','quiet_end','auto_read')},key_configured=bool(self.key),workspace=self.config['workspace'],workspace_id=self.config['workspace_id'],workspace_is_demo=Path(self.config['workspace']).resolve()==(self.folder/'demo-workspace').resolve())
    def model_settings(self,payload):
        """Validate a draft without persisting or changing its bound credential."""
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
            for field in ('notifications','pet_sound','reduce_motion','do_not_disturb','quiet_hours','auto_read'):
                if field in payload:
                    if type(payload[field])!=bool:raise ValueError('界面开关须为布尔值')
                    config[field]=payload[field]
            for field in ('quiet_start','quiet_end'):
                if field in payload:
                    import re
                    if not isinstance(payload[field],str) or not re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d',payload[field]):raise ValueError('安静时间须为HH:MM')
                    config[field]=payload[field]
            if 'pet_size' in payload:
                if type(payload['pet_size'])!=int or not 70<=payload['pet_size']<=140:raise ValueError('角色大小须为70至140')
                config['pet_size']=payload['pet_size']
            if 'pet_activity' in payload:
                if payload['pet_activity'] not in ('quiet','normal','lively'):raise ValueError('活跃程度无效')
                config['pet_activity']=payload['pet_activity']
            # Validate the address before retaining a credential for it.
            from urllib.parse import urlsplit
            url=urlsplit(config['base_url'])
            if url.scheme!='https' and not (url.scheme=='http' and url.hostname in ('127.0.0.1','localhost')):raise ValueError('API地址必须使用HTTPS')
            if not url.hostname or url.username or url.password or url.query or url.fragment:raise ValueError('API地址格式不合法')
            if url.hostname=='api.deepseek.com':
                alias=''.join(c for c in config['model'].lower() if c.isalnum())
                if alias in ('deepseekv41flash','deepseekv41flash1017','deepseekv4flash'):config['model']='deepseek-flash'
                elif alias=='deepseekv4pro':config['model']='deepseek-v4-pro'
            key=self.key
            if payload.get('clear_key'):
                key=''
            elif payload.get('api_key'):
                if not isinstance(payload['api_key'],str) or len(payload['api_key'])>1000:raise ValueError('密钥格式不合法')
                key=payload['api_key'].strip()
            elif config['base_url'].rstrip('/')!=self.config['base_url'].rstrip('/') and key:
                raise ValueError('更换API地址时请重新填写密钥，避免把旧密钥发送给新服务')
            if config['use_model'] and not key:raise ValueError('启用模型前请在软件中填写自己的API密钥')
            return config,key
    def save(self,payload):
        with self.lock:
            config,key=self.model_settings(payload)
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
    def choose_workspace(self,path):
        if not isinstance(path,str) or not path.strip() or len(path)>800 or not Path(path).is_absolute():raise ValueError('请选择有效的工作文件夹绝对路径')
        folder=Path(path).resolve()
        if not folder.is_dir() or folder==Path(folder.anchor):raise ValueError('请选择具体的办公文件夹，不能选择整个磁盘')
        with self.lock:
            self.config.update(workspace=str(folder),workspace_id=uuid.uuid4().hex)
            self._write('settings.json',self.config)
        return self.public()
    def remember(self,key,value):
        with self.lock:self.preferences[key]=value;self._write('preferences.json',self.preferences)
    def forget(self,key):
        with self.lock:self.preferences.pop(key,None);self._write('preferences.json',self.preferences)
