"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
const electron_1 = require("electron");
electron_1.contextBridge.exposeInMainWorld('electronAPI', {
    startDownload: (data) => electron_1.ipcRenderer.invoke('start-download', data),
    onConsole: (callback) => electron_1.ipcRenderer.on('console-output', (_, data) => {
        callback(data);
    })
});
