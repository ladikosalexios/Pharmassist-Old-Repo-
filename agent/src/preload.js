// Minimal, safe bridge: the overlay renderer only receives display data via
// these channels. No Node, no backend, no cookie ever reaches the renderer.
const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("agent", {
  onStatus: (cb) => ipcRenderer.on("status", (_e, s) => cb(s)),
  onChecking: (cb) => ipcRenderer.on("checking", (_e, code) => cb(code)),
  onResult: (cb) => ipcRenderer.on("scan-result", (_e, rx) => cb(rx)),
  onError: (cb) => ipcRenderer.on("scan-error", (_e, d) => cb(d)),
  onClear: (cb) => ipcRenderer.on("clear", () => cb()),
});
