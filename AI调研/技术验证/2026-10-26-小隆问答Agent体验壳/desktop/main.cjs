const {app,BrowserWindow,ipcMain,Menu,session,screen}=require('electron');
const path=require('path');
const fs=require('fs');const os=require('os');
const argument=process.argv.find(a=>a.startsWith('--xl-url='));
if(!argument)throw Error('Missing local session');
const base=argument.slice('--xl-url='.length),origin=new URL(base).origin;
if(new URL(base).hostname!=='127.0.0.1'||!base.endsWith('/'))throw Error('Only a local session is allowed');
const runtime=path.join(os.homedir(),'.codex/tools/xiaolong-agent-20261026/runtime');
app.setPath('userData',path.join(runtime,'electron-profile'));
let pet,panel,quitting=false;
function secure(win){
 win.webContents.setWindowOpenHandler(()=>({action:'deny'}));
 win.webContents.on('will-navigate',(event,url)=>{if(!url.startsWith(base))event.preventDefault()});
 win.webContents.session.setPermissionRequestHandler((contents,permission,callback)=>callback(false));
}
function showPanel(){if(panel){panel.show();panel.focus();}}
function record(){fs.mkdirSync(runtime,{recursive:true});fs.writeFileSync(path.join(runtime,'desktop-state.json'),JSON.stringify({version:app.getVersion(),pet:pet?.getBounds(),panel:panel?.getBounds(),transparentRequested:true,backgroundColor:pet?.getBackgroundColor(),onTop:pet?.isAlwaysOnTop()},null,2));}
app.whenReady().then(()=>{
 session.defaultSession.webRequest.onBeforeRequest((details,callback)=>{
  const allowed=details.url.startsWith(base)||details.url.startsWith('blob:'+origin+'/')||details.url.startsWith('devtools:');callback({cancel:!allowed});
 });
 const work=screen.getPrimaryDisplay().workArea;
 const settings={preload:path.join(__dirname,'preload.cjs'),contextIsolation:true,nodeIntegration:false,sandbox:true,backgroundThrottling:true};
 pet=new BrowserWindow({title:'小隆 · 桌面伙伴',width:300,height:410,x:work.x+work.width-330,y:work.y+work.height-430,
  transparent:true,frame:false,hasShadow:false,resizable:false,alwaysOnTop:true,show:false,backgroundColor:'#00000000',webPreferences:settings});
 panel=new BrowserWindow({title:'小隆 · 公司问答体验',width:900,height:820,minWidth:720,minHeight:650,show:false,backgroundColor:'#f5f4ef',webPreferences:settings});
 secure(pet);secure(panel);pet.setMenu(null);panel.setMenu(null);
 pet.loadURL(base+'pet.html');panel.loadURL(base+'panel.html');
 pet.once('ready-to-show',()=>{pet.show();record()});pet.on('moved',record);
 panel.on('close',event=>{if(!quitting){event.preventDefault();panel.hide()}});
 pet.on('closed',()=>{quitting=true;app.quit()});
 pet.webContents.on('context-menu',()=>Menu.buildFromTemplate([
  {label:'和小隆聊聊 / 查业务',click:showPanel},
  {label:'始终置顶',type:'checkbox',checked:pet.isAlwaysOnTop(),click:item=>{pet.setAlwaysOnTop(item.checked);record()}},
  {type:'separator'},{label:'退出小隆',click:()=>{quitting=true;app.quit()}}
 ]).popup({window:pet}));
 ipcMain.handle('xl:action',(event,action,value)=>{
  if(![pet.webContents,panel.webContents].includes(event.sender)||!event.sender.getURL().startsWith(base))throw Error('Invalid window');
  if(action==='open-panel'){showPanel();return true}
  if(action==='hide-panel'){panel.hide();return true}
  if(action==='pin'){pet.setAlwaysOnTop(!pet.isAlwaysOnTop());record();return pet.isAlwaysOnTop()}
  if(action==='passthrough'&&event.sender===pet.webContents){pet.setIgnoreMouseEvents(Boolean(value),{forward:true});return true}
  if(action==='quit'){quitting=true;app.quit();return true}
  throw Error('Unknown action');
 });
});
app.on('before-quit',()=>{quitting=true});app.on('window-all-closed',()=>app.quit());
