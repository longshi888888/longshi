const assert=require('node:assert/strict');
const originalNow=Date.now,originalInterval=global.setInterval,originalClear=global.clearInterval;let clock=1000,tick;
Date.now=()=>clock;global.setInterval=fn=>(tick=fn,1);global.clearInterval=()=>{};
class Window{constructor(options={}){this.bounds={x:0,y:0,width:options.width||300,height:options.height||410};this.visible=false;this.sent=[];this.webContents={send:(...v)=>this.sent.push(v)}}setMenu(){}loadURL(){}getBounds(){return {...this.bounds}}setSize(width,height){Object.assign(this.bounds,{width,height})}setPosition(x,y){Object.assign(this.bounds,{x,y})}setIgnoreMouseEvents(){}showInactive(){this.visible=true}hide(){this.visible=false}isDestroyed(){return false}}
try{
const pet=new Window(),quick=new Window();pet.setPosition(650,250);let saved=0;const game=require('./desktop/hat.cjs')({BrowserWindow:Window,app:{on(){}},screen:{getDisplayNearestPoint:()=>({workArea:{x:0,y:0,width:1280,height:850}})},base:'http://127.0.0.1/synthetic/',settings:{},pet,quick,record:()=>saved++});
assert.equal(game.handle(pet.webContents,'hat-start',{x:NaN,y:2}),false);assert.throws(()=>game.handle({},'hat-release'),/Invalid/);
const origin=pet.getBounds();game.handle(pet.webContents,'hat-start',{x:800,y:360,scale:.83});assert.equal(game.state().phase,'held');clock+=60;game.handle(pet.webContents,'hat-drag',{x:450,y:200});clock+=40;game.handle(pet.webContents,'hat-drag',{x:100,y:80});game.handle(pet.webContents,'hat-release');assert.equal(game.state().phase,'flying');
const seen=new Set();for(let i=0;i<1800;i++){clock+=33;tick();const s=game.state();seen.add(s.phase);const b=game.window.getBounds();assert.ok(b.x>=0&&b.y>=0&&b.x+b.width<=1280&&b.y+b.height<=850);if(s.phase==='home')break}
for(const state of ['flying','settled','fetching','pickup','returning','home'])assert.ok(seen.has(state),state);assert.deepEqual(pet.getBounds(),origin);assert.equal(game.window.visible,false);assert.ok(saved>0);
game.handle(pet.webContents,'hat-start',{x:800,y:360});clock+=60;game.handle(pet.webContents,'hat-drag',{x:900,y:370});game.handle(pet.webContents,'hat-release');clock+=33;tick();game.handle(game.window.webContents,'hat-start',{x:920,y:380,scale:1});assert.equal(game.state().phase,'held');game.pausePet(true);const p=pet.getBounds();pet.setPosition(p.x+25,p.y);game.pausePet(false);game.handle(game.window.webContents,'hat-retrieve');
for(let i=0;i<1800&&game.state().phase!=='home';i++){clock+=33;tick()}assert.equal(game.state().phase,'home');assert.equal(pet.getBounds().x,origin.x+25);
console.log(JSON.stringify({ok:true,bounds:true,allPhases:[...seen],returnToOrigin:true,regrabAndBodyMove:true,invalidOriginRejected:true}));
}finally{Date.now=originalNow;global.setInterval=originalInterval;global.clearInterval=originalClear}
