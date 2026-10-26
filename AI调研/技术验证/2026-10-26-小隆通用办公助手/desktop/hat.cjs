// A small native 3D hat window; physics and retrieval stay inside desktop work areas.
const path=require('path');
module.exports=function createHat({BrowserWindow,app,screen,base,settings,pet,quick,record}){
 const win=new BrowserWindow({title:'小隆的安全帽',width:170,height:132,frame:false,transparent:true,alwaysOnTop:true,resizable:false,hasShadow:false,show:false,backgroundColor:'#00000000',webPreferences:settings});win.setMenu(null);win.loadURL(base+'hat.html');
 let phase='home',home=null,offset={x:85,y:66},samples=[],velocity={x:0,y:0},position={x:0,y:0},since=0,last=Date.now(),spin=0,scale=1,paused=false,petDragAnchor=null,pickStart=null,petLastPhase='';
 const finite=n=>typeof n==='number'&&Number.isFinite(n)&&Math.abs(n)<100000;
 function area(point){return screen.getDisplayNearestPoint({x:Math.round(point.x),y:Math.round(point.y)}).workArea}
 function bounded(point,w,h){const a=area({x:point.x+w/2,y:point.y+h/2});return {x:Math.max(a.x,Math.min(point.x,a.x+a.width-w)),y:Math.max(a.y,Math.min(point.y,a.y+a.height-h))}}
 function feedback(force=false){if(force||phase!==petLastPhase){petLastPhase=phase;pet.webContents.send('xl:pet-feedback',{kind:'hat',phase,missing:!['home','returning'].includes(phase)});}win.webContents.send('xl:pet-feedback',{kind:'hat-motion',phase,spin,scale})}
 function setPhase(next){phase=next;since=Date.now();feedback(true)}
 function put(point){const b=win.getBounds();position=bounded(point,b.width,b.height);win.setPosition(Math.round(position.x),Math.round(position.y))}
 function head(){const p=pet.getBounds(),b=win.getBounds(),ratio=p.width/300;return {x:p.x+p.width/2-b.width/2,y:p.y+113*ratio-b.height/2}}
 function movePet(target,dt,speed=430){const p=pet.getBounds(),goal=bounded(target,p.width,p.height),dx=goal.x-p.x,dy=goal.y-p.y,d=Math.hypot(dx,dy),step=speed*dt;if(d<=Math.max(step,2)){pet.setPosition(Math.round(goal.x),Math.round(goal.y));return true}pet.setPosition(Math.round(p.x+dx/d*step),Math.round(p.y+dy/d*step));return false}
 function finish(){win.hide();phase='home';since=Date.now();feedback(true);record();home=null;velocity={x:0,y:0}}
 function begin(value){if(!finite(value?.x)||!finite(value?.y))return false;quick.hide();if(phase==='home'){home=pet.getBounds();const ratio=home.width/300;win.setSize(Math.round(170*ratio),Math.round(132*ratio));scale=[1,.83,.66,.5].includes(value.scale)?value.scale:1;put(head());offset={x:value.x-position.x,y:value.y-position.y}}else{offset={x:value.x-position.x,y:value.y-position.y}}samples=[{x:value.x,y:value.y,t:Date.now()}];velocity={x:0,y:0};setPhase('held');win.setIgnoreMouseEvents(false);win.showInactive();return true}
 function drag(value){if(phase!=='held'||!finite(value?.x)||!finite(value?.y))return false;const t=Date.now();samples.push({x:value.x,y:value.y,t});samples=samples.filter(s=>t-s.t<140);put({x:value.x-offset.x,y:value.y-offset.y});return true}
 function release(){if(phase!=='held')return false;const first=samples[0],last=samples.at(-1);if(first&&last){const seconds=Math.max(.03,(last.t-first.t)/1000);velocity={x:Math.max(-2200,Math.min(2200,(last.x-first.x)/seconds)),y:Math.max(-2400,Math.min(2400,(last.y-first.y)/seconds))}}setPhase('flying');return true}
 function retrieve(){if(phase==='home')return;velocity={x:0,y:0};setPhase('fetching')}
 const timer=setInterval(()=>{if(win.isDestroyed()||pet.isDestroyed())return;const now=Date.now(),dt=Math.min(.045,(now-last)/1000);last=now;if(phase==='home'||phase==='held')return;
  if(phase==='flying'){const b=win.getBounds(),a=area({x:position.x+b.width/2,y:position.y+b.height/2}),floor=a.y+a.height-b.height-8;velocity.y+=1500*dt;position.x+=velocity.x*dt;position.y+=velocity.y*dt;spin+=velocity.x*dt*.0025;
   if(position.x<a.x){position.x=a.x;velocity.x=Math.abs(velocity.x)*.5}if(position.x>a.x+a.width-b.width){position.x=a.x+a.width-b.width;velocity.x=-Math.abs(velocity.x)*.5}if(position.y<a.y){position.y=a.y;velocity.y=Math.abs(velocity.y)*.4}if(position.y>=floor){position.y=floor;velocity.y=-Math.abs(velocity.y)*.36;velocity.x*=.83;if(Math.abs(velocity.y)<65)velocity.y=0;if(Math.abs(velocity.x)<16)velocity.x=0;if(!velocity.y&&!velocity.x)setPhase('settled')}velocity.x*=Math.exp(-.4*dt);put(position);
  }else if(phase==='settled'&&now-since>850)retrieve();
  else if(phase==='fetching'&&!paused){const p=pet.getBounds(),b=win.getBounds(),target={x:position.x+b.width/2-p.width/2,y:position.y+b.height-p.height+35};if(movePet(target,dt)){pickStart={...position};setPhase('pickup')}}
  else if(phase==='pickup'&&!paused){const f=Math.min(1,(now-since)/650),e=f*f*(3-2*f),target=head();put({x:pickStart.x+(target.x-pickStart.x)*e,y:pickStart.y+(target.y-pickStart.y)*e-Math.sin(f*Math.PI)*45});spin*=.85;if(f===1){win.hide();setPhase('returning')}}
  else if(phase==='returning'&&!paused&&home){if(movePet(home,dt))finish()}
  if(phase!=='home')feedback();
 },33);
 app.on('before-quit',()=>clearInterval(timer));
 return {window:win,retrieve,pausePet(value){paused=value;if(value)petDragAnchor=pet.getBounds();else if(phase!=='home'&&petDragAnchor){const p=pet.getBounds();if(Math.hypot(p.x-petDragAnchor.x,p.y-petDragAnchor.y)>6)home=p;petDragAnchor=null}},handle(sender,action,value){if(![pet.webContents,win.webContents].includes(sender))throw Error('Invalid hat window');if(action==='hat-start')return begin(value);if(action==='hat-drag')return drag(value);if(action==='hat-release')return release();if(action==='hat-retrieve'){retrieve();return true}if(action==='hat-pass'&&sender===win.webContents){if(phase!=='held')win.setIgnoreMouseEvents(Boolean(value),{forward:true});return true}throw Error('Unknown hat action')},state:()=>({phase,position:{...position},velocity:{...velocity},home,scale})};
};
