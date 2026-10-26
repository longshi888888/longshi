const {contextBridge,ipcRenderer}=require('electron');
contextBridge.exposeInMainWorld('xiaolongDesktop',Object.freeze({
 openPanel:()=>ipcRenderer.invoke('xl:action','open-panel'),
 openQuick:()=>ipcRenderer.invoke('xl:action','open-quick'),
 hideQuick:()=>ipcRenderer.invoke('xl:action','hide-quick'),
 petDragStart:()=>ipcRenderer.invoke('xl:action','pet-drag-start'),
 petDragMove:delta=>ipcRenderer.invoke('xl:action','pet-drag-move',delta),
 petDragEnd:()=>ipcRenderer.invoke('xl:action','pet-drag-end'),
 petReply:text=>ipcRenderer.invoke('xl:action','pet-reply',String(text)),
 petActivity:state=>ipcRenderer.invoke('xl:action','pet-activity',String(state)),
 hatStart:value=>ipcRenderer.invoke('xl:action','hat-start',value),
 hatDrag:value=>ipcRenderer.invoke('xl:action','hat-drag',value),
 hatRelease:()=>ipcRenderer.invoke('xl:action','hat-release'),
 hatRetrieve:()=>ipcRenderer.invoke('xl:action','hat-retrieve'),
 hatPass:value=>ipcRenderer.invoke('xl:action','hat-pass',Boolean(value)),
 onPetFeedback:callback=>{if(typeof callback!=='function')return;const listener=(_event,data)=>callback(data);ipcRenderer.on('xl:pet-feedback',listener);return()=>ipcRenderer.removeListener('xl:pet-feedback',listener)},
 hidePanel:()=>ipcRenderer.invoke('xl:action','hide-panel'),
 openExternal:url=>ipcRenderer.invoke('xl:action','open-external',String(url)),
 testNotification:()=>ipcRenderer.invoke('xl:action','test-notification'),
 chooseFolder:()=>ipcRenderer.invoke('xl:action','choose-folder'),
 pin:()=>ipcRenderer.invoke('xl:action','pin'),
 passthrough:value=>ipcRenderer.invoke('xl:action','passthrough',Boolean(value)),
 quit:()=>ipcRenderer.invoke('xl:action','quit')
}));
