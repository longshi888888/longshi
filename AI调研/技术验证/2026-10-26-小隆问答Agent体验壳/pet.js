import * as THREE from 'three';
import {GLTFLoader} from './vendor/GLTFLoader.js';
import {OrbitControls} from './vendor/OrbitControls.js';
import {RoomEnvironment} from './vendor/RoomEnvironment.js';
const host=document.querySelector('#stage'),renderer=new THREE.WebGLRenderer({alpha:true,antialias:true,preserveDrawingBuffer:true});
renderer.setClearColor(0,0);renderer.setSize(290,284);renderer.setPixelRatio(Math.min(devicePixelRatio,1.5));renderer.toneMapping=THREE.ACESFilmicToneMapping;host.append(renderer.domElement);
const scene=new THREE.Scene(),camera=new THREE.PerspectiveCamera(32,290/284,.05,30);camera.position.set(0,0,4.3);
const controls=new OrbitControls(camera,renderer.domElement);controls.enableDamping=true;controls.enablePan=false;controls.enableZoom=false;
const room=new RoomEnvironment(),pmrem=new THREE.PMREMGenerator(renderer);scene.environment=pmrem.fromScene(room,.04).texture;scene.environmentIntensity=.6;room.dispose();pmrem.dispose();
scene.add(new THREE.HemisphereLight('#fff8e8','#a7aaa2',1.8));const light=new THREE.DirectionalLight('#fff9f0',2);light.position.set(-3,4,5);scene.add(light);
let model,busy=false,dragging=false,passing=false,last=0,panelRequest=0;const ray=new THREE.Raycaster(),mouse=new THREE.Vector2();
function hats(scale){model?.traverse(m=>{if(m.name==='SafetyHat'||m.name==='HatUnderside')m.scale.setScalar(scale)});localStorage.setItem('xl-hat-scale',String(scale));}
new GLTFLoader().load('./model.glb',gltf=>{model=gltf.scene;scene.add(model);const saved=Number(localStorage.getItem('xl-hat-scale')||1);document.querySelector('#hat').value=String([1,.83,.66,.5].includes(saved)?saved:1);hats(Number(document.querySelector('#hat').value));renderer.render(scene,camera);document.documentElement.dataset.model='ready';window.xiaolongModel={model,camera,controls,renderer};},undefined,()=>{document.querySelector('#bubble').textContent='本机角色素材未找到，问答面板仍可使用';document.documentElement.dataset.model='error';});
document.querySelector('#hat').onchange=e=>hats(Number(e.target.value));
document.querySelector('#chat').onclick=()=>window.xiaolongDesktop?.openPanel();document.querySelector('#pin').onclick=async()=>{const pin=await window.xiaolongDesktop?.pin();document.querySelector('#pin').textContent=pin?'钉':'○';};
host.ondblclick=()=>{controls.enableDamping=false;controls.update();camera.position.set(0,0,4.3);controls.target.set(0,0,0);controls.update();controls.enableDamping=true;const s=document.querySelector('#spark');s.style.opacity=1;s.style.transform='translateY(-25px)';setTimeout(()=>{s.style.opacity=0;s.style.transform=''},700);};
host.addEventListener('pointerdown',()=>{dragging=true;window.xiaolongDesktop?.passthrough(false)});window.addEventListener('pointerup',()=>dragging=false);
window.addEventListener('mousemove',event=>{
 if(dragging)return;let hit=true;
 if(event.target===renderer.domElement&&model){const rect=renderer.domElement.getBoundingClientRect();mouse.set((event.clientX-rect.left)/rect.width*2-1,-(event.clientY-rect.top)/rect.height*2+1);ray.setFromCamera(mouse,camera);hit=ray.intersectObject(model,true).length>0;}
 else if(event.target===document.body||event.target===document.documentElement)hit=false;
 if(passing===hit){passing=!hit;window.xiaolongDesktop?.passthrough(passing);}
});
async function status(){try{const s=await fetch('./status').then(r=>r.json()),job=s.active;if(s.panel_request>panelRequest){panelRequest=s.panel_request;window.xiaolongDesktop?.openPanel();}busy=!!job.id&&!['done','error'].includes(job.state);document.querySelector('#bubble').textContent=busy?job.message:job.state==='error'?'这次没有查成，点开看看原因':job.state==='done'?job.message+'，点开看看':'我在呢，想查什么？';}catch{document.querySelector('#bubble').textContent='问答服务已断开';}}
setInterval(status,900);status();
function frame(t){requestAnimationFrame(frame);if(document.hidden||t-last<33)return;last=t;if(model)model.position.y=Math.sin(t/(busy?250:1100))*(busy?.025:.012);controls.update();renderer.render(scene,camera);}requestAnimationFrame(frame);
