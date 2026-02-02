const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("kneader", {
  exitApp: () => ipcRenderer.send("kneader-exit")
});
