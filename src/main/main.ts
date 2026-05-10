import {
    app,
    BrowserWindow,
    ipcMain
} from "electron";

import path from "path";

import {
    startDownload
} from "./downloader";

import {
    updateYtDlp
} from "./updater";

let mainWindow: BrowserWindow;

async function createWindow() {

    mainWindow = new BrowserWindow({

        width: 1200,
        height: 850,

        webPreferences: {

            preload: path.join(
                __dirname,
                "preload.js"
            ),

            contextIsolation: true,
            nodeIntegration: false
        }
    });

    await mainWindow.loadFile(

        path.join(
            __dirname,
            "../renderer/index.html"
        )
    );

    mainWindow.webContents.send(
        "console-output",
        "Application started"
    );

    updateYtDlp((msg) => {

        mainWindow.webContents.send(
            "console-output",
            msg
        );
    });
}

app.whenReady().then(createWindow);

app.on(
    "window-all-closed",
    () => {

        if (
            process.platform !== "darwin"
        ) {

            app.quit();
        }
    }
);

ipcMain.handle(

    "start-download",

    async (_, data) => {

        return await startDownload(

            data,

            (msg) => {

                mainWindow.webContents.send(
                    "console-output",
                    msg
                );
            }
        );
    }
);