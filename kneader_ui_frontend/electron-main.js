const { app, BrowserWindow,ipcMain} = require("electron");

let mainWindow = null;

// Single instance lock
const gotLock = app.requestSingleInstanceLock();

if (!gotLock) {
  app.quit();
  return;
}

ipcMain.on("kneader-exit", () => {
  app.quit();
});


function openKioskWindow(hmiUrl) {
  if (mainWindow) {
    mainWindow.focus();
    return;
  }

  const path = require("path");

mainWindow = new BrowserWindow({
  fullscreen: true,
  kiosk: true,
  frame: false,
  autoHideMenuBar: true,
  webPreferences: {
    preload: path.join(__dirname, "preload.js"),
    contextIsolation: true,
    nodeIntegration: false
  }
});


  mainWindow.loadURL(hmiUrl);

  mainWindow.on("closed", () => {
    mainWindow = null;
  });
}

// 🔑 HANDLE SECOND INSTANCE (already running)
app.on("second-instance", (event, argv) => {
  const protocolArg = argv.find(arg => arg.startsWith("kneader://"));
  if (protocolArg) {
    const url = new URL(protocolArg);
    const hmi = url.searchParams.get("hmi");
    if (hmi) openKioskWindow(hmi);
  }
});

// 🔑 HANDLE FIRST LAUNCH (MOST IMPORTANT)
app.whenReady().then(() => {
  const protocolArg = process.argv.find(arg =>
    arg.startsWith("kneader://")
  );

  if (protocolArg) {
    const url = new URL(protocolArg);
    const hmi = url.searchParams.get("hmi");
    openKioskWindow(hmi || "http://localhost:8080/assets/kneader/");
  }
});
