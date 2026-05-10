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
            preload: path_1.default.join(__dirname, "preload.js"),
            contextIsolation: true,
            nodeIntegration: false
        }
    });
    await mainWindow.loadFile(path_1.default.join(__dirname, "../renderer/index.html"));
    mainWindow.webContents.send("console-output", "Application started");
    (0, updater_1.updateYtDlp)((msg) => {
        mainWindow.webContents.send("console-output", msg);
    });
}
electron_1.app.whenReady().then(createWindow);
electron_1.app.on("window-all-closed", () => {
    if (process.platform !== "darwin") {
        electron_1.app.quit();
    }
});
electron_1.ipcMain.handle("start-download", async (_, data) => {
    return await (0, downloader_1.startDownload)(data, (msg) => {
        mainWindow.webContents.send("console-output", msg);
    });
});
