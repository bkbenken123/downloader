import { contextBridge, ipcRenderer } from 'electron';

contextBridge.exposeInMainWorld('electronAPI', {
  startDownload: (data: any) => ipcRenderer.invoke('start-download', data),
  onConsole: (callback: any) =>
    ipcRenderer.on('console-output', (_, data) => {
      callback(data);
    })
});
