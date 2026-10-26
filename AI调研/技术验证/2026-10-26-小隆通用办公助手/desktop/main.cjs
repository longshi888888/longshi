const {app,BrowserWindow,ipcMain,Menu,session,screen,dialog,shell,Notification}=require('electron');
const path=require('path');
const fs=require('fs');const os=require('os');
const argument=process.argv.find(a=>a.startsWith('--xl-url='));
if(!argument)throw Error('Missing local session');
const base=argument.slice('--xl-url='.length),origin=new URL(base).origin;
if(new URL(base).hostname!=='127.0.0.1'||!base.endsWith('/'))throw Error('Only a local session is allowed');
const runtimeRoot=path.join(os.homedir(),'.codex/tools/xiaolong-office-20261026/runtime');
const runtimeArg=process.argv.find(a=>a.startsWith('--xl-runtime='));const runtime=runtimeArg?path.resolve(runtimeArg.slice('--xl-runtime='.length)):runtimeRoot;
if(runtime!==runtimeRoot&&!runtime.startsWith(runtimeRoot+path.sep))throw Error('Runtime must stay within Xiaolong local data');
app.setPath('userData',path.join(runtime,'electron-profile'));
let pet,panel,quick,hatGame,dragStart=null,quitting=false;
app.setAppUserModelId('com.longshi.xiaolong.office');let lastPetSize=100;const notified=new Set();
function notify(title,body){if(!Notification.isSupported())throw Error('当前系统未提供桌面通知');const notification=new Notification({title,body,silent:true});notification.on('click',showPanel);notification.show();return true}
function secure(win){
 win.webContents.setWindowOpenHandler(()=>({action:'deny'}));
 win.webContents.on('will-navigate',(event,url)=>{if(!url.startsWith(base))event.preventDefault()});
 win.webContents.session.setPermissionRequestHandler((contents,permission,callback,details)=>callback(permission==='media'&&[panel?.webContents,quick?.webContents].includes(contents)&&contents.getURL().startsWith(base)&&details.mediaTypes?.every(t=>t==='audio')));
 win.webContents.session.setPermissionCheckHandler((contents,permission)=>permission==='media'&&[panel?.webContents,quick?.webContents].includes(contents)&&contents.getURL().startsWith(base));
}
function showPanel(){if(panel){quick?.hide();panel.show();panel.focus();}}
function showQuick(){if(!quick)return;const p=pet.getBounds(),work=screen.getDisplayMatching(p).workArea,b=quick.getBounds();let x=p.x-b.width+20;if(x<work.x)x=p.x+p.width-20;x=Math.max(work.x,Math.min(x,work.x+work.width-b.width));const y=Math.max(work.y,Math.min(p.y+15,work.y+work.height-b.height));quick.setPosition(x,y);quick.show();quick.focus();quick.webContents.send('xl:pet-feedback',{kind:'focus'});}
function record(){fs.mkdirSync(runtime,{recursive:true});fs.writeFileSync(path.join(runtime,'desktop-state.json'),JSON.stringify({version:app.getVersion(),pet:pet?.getBounds(),panel:panel?.getBounds(),transparentRequested:true,backgroundColor:pet?.getBackgroundColor(),onTop:pet?.isAlwaysOnTop()},null,2));}
app.whenReady().then(()=>{
 session.defaultSession.webRequest.onBeforeRequest((details,callback)=>{
  const allowed=details.url.startsWith(base)||details.url.startsWith('blob:'+origin+'/')||details.url.startsWith('devtools:');callback({cancel:!allowed});
 });
 const work=screen.getPrimaryDisplay().workArea;
 let placement={width:300,height:410,x:work.x+work.width-330,y:work.y+work.height-430};
 try{const saved=JSON.parse(fs.readFileSync(path.join(runtime,'desktop-state.json'),'utf8')).pet;if(saved&&['x','y','width','height'].every(k=>Number.isFinite(saved[k]))&&saved.width>=210&&saved.width<=420){const area=screen.getDisplayMatching(saved).workArea;placement={width:saved.width,height:saved.height,x:Math.max(area.x-saved.width+70,Math.min(saved.x,area.x+area.width-70)),y:Math.max(area.y,Math.min(saved.y,area.y+area.height-70))};lastPetSize=Math.round(saved.width/3)}}catch{}
 const settings={preload:path.join(__dirname,'preload.cjs'),contextIsolation:true,nodeIntegration:false,sandbox:true,backgroundThrottling:true};
 pet=new BrowserWindow({title:'小隆 · 桌面伙伴',...placement,
  transparent:true,frame:false,hasShadow:false,resizable:false,alwaysOnTop:true,show:false,backgroundColor:'#00000000',webPreferences:settings});
 panel=new BrowserWindow({title:'小隆 · 办公工作台',width:Math.min(1380,work.width-60),height:Math.min(900,work.height-50),minWidth:820,minHeight:650,show:false,backgroundColor:'#f2f4f1',webPreferences:settings});
 quick=new BrowserWindow({title:'小隆随手聊',width:370,height:445,frame:false,transparent:true,hasShadow:false,resizable:false,alwaysOnTop:true,show:false,backgroundColor:'#00000000',webPreferences:settings});
 hatGame=require('./hat.cjs')({BrowserWindow,app,screen,base,settings,pet,quick,record});
 secure(pet);secure(panel);secure(quick);secure(hatGame.window);pet.setMenu(null);panel.setMenu(null);quick.setMenu(null);
 pet.loadURL(base+'pet.html');panel.loadURL(base+'panel.html');quick.loadURL(base+'quick.html');
 pet.once('ready-to-show',()=>{pet.show();record()});pet.on('moved',()=>{if(!hatGame||hatGame.state().phase==='home')record()});
 panel.on('close',event=>{if(!quitting){event.preventDefault();panel.hide()}});
 panel.on('hide',()=>panel.webContents.send('xl:pet-feedback',{kind:'panel-hide'}));
 quick.on('close',event=>{if(!quitting){event.preventDefault();quick.hide()}});
 quick.on('hide',()=>quick.webContents.send('xl:pet-feedback',{kind:'hide'}));
 pet.on('closed',()=>{quitting=true;app.quit()});
 pet.webContents.on('context-menu',()=>Menu.buildFromTemplate([
  {label:'打开办公助手',click:showPanel},
  {label:'让小隆捡回帽子',click:()=>hatGame.retrieve()},
  {label:'始终置顶',type:'checkbox',checked:pet.isAlwaysOnTop(),click:item=>{pet.setAlwaysOnTop(item.checked);record()}},
  {type:'separator'},{label:'退出小隆',click:()=>{quitting=true;app.quit()}}
 ]).popup({window:pet}));
 ipcMain.handle('xl:action',async(event,action,value)=>{
  if(![pet.webContents,panel.webContents,quick.webContents,hatGame.window.webContents].includes(event.sender)||!event.sender.getURL().startsWith(base))throw Error('Invalid window');
  if(action.startsWith('hat-'))return hatGame.handle(event.sender,action,value);
  if(action==='open-panel'){showPanel();return true}
  if(action==='open-quick'){showQuick();return true}
  if(action==='hide-quick'){quick.hide();return true}
  if(action==='pet-reply'&&event.sender===quick.webContents){pet.webContents.send('xl:pet-feedback',{kind:'reply',text:String(value).slice(0,100)});return true}
  if(action==='pet-activity'&&[panel.webContents,quick.webContents].includes(event.sender)&&['idle','listening','speaking'].includes(value)){pet.webContents.send('xl:pet-feedback',{kind:'activity',state:value});if(value!=='idle')for(const win of [panel,quick])if(win.webContents!==event.sender)win.webContents.send('xl:pet-feedback',{kind:'speech-stop'});return true}
  if(action==='pet-drag-start'&&event.sender===pet.webContents){dragStart=pet.getBounds();hatGame.pausePet(true);pet.setIgnoreMouseEvents(false);return true}
  if(action==='pet-drag-move'&&event.sender===pet.webContents&&dragStart){const dx=Number(value?.dx),dy=Number(value?.dy);if(!Number.isFinite(dx)||!Number.isFinite(dy)||Math.abs(dx)>20000||Math.abs(dy)>20000)return false;quick.hide();const target={x:dragStart.x+Math.round(dx),y:dragStart.y+Math.round(dy)},area=screen.getDisplayNearestPoint(target).workArea;pet.setPosition(Math.max(area.x-dragStart.width+70,Math.min(target.x,area.x+area.width-70)),Math.max(area.y,Math.min(target.y,area.y+area.height-70)));return true}
  if(action==='pet-drag-end'&&event.sender===pet.webContents){dragStart=null;hatGame.pausePet(false);record();return true}
  if(action==='hide-panel'){panel.hide();return true}
  if(action==='test-notification'&&event.sender===panel.webContents)return notify('小隆办公助手','这是桌面通知测试，点击可以回到工作台。');
  if(action==='open-external'&&[panel.webContents,quick.webContents].includes(event.sender)){const url=new URL(String(value));if(!['https:','http:'].includes(url.protocol)||url.username||url.password)throw Error('仅支持普通网页链接');await shell.openExternal(url.href);return true}
  if(action==='choose-folder'){const result=await dialog.showOpenDialog(panel,{title:'选择小隆可以读取的办公资料文件夹',properties:['openDirectory'],buttonLabel:'使用这个文件夹'});return result.canceled?null:result.filePaths[0];}
  if(action==='pin'){pet.setAlwaysOnTop(!pet.isAlwaysOnTop());record();return pet.isAlwaysOnTop()}
  if(action==='passthrough'&&event.sender===pet.webContents){pet.setIgnoreMouseEvents(Boolean(value),{forward:true});return true}
  if(action==='quit'){quitting=true;app.quit();return true}
  throw Error('Unknown action');
 });
 const poll=setInterval(async()=>{try{const response=await fetch(base+'status');const state=await response.json(),options=state.settings;if(options.pet_size!==lastPetSize){const bounds=pet.getBounds(),ratio=options.pet_size/100,width=Math.round(300*ratio),height=Math.round(410*ratio);pet.setBounds({x:bounds.x+Math.round((bounds.width-width)/2),y:bounds.y+bounds.height-height,width,height});lastPetSize=options.pet_size;record()}for(const job of state.jobs||[]){if(!['done','error','cancelled','waiting'].includes(job.state))continue;const key=job.id+':'+job.state;if(notified.has(key))continue;notified.add(key);if(!options.notifications||state.quiet)continue;if((!panel.isVisible()||panel.isMinimized())&&!quick.isVisible()){notify(job.state==='waiting'?'小隆在等你确认':job.state==='error'?'小隆的任务未完成':job.state==='cancelled'?'小隆已停止任务':'小隆处理好了',job.question.slice(0,80))}}}catch{}},1200);app.on('before-quit',()=>clearInterval(poll));
});
app.on('before-quit',()=>{quitting=true});app.on('window-all-closed',()=>app.quit());
