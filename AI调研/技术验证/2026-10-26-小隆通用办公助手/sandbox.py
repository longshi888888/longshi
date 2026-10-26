"""WASI Python: only staged copies and output folder, no host shell/network."""
from pathlib import Path
import threading,time,tempfile,hashlib,io,csv

def run_python(code,files,tools,runtime,timeout=25):
    import wasmtime
    runtime=Path(runtime)
    if not (runtime/'python.wasm').is_file():raise ValueError('受限Python运行环境未就绪')
    if not isinstance(code,str) or not code.strip() or len(code)>20000:raise ValueError('脚本须为1至20000字')
    if not isinstance(files,list) or len(files)>20:raise ValueError('一次最多20个输入文件')
    config=wasmtime.Config();config.epoch_interruption=True;engine=wasmtime.Engine(config)
    cache=tools.store.folder/'sandbox-cache';cache.mkdir(exist_ok=True)
    key=hashlib.sha256((runtime/'python.wasm').read_bytes()).hexdigest()[:16];compiled=cache/(key+'.cwasm')
    try:module=wasmtime.Module.deserialize(engine,compiled.read_bytes())
    except Exception:
        module=wasmtime.Module.from_file(engine,str(runtime/'python.wasm'));compiled.write_bytes(module.serialize())
    with tempfile.TemporaryDirectory(dir=tools.store.folder,prefix='script-') as temp:
        work=Path(temp);inputs=work/'input';outputs=work/'output';inputs.mkdir();outputs.mkdir();size=0
        for relative in files:
            tools.check();file=tools.path(relative)
            if not file.is_file() or file.suffix.lower() not in ('.txt','.md','.csv','.json','.xlsx','.docx','.pdf'):raise ValueError('输入须为支持的办公资料')
            size+=file.stat().st_size
            if size>20_000_000:raise ValueError('脚本输入总量超过20MB')
            target=inputs/relative;target.parent.mkdir(parents=True,exist_ok=True);raw=file.read_bytes();target.write_bytes(raw)
            reference=tools._reference(file,'受限脚本输入副本')
            if reference['sha256']!=hashlib.sha256(raw).hexdigest():raise ValueError('输入文件复制时已变化，请重新读取')
        tools.stage('working','输入副本已核对，正在执行受限脚本',{'sources':list(tools.sources.values()),'steps':list(tools.trace),'artifacts':list(tools.artifacts)})
        (work/'main.py').write_text(code,encoding='utf-8');captured=bytearray();errors=bytearray()
        def collect(buffer,data):
            if len(buffer)<64000:buffer.extend(data[:64000-len(buffer)])
            return len(data)
        wasi=wasmtime.WasiConfig();wasi.argv=['python','-S','-B','/work/main.py'];wasi.env=[('PYTHONHOME','/runtime'),('PYTHONUTF8','1')]
        wasi.preopen_dir(str(runtime),'/runtime',fs_mutable=False);wasi.preopen_dir(str(work),'/work',fs_mutable=True)
        wasi.stdout_custom=lambda data:collect(captured,data);wasi.stderr_custom=lambda data:collect(errors,data)
        store=wasmtime.Store(engine);store.set_wasi(wasi);store.set_limits(memory_size=256*1024*1024);store.set_epoch_deadline(1)
        finished=threading.Event();interrupted=[]
        def watchdog():
            deadline=time.monotonic()+timeout
            while not finished.wait(.05):
                try:
                    entries=list(work.rglob('*'));too_large=len(entries)>1200 or sum(p.stat().st_size for p in entries if p.is_file() and not p.is_symlink())>40_000_000
                except OSError:too_large=True
                if tools.stop.is_set() or time.monotonic()>deadline or too_large:
                    interrupted.append(True);engine.increment_epoch();return
        thread=threading.Thread(target=watchdog,daemon=True);thread.start();exit_code=0
        try:
            linker=wasmtime.Linker(engine);linker.define_wasi();instance=linker.instantiate(store,module);instance.exports(store)['_start'](store)
        except wasmtime.ExitTrap as error:exit_code=error.code
        except wasmtime.Trap:
            if tools.stop.is_set():raise InterruptedError('脚本已停止') from None
            raise ValueError('脚本达到时间/内存限制或运行被中止') from None
        finally:
            finished.set();thread.join(1);store.close();linker.close();module.close();engine.close()
        artifacts=[];total=0
        for file in outputs.iterdir():
            if not file.is_file() or file.suffix.lower() not in ('.md','.txt','.csv','.json'):continue
            if file.is_symlink() or not file.resolve().is_relative_to(outputs.resolve()):raise ValueError('不收集指向输出目录以外的链接')
            if len(artifacts)>=10:break
            raw=file.read_bytes();total+=len(raw)
            if total>10_000_000:raise ValueError('脚本输出超过10MB')
            if file.suffix.lower()=='.csv':
                source=io.StringIO(raw.decode('utf-8-sig'));target=io.StringIO();writer=csv.writer(target)
                for row in csv.reader(source):writer.writerow(["'"+cell if cell.startswith(('=','+','-','@')) else cell for cell in row])
                raw=target.getvalue().encode('utf-8-sig')
            artifacts.append(tools._save(file.stem,file.suffix.lower(),raw))
        return {'exit_code':exit_code,'stdout':captured.decode('utf-8',errors='replace'),'stderr':errors.decode('utf-8',errors='replace'),'artifacts':artifacts,'isolation':'WASI；仅输入副本与输出目录，无宿主Shell或网络，256MB内存/25秒'}
