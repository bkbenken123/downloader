"use strict";
var __importDefault = (this && this.__importDefault) || function (mod) {
    return (mod && mod.__esModule) ? mod : { "default": mod };
};
Object.defineProperty(exports, "__esModule", { value: true });
const electron_1 = require("electron");
const path_1 = __importDefault(require("path"));
const downloader_1 = require("./downloader");
const updater_1 = require("./updater");
let mainWindow;
async function createWindow() {
    mainWindow = new electron_1.BrowserWindow({
        width: 1200,
        height: 850,
        webPreferences: {
            preload: path_1.default.join(__dirname, 'preload.js'),
            contextIsolation: true,
            nodeIntegration: false
        },
        show: false
    });
    mainWindow.webContents.openDevTools();
    await mainWindow.loadFile(path_1.default.join(__dirname, '../renderer/index.html'));
    mainWindow.show();
    mainWindow.webContents.send('console-output', '\n=== Application started ===\n');
    (0, updater_1.updateYtDlp)((msg) => {
        if (mainWindow) {
            mainWindow.webContents.send('console-output', msg);
        }
    });
}
electron_1.app.whenReady().then(createWindow);
electron_1.app.on('window-all-closed', () => {
    if (process.platform !== 'darwin') {
        electron_1.app.quit();
    }
});
electron_1.ipcMain.handle('start-download', async (event, data) => {
    try {
        if (!mainWindow) {
            throw new Error('Main window not available');
        }
        const result = await (0, downloader_1.startDownload)(data, (msg) => {
            if (mainWindow && !mainWindow.isDestroyed()) {
                mainWindow.webContents.send('console-output', msg);
            }
        });
        return result;
    }
    catch (error) {
        const errorMsg = error instanceof Error ? error.message : String(error);
        if (mainWindow && !mainWindow.isDestroyed()) {
            mainWindow.webContents.send('console-output', `\n❌ Error: ${errorMsg}\n`);
        }
        throw error;
    }
});
