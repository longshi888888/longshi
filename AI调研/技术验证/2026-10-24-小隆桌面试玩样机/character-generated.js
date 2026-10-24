import * as THREE from 'three';
import {GLTFLoader} from './vendor/GLTFLoader.js';
import {OrbitControls} from './vendor/OrbitControls.js';
import {RoomEnvironment} from './vendor/RoomEnvironment.js';
const modes=['normal','middle','small','tiny'],labels=['原版','中间档','小一点','最小'];
const sizes={normal:1,middle:.83,small:.66,tiny:.50},views=[];
let selected=modes.includes(localStorage.getItem('xl-generated-hat'))?localStorage.getItem('xl-generated-hat'):'normal';
function applyHat(model,mode){model.traverse(m=>{if(m.name==='SafetyHat'||m.name==='HatUnderside')m.scale.setScalar(sizes[mode]);});}
function makeView(host,source,interactive,mode){
  const renderer=new THREE.WebGLRenderer({antialias:true,alpha:true});
  renderer.setPixelRatio(Math.min(devicePixelRatio,1.5));renderer.toneMapping=THREE.ACESFilmicToneMapping;
  host.replaceChildren(renderer.domElement);const scene=new THREE.Scene(),model=source.clone(true);applyHat(model,mode);scene.add(model);
  const camera=new THREE.PerspectiveCamera(32,1,.05,30);camera.position.set(0,.04,4.6);
  const pmrem=new THREE.PMREMGenerator(renderer),room=new RoomEnvironment();scene.environment=pmrem.fromScene(room,.04).texture;scene.environmentIntensity=.6;room.dispose();pmrem.dispose();
  scene.add(new THREE.HemisphereLight('#fff8e8','#a7aaa2',1.8));const key=new THREE.DirectionalLight('#fff9f0',2);key.position.set(-3,4,5);scene.add(key);
  let controls;
  if(interactive){
    controls=new OrbitControls(camera,renderer.domElement);controls.enableDamping=true;controls.enablePan=false;controls.minDistance=2.6;controls.maxDistance=7;renderer.domElement.style.touchAction='none';
    host.ondblclick=()=>{controls.enableDamping=false;controls.update();camera.position.set(0,.04,4.6);controls.target.set(0,0,0);controls.update();controls.enableDamping=true;};
    host.onkeydown=e=>{if(e.key==='ArrowLeft'||e.key==='ArrowRight'){const angle=Math.atan2(camera.position.x,camera.position.z)+(e.key==='ArrowLeft'?-.2:.2),r=camera.position.length();camera.position.set(Math.sin(angle)*r,.04,Math.cos(angle)*r);controls.update();e.preventDefault();}};
  }
  new ResizeObserver(()=>{const r=host.getBoundingClientRect();if(r.width&&r.height){renderer.setSize(r.width,r.height,false);camera.aspect=r.width/r.height;camera.updateProjectionMatrix();}}).observe(host);
  const view={host,renderer,scene,model,camera,controls,mode};views.push(view);return view;
}
function choose(mode){selected=mode;localStorage.setItem('xl-generated-hat',mode);applyHat(views[0].model,mode);document.querySelectorAll('.pick').forEach(b=>b.classList.toggle('selected',b.dataset.kind===mode));document.documentElement.dataset.characterMode=mode;}
new GLTFLoader().load('./model-assets/xiaolong-parts.glb',gltf=>{
  const picker=document.querySelector('#picker');picker.replaceChildren();makeView(document.querySelector('#pet'),gltf.scene,true,selected);
  modes.forEach((mode,i)=>{const button=document.createElement('button');button.className='pick';button.dataset.kind=mode;const stage=document.createElement('div');stage.className='model-preview';button.append(stage);const title=document.createElement('strong');title.textContent=labels[i];button.append(title);const note=document.createElement('span');note.textContent=mode==='middle'?'介于原版和小一点之间':'同一模型 · 仅调整帽子';button.append(note);button.onclick=()=>choose(mode);picker.append(button);makeView(stage,gltf.scene,false,mode);});
  choose(selected);document.documentElement.dataset.model='generated-ready';window.xiaolongAppearance={modes,choose,views,kind:'generated-glb',sizes};
},undefined,error=>{console.error(error);document.querySelector('#petLine').textContent='3D模型加载失败，请重新打开';document.documentElement.dataset.model='error';});
let last=0;function frame(t){requestAnimationFrame(frame);if(document.hidden||t-last<33)return;last=t;for(const v of views){if(!v.host.getClientRects().length)continue;v.controls?.update();v.renderer.render(v.scene,v.camera);}}requestAnimationFrame(frame);
