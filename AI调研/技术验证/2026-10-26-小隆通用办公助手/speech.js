(()=>{
 let token=0,audio=null,active=false;
 const api=async(path,data)=>{const r=await fetch('./'+path,data===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)}),d=await r.json();if(!r.ok)throw Error(d.error||'朗读未完成');return d};
 function signal(state,message='',updatePet=true){active=state!=='idle'&&state!=='error';document.dispatchEvent(new CustomEvent('xl-speech',{detail:{state,message}}));if(updatePet)window.xiaolongDesktop?.petActivity(state==='playing'?'speaking':'idle')}
 async function stop(){token++;if(audio){audio.pause();audio.removeAttribute('src');audio.load();audio=null}signal('idle');try{await api('tts/stop',{})}catch{}}
 async function speak(text){await stop();const own=++token,clean=String(text||'').replace(/```[\s\S]*?```/g,'代码片段请查看文字。').replace(/\[([^\]]+)\]\([^)]*\)/g,'$1').replace(/[#*`|>]/g,'').trim();if(!clean)return;signal('generating',clean.length>1800?'仅朗读前1800字，完整内容见文字。':'正在准备本机音频…');try{let job=await api('tts/start',{text:clean.slice(0,1800)});while(own===token&&job.state==='generating'){await new Promise(r=>setTimeout(r,160));job=await api('tts/status?id='+encodeURIComponent(job.id))}if(own!==token)return;if(job.state!=='ready')throw Error(job.message);audio=new Audio('./'+job.url);audio.onended=()=>{if(own===token){audio=null;signal('idle')}};audio.onerror=()=>{if(own===token)signal('error','音频播放未完成，可重试或查看文字')};await audio.play();if(own!==token){audio?.pause();return}signal('playing',clean.length>1800?'朗读前1800字，点击可停止':'正在朗读，开麦或点击可打断')}catch(e){if(own===token)signal('error',e.message)}}
 window.xiaolongSpeech={speak,stop,get active(){return active}};
 document.addEventListener('keydown',event=>{if(event.key==='Escape')stop()});
 window.xiaolongDesktop?.onPetFeedback(message=>{if(message.kind==='hide'||message.kind==='panel-hide')stop();if(message.kind==='speech-stop'){token++;if(audio){audio.pause();audio=null}signal('idle','',false)}});
 window.addEventListener('beforeunload',()=>{audio?.pause();fetch('./tts/stop',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}',keepalive:true}).catch(()=>{})});
})();
