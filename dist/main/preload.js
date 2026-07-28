"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
const electron_1 = require("electron");
electron_1.contextBridge.exposeInMainWorld('electronAPI', {
    startDownload: (data) => {
        return electron_1.ipcRenderer.invoke('start-download', data).catch((err) => {
            console.error('Download error:', err);
            throw err;
        });
    },
    onConsole: (callback) => {
        const listener = (_, data) => callback(data);
        electron_1.ipcRenderer.on('console-output', listener);
        // Return cleanup function
        return () => electron_1.ipcRenderer.removeListener('console-output', listener);
    }
});
