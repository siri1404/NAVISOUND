const { app, BrowserWindow } = require('electron');
const path = require('path');

// Relax autoplay policy so speechSynthesis can run without a user gesture
app.commandLine.appendSwitch('autoplay-policy', 'no-user-gesture-required');

function createWindow() {
  const win = new BrowserWindow({
    width: 900,
    height: 700,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      nodeIntegration: false,
      contextIsolation: true,
    },
  });

  // load local dev server in dev, otherwise load built index
  const devUrl = 'http://localhost:5173';
  win.loadURL(devUrl).catch(() => {
    win.loadFile(path.join(__dirname, 'dist', 'index.html'));
  });

  // optional: open devtools for development
  // win.webContents.openDevTools();
}

app.whenReady().then(() => {
  createWindow();

  app.on('activate', function () {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on('window-all-closed', function () {
  if (process.platform !== 'darwin') app.quit();
});
