import { contextBridge, ipcRenderer } from 'electron';

contextBridge.exposeInMainWorld('electronAPI', {
  startDownload: (data: any) => {
    return ipcRenderer.invoke('start-download', data).catch((err: any) => {
      console.error('Download error:', err);
      throw err;
    });
  },
  onConsole: (callback: any) => {
    const listener = (_: any, data: string) => callback(data);
    ipcRenderer.on('console-output', listener);
    
    // Return cleanup function
    return () => ipcRenderer.removeListener('console-output', listener);
  }
});
