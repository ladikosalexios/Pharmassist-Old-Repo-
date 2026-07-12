// PharmAssist Agent — main process.
//
// A background daemon that (1) floats an always-on-top, non-focus-stealing
// overlay in the corner, (2) listens globally for a barcode scan (keyboard
// wedge) while the pharmacist works in ANOTHER app, and (3) resolves the scan
// to a safety verdict via the mock backend and shows it. This is the research
// prototype of the parasitic agent in docs/parasitic-agent-plan.md.

const { app, BrowserWindow, globalShortcut, screen } = require("electron");
const path = require("path");
const fs = require("fs");
const { Backend } = require("./backend");
const { startScanner } = require("./scanner");

const cfg = JSON.parse(fs.readFileSync(path.join(__dirname, "..", "config.json"), "utf8"));

let win = null;
let backend = null;
let lastStatus = { ok: false, text: "Starting…", autoHideMs: cfg.overlay.autoHideMs };

function createWindow() {
  const { workArea } = screen.getPrimaryDisplay();
  const W = 380;
  const H = 300;
  const margin = 16;
  win = new BrowserWindow({
    width: W,
    height: H,
    x: workArea.x + workArea.width - W - margin,
    y: workArea.y + margin,
    frame: false,
    transparent: true,
    resizable: false,
    movable: true,
    alwaysOnTop: true,
    skipTaskbar: true,
    focusable: false, // never steal focus from the pharmacist's real app
    hasShadow: false,
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });
  win.setAlwaysOnTop(true, "screen-saver");
  win.setVisibleOnAllWorkspaces(true, { visibleOnFullScreen: true });
  win.loadFile(path.join(__dirname, "overlay.html"));
  // Push the current status once the page is ready (avoids a load/IPC race).
  win.webContents.on("did-finish-load", () => send("status", lastStatus));
}

function send(channel, payload) {
  if (win && !win.isDestroyed()) win.webContents.send(channel, payload);
}

function setStatus(ok, text) {
  lastStatus = { ok, text, autoHideMs: cfg.overlay.autoHideMs };
  send("status", lastStatus);
}

async function connect() {
  try {
    await backend.login();
    setStatus(true, "Listening for scans");
    console.log("[agent] backend login OK");
  } catch (e) {
    setStatus(false, "Backend login failed — is it up? " + e.message);
    console.error("[agent] login failed:", e.message);
  }
}

async function onScan(code) {
  console.log("[agent] scan:", code);
  send("checking", code);
  try {
    const rx = await backend.prescription(code);
    if (rx.notFound) {
      send("scan-error", { code, message: "No prescription found for " + code });
      return;
    }
    send("scan-result", rx);
  } catch (e) {
    send("scan-error", { code, message: e.message });
    console.error("[agent] scan lookup failed:", e.message);
  }
}

app.whenReady().then(async () => {
  createWindow();
  backend = new Backend(cfg);
  await connect();

  try {
    startScanner(cfg.scan, onScan);
    console.log("[agent] scanner started");
  } catch (e) {
    setStatus(false, "Scanner hook failed: " + e.message);
    console.error("[agent] scanner failed:", e.message);
  }

  globalShortcut.register("CommandOrControl+Shift+H", () => {
    if (!win) return;
    win.isVisible() ? win.hide() : win.show();
  });
  globalShortcut.register("CommandOrControl+Shift+C", () => send("clear"));
  globalShortcut.register("CommandOrControl+Shift+Q", () => app.quit());
});

app.on("will-quit", () => globalShortcut.unregisterAll());
// Daemon: keep running with no visible windows (macOS) rather than quitting.
app.on("window-all-closed", () => {});
