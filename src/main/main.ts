import { app, BrowserWindow, ipcMain } from 'electron';
import path from 'path';
import { startDownload } from './downloader';
import { updateYtDlp } from './updater';

let mainWindow: BrowserWindow;

async function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1200,
    height: 850,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false
    },
    show: false
  });

  mainWindow.webContents.openDevTools();
  await mainWindow.loadFile(path.join(__dirname, '../renderer/index.html'));
  mainWindow.show();

  mainWindow.webContents.send('console-output', '\n=== Application started ===\n');

  updateYtDlp((msg) => {
    if (mainWindow) {
      mainWindow.webContents.send('console-output', msg);
    }
  });
}

app.whenReady().then(createWindow);

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit();
  }
});

ipcMain.handle('start-download', async (event, data) => {
  try {
    if (!mainWindow) {
      throw new Error('Main window not available');
    }

    const result = await startDownload(data, (msg) => {
      if (mainWindow && !mainWindow.isDestroyed()) {
        mainWindow.webContents.send('console-output', msg);
      }
    });

    return result;
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error);
    if (mainWindow && !mainWindow.isDestroyed()) {
      mainWindow.webContents.send('console-output', `\n❌ Error: ${errorMsg}\n`);
    }
    throw error;
  }
});
