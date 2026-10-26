const {contextBridge,ipcRenderer}=require('electron');
contextBridge.exposeInMainWorld('xiaolongDesktop',Object.freeze({
 openPanel:()=>ipcRenderer.invoke('xl:action','open-panel'),
 hidePanel:()=>ipcRenderer.invoke('xl:action','hide-panel'),
 pin:()=>ipcRenderer.invoke('xl:action','pin'),
 passthrough:value=>ipcRenderer.invoke('xl:action','passthrough',Boolean(value)),
 quit:()=>ipcRenderer.invoke('xl:action','quit')
}));
