"""Xiaolong local Windows preview. Runtime artifacts live outside the project."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import secrets
import subprocess
import sys
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from data import Evidence, ROOT

ASSETS = Path(getattr(sys, '_MEIPASS', Path(__file__).parent))
RUNTIME = Path.home() / '.codex/tools/longshi-assistant-prototype/runtime-public'
VERSION = '0.6.0-public-synthetic'
VENDOR = ASSETS / 'vendor' if hasattr(sys, '_MEIPASS') else Path(os.environ.get('XIAOLONG_THREE_DIR', Path.home() / '.codex/tools/longshi-assistant-prototype/vendor/three-0.186.1/package'))


class LocalServer(ThreadingHTTPServer):
    daemon_threads = True
    def __init__(self, root=ROOT):
        super().__init__(('127.0.0.1', 0), Handler)
        self.token = secrets.token_urlsafe(24)
        self.origin = f'http://127.0.0.1:{self.server_port}'
        self.prefix = '/' + self.token + '/'
        self.evidence = Evidence(root)
        self.last_seen = time.monotonic()
        self.reload_lock = threading.Lock()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass  # no question / financial data in logs

    def reply(self, status, data, content_type='application/json; charset=utf-8'):
        raw = json.dumps(data, ensure_ascii=False).encode('utf-8') if content_type.startswith('application/json') else data
        self.send_response(status)
        self.send_header('Content-Type',content_type)
        self.send_header('Content-Length',str(len(raw)))
        self.send_header('Cache-Control','no-store')
        self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('Referrer-Policy','no-referrer')
        self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; connect-src 'self' blob:; frame-ancestors 'none'; base-uri 'none'; form-action 'none'")
        self.end_headers()
        self.wfile.write(raw)

    def allowed(self):
        host = self.headers.get('Host','')
        if host != self.server.origin.split('//')[1]:
            return False
        origin = self.headers.get('Origin')
        if origin and origin != self.server.origin:
            return False
        return urlsplit(self.path).path.startswith(self.server.prefix)

    def do_GET(self):
        if not self.allowed():
            return self.reply(403, {'error':'无效的本机会话'})
        path = urlsplit(self.path).path[len(self.server.prefix):]
        self.server.last_seen = time.monotonic()
        if path in ('','index.html'):
            return self.reply(200,(ASSETS/'ui.html').read_bytes(),'text/html; charset=utf-8')
        if path == 'character-generated.js':
            return self.reply(200,(ASSETS/path).read_bytes(),'text/javascript; charset=utf-8')
        if path == 'model-demo':
            return self.reply(200,(ASSETS/'model-viewer.html').read_bytes(),'text/html; charset=utf-8')
        if path in ('model-assets/xiaolong-gray.glb','model-assets/xiaolong-textured.glb','model-assets/xiaolong-parts.glb'):
            model = Path(os.environ.get('XIAOLONG_MODEL_DIR', Path.home()/'.codex/tools/longshi-assistant-prototype/private-model-assets'))/path.split('/')[-1]
            if not model.is_file():
                return self.reply(404,{'error':'模型尚未生成'})
            return self.reply(200,model.read_bytes(),'model/gltf-binary')
        vendor_files = {'vendor/three.module.js':'build/three.module.js',
                        'vendor/three.core.js':'build/three.core.js',
                        'vendor/RoomEnvironment.js':'examples/jsm/environments/RoomEnvironment.js',
                        'vendor/RoundedBoxGeometry.js':'examples/jsm/geometries/RoundedBoxGeometry.js',
                        'vendor/GLTFLoader.js':'examples/jsm/loaders/GLTFLoader.js',
                        'vendor/OrbitControls.js':'examples/jsm/controls/OrbitControls.js',
                        'utils/BufferGeometryUtils.js':'examples/jsm/utils/BufferGeometryUtils.js',
                        'utils/SkeletonUtils.js':'examples/jsm/utils/SkeletonUtils.js',
                        'vendor/LICENSE':'LICENSE'}
        if path in vendor_files:
            return self.reply(200,(VENDOR/vendor_files[path]).read_bytes(),
                              'text/javascript; charset=utf-8' if path.endswith('.js') else 'text/plain; charset=utf-8')
        if path == 'appearance-status':
            model = Path(os.environ.get('XIAOLONG_MODEL_DIR', Path.home()/'.codex/tools/longshi-assistant-prototype/private-model-assets'))/'xiaolong-parts.glb'
            return self.reply(200,{'available':model.is_file() and (VENDOR/'build/three.module.js').is_file()})
        if path == 'status':
            return self.reply(200,dict(self.server.evidence.status(),version=VERSION))
        if path.startswith('source/'):
            sid = path.split('/')[-1]
            source = self.server.evidence.sources.get(sid)
            if not source:
                return self.reply(404,{'error':'未知来源'})
            file = Path(source['path'])
            if not file.is_file():
                return self.reply(404,{'error':'来源文件已移走'})
            if hashlib.sha256(file.read_bytes()).hexdigest() != source['sha256']:
                return self.reply(409,{'error':'来源在本次读取后已变化，请先重新读取资料'})
            # Only curated Markdown is served inline, always rendered as text in the UI.
            text = file.read_text(encoding='utf-8-sig') if file.suffix.lower() == '.md' else ''
            return self.reply(200,{'name':source['name'],'path':'demo-data/' + file.name,
                'text':text,'status':source['status'],'sha256':source['sha256']})
        return self.reply(404,{'error':'页面不存在'})

    def do_POST(self):
        if not self.allowed():
            return self.reply(403,{'error':'无效的本机会话'})
        try:
            size = int(self.headers.get('Content-Length','0'))
            if size < 0 or size > 8192:
                return self.reply(413,{'error':'请求过长'})
            payload = json.loads(self.rfile.read(size) or '{}')
            if not isinstance(payload,dict):
                raise ValueError('请求应为对象')
            self.server.last_seen = time.monotonic()
            action = urlsplit(self.path).path[len(self.server.prefix):]
            if action == 'ask':
                q = payload.get('question','')
                if not isinstance(q,str):
                    raise ValueError('问题应为文字')
                return self.reply(200,self.server.evidence.ask(q))
            if action == 'ping':
                return self.reply(200,{'ok':True})
            if action == 'reload':
                with self.server.reload_lock:
                    replacement = Evidence(self.server.evidence.root)
                    self.server.evidence = replacement
                return self.reply(200,replacement.status())
            if action == 'open':
                sid = payload.get('id','')
                source = self.server.evidence.sources.get(sid)
                if not source:
                    return self.reply(404,{'error':'未知来源'})
                file = Path(source['path'])
                if file.suffix.lower() not in ('.md','.pdf','.xlsx') or not file.is_file():
                    return self.reply(400,{'error':'该来源当前不能打开'})
                if hashlib.sha256(file.read_bytes()).hexdigest() != source['sha256']:
                    return self.reply(409,{'error':'原件已变化，请先重新读取资料'})
                if os.name == 'nt':
                    os.startfile(str(file))
                return self.reply(200,{'ok':True})
            if action == 'quit':
                self.reply(200,{'ok':True})
                threading.Thread(target=self.server.shutdown,daemon=True).start()
                return
            return self.reply(404,{'error':'未知操作'})
        except (ValueError,TypeError,json.JSONDecodeError):
            return self.reply(400,{'error':'请求格式不正确'})
        except Exception:
            return self.reply(500,{'error':'本次读取未完成；没有修改原件。请重试或查看资料状态。'})


def edge_path():
    for base in ('PROGRAMFILES(X86)','PROGRAMFILES','LOCALAPPDATA'):
        folder = os.environ.get(base)
        if folder:
            candidate = Path(folder)/'Microsoft/Edge/Application/msedge.exe'
            if candidate.is_file():
                return candidate
    return None


def open_window(url):
    edge = edge_path()
    if edge:
        subprocess.Popen([str(edge), '--app='+url, '--window-size=1200,880',
            '--window-position=120,60','--no-first-run', '--no-default-browser-check',
            '--user-data-dir='+str(RUNTIME/'edge-profile')],
            creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    else:
        import webbrowser
        webbrowser.open(url)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--no-window',action='store_true')
    args = parser.parse_args()
    RUNTIME.mkdir(parents=True,exist_ok=True)
    pointer = RUNTIME/'current.json'
    if not args.no_window and pointer.is_file():
        try:
            previous = json.loads(pointer.read_text(encoding='utf-8'))
            with urllib.request.urlopen(previous['url']+'status',timeout=1) as response:
                old_status = json.load(response)
            if old_status.get('version') == VERSION:
                open_window(previous['url']+'#looks')
                return
        except Exception:
            pass
    server = LocalServer()
    url = server.origin + server.prefix
    pointer.write_text(json.dumps({'url':url,'pid':os.getpid()},ensure_ascii=False),encoding='utf-8')
    if not args.no_window:
        open_window(url+'#looks')
    def idle_exit():
        while True:
            time.sleep(30)
            if time.monotonic()-server.last_seen > 180:
                server.shutdown()
                return
    threading.Thread(target=idle_exit,daemon=True).start()
    try:
        server.serve_forever(poll_interval=.3)
    finally:
        server.server_close()
        try:
            if json.loads(pointer.read_text(encoding='utf-8')).get('pid') == os.getpid():
                pointer.unlink()
        except (OSError,ValueError):
            pass


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        if os.name == 'nt':
            import ctypes
            ctypes.windll.user32.MessageBoxW(0,'启动未完成：'+str(error),'小隆 · 本机试玩',0x10)
        else:
            raise
