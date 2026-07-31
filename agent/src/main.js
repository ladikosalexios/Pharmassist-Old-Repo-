// PharmAssist Agent — main process.
//
// A background daemon that (1) floats an always-on-top, non-focus-stealing
// overlay in the corner, (2) listens globally for a barcode scan (keyboard
// wedge) while the pharmacist works in ANOTHER app, and (3) resolves the scan
// to a safety verdict via the mock backend and shows it. This is the research
// prototype of the parasitic agent in docs/parasitic-agent-plan.md.

const { app, BrowserWindow, globalShortcut, screen, ipcMain, shell } = require("electron");
const path = require("path");
const fs = require("fs");
const { Backend } = require("./backend");
const { startScanner } = require("./scanner");

const cfg = JSON.parse(fs.readFileSync(path.join(__dirname, "..", "config.json"), "utf8"));

// Environment profile. Default `live` uses config.json as-is (the hosted box,
// currently pointed at the live ΗΔΥΚΑ / testeps backend, demo mapping off).
// Set PHARMASSIST_ENV=demo (or the shorthand PHARMASSIST_DEMO=1) to run the old
// local demo: localhost backend + the scripted pack→scenario mapping, so the
// RX2024 barcodes and the Cmd/Ctrl+Alt+1..8 hotkeys resolve against mock data.
const ENV = (process.env.PHARMASSIST_ENV || (process.env.PHARMASSIST_DEMO ? "demo" : "live")).toLowerCase();
if (ENV === "demo") {
  cfg.backendUrl = "http://localhost:8000";
  cfg.webAppUrl = "http://localhost:5173";
  cfg.demo = Object.assign({}, cfg.demo, { mapUnknownToDemo: true });
}

// Point a shipped build at a specific backend WITHOUT rebuilding: these env vars
// win over the profile above and the bundled config.json. Use them in a launcher
// (.command / shortcut) so one signed binary serves localhost, demo, or cloud.
if (process.env.PHARMASSIST_BACKEND_URL) cfg.backendUrl = process.env.PHARMASSIST_BACKEND_URL;
if (process.env.PHARMASSIST_WEBAPP_URL) cfg.webAppUrl = process.env.PHARMASSIST_WEBAPP_URL;
console.log("[agent] env:", ENV, "· backend:", cfg.backendUrl, "· webapp:", cfg.webAppUrl);

let win = null;
let backend = null;
let currentRxId = null; // the prescription currently on the card — target of the SPA handoff
let lastStatus = { ok: false, text: "Starting…", autoHideMs: cfg.overlay.autoHideMs };

const WIN_W = 380;
const WIN_MARGIN = 16;

function anchorTopRight(height) {
  const { workArea } = screen.getPrimaryDisplay();
  const h = Math.min(Math.max(Math.round(height), 48), workArea.height - WIN_MARGIN * 2);
  win.setBounds({
    x: workArea.x + workArea.width - WIN_W - WIN_MARGIN,
    y: workArea.y + WIN_MARGIN,
    width: WIN_W,
    height: h,
  });
}

function createWindow() {
  const { workArea } = screen.getPrimaryDisplay();
  win = new BrowserWindow({
    width: WIN_W,
    height: 120,
    x: workArea.x + workArea.width - WIN_W - WIN_MARGIN,
    y: workArea.y + WIN_MARGIN,
    frame: false,
    transparent: true,
    resizable: false,
    movable: false,
    alwaysOnTop: true,
    skipTaskbar: true,
    focusable: false, // never take key focus from the pharmacist's real app
    hasShadow: false,
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });
  win.setAlwaysOnTop(true, "screen-saver");
  win.setVisibleOnAllWorkspaces(true, { visibleOnFullScreen: true });
  // Click-through: the transparent area (and the card itself) must never
  // intercept a click or steal focus — the pharmacist works right through it.
  // Dismiss/interaction is via hotkeys, so we lose nothing.
  win.setIgnoreMouseEvents(true, { forward: true });
  win.loadFile(path.join(__dirname, "overlay.html"));
  // Push the current status once the page is ready (avoids a load/IPC race).
  win.webContents.on("did-finish-load", () => send("status", lastStatus));
}

