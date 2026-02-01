const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('aobmaster', {
  ipcRequest: (payload) => ipcRenderer.invoke('aobmaster:request', payload),
  openFileDialog: (options) => ipcRenderer.invoke('aobmaster:open-file', options),
  saveFileDialog: (options) => ipcRenderer.invoke('aobmaster:save-file', options),
  exportConfig: (payload) => ipcRenderer.invoke('aobmaster:export-config', payload),
  cancelRequest: () => ipcRenderer.invoke('aobmaster:cancel'),
});