// The renderer measures its content and asks for exactly that height, so a long
// card never clips and the idle pill never leaves a big invisible window.
ipcMain.on("resize", (_e, height) => {
  if (win && !win.isDestroyed()) anchorTopRight(height);
});

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

const DEMO = cfg.demo || { mapUnknownToDemo: false, prescriptions: [] };
const RX_RE = /^RX\d{4}-\d{3}$/i;

// Deterministic pick so the SAME pack always maps to the SAME scenario — a
// scripted research demo stays reproducible run to run.
function hashPick(str, list) {
  let h = 0;
  for (let i = 0; i < str.length; i++) h = (h * 31 + str.charCodeAt(i)) >>> 0;
  return list[h % list.length];
}

// A scanned code is either a printed RX barcode (use directly) or a real GS1
// medicine pack with no prescription attached (map to a demo scenario).
function resolveCode(code) {
  if (RX_RE.test(code)) return { rxId: code.toUpperCase(), mappedFrom: null };
  if (DEMO.mapUnknownToDemo && DEMO.prescriptions.length) {
    return { rxId: hashPick(code, DEMO.prescriptions), mappedFrom: code };
  }
  return { rxId: code.toUpperCase(), mappedFrom: null };
}

async function showPrescription(rxId) {
  send("checking", rxId);
  try {
    const rx = await backend.prescription(rxId);
    if (rx.notFound) {
      currentRxId = null;
      send("scan-error", { code: rxId, message: "No prescription found for " + rxId });
      return;
    }
    currentRxId = rx.rxId || rxId;
    send("scan-result", rx);
  } catch (e) {
    send("scan-error", { code: rxId, message: e.message });
    console.error("[agent] lookup failed:", e.message);
  }
}

async function onScan(code) {
  const { rxId, mappedFrom } = resolveCode(code);
  // Log the mapping for the facilitator; the overlay shows only the (real-
  // looking) prescription, so the research subject never sees the wiring.
  if (mappedFrom) console.log(`[agent] pack ${mappedFrom.slice(0, 20)}… → demo ${rxId}`);
  else console.log("[agent] scan:", rxId);
  await showPrescription(rxId);
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

  // Simulated-scan fallback: fire a specific demo scenario with no scanner and
  // no Accessibility permission (globalShortcut needs neither). Cmd/Ctrl+Alt+N.
  (DEMO.prescriptions || []).slice(0, 8).forEach((rxId, i) => {
    const accel = `CommandOrControl+Alt+${i + 1}`;
    const ok = globalShortcut.register(accel, () => {
      console.log(`[agent] hotkey ${accel} → ${rxId}`);
      showPrescription(rxId);
    });
    console.log(`[agent] hotkey ${accel} → ${rxId}: ${ok ? "registered" : "FAILED (in use?)"}`);
  });

  // Notice → act handoff: open the current prescription's FULL verification
  // view in the web SPA (deep work: all checks, SPC, override-with-reason, ADR).
  // The agent is the heads-up display; the SPA is the console you drop into.
  globalShortcut.register("CommandOrControl+Alt+Return", () => {
    if (!currentRxId) return;
    const url = cfg.webAppUrl.replace(/\/$/, "") + "/prescription/" + encodeURIComponent(currentRxId);
    console.log("[agent] open full review →", url);
    shell.openExternal(url);
  });

  globalShortcut.register("CommandOrControl+Shift+H", () => {
    if (!win) return;
    win.isVisible() ? win.hide() : win.showInactive(); // showInactive → never focuses
  });
  globalShortcut.register("CommandOrControl+Shift+C", () => {
    currentRxId = null;
    send("clear");
  });
  globalShortcut.register("CommandOrControl+Shift+Q", () => app.quit());
});

app.on("will-quit", () => globalShortcut.unregisterAll());
// Daemon: keep running with no visible windows (macOS) rather than quitting.
app.on("window-all-closed", () => {});
