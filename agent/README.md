# PharmAssist Agent (research prototype)

The **scan-riding safety overlay** — a cross-platform (macOS + Windows) desktop
daemon that floats an always-on-top card in the corner, listens *globally* for a
barcode scan while the pharmacist works in their existing software, and pops the
prescription's safety verdict beside it. This is Phase 2 of
[`../docs/parasitic-agent-plan.md`](../docs/parasitic-agent-plan.md), built for
user research against **mock/test data** — no live ΗΔΥΚΑ.

## Why Electron + uiohook

A browser tab can't see keystrokes destined for another app, and can't float
over one. A native shell can. Electron gives us the overlay + reuse of web UI;
`uiohook-napi` gives cross-platform global keyboard capture. (Tauri is the
lighter productionization path per the plan; Electron is the fastest way to put
something in front of users.)

## Run it

**1. Start the mock backend** (from the repo root):

```bash
docker compose up -d backend db
```

The agent logs in with the seeded dev pharmacist (`config.json`) and talks to
`http://localhost:8000` in mock mode, so scans resolve to the curated
`MOCK_SAFETY_CHECKS` scenarios.

**2. Install + run the agent:**

```bash
cd agent
npm install
npm run barcodes     # writes barcodes.html — the scannable test prescriptions
npm start
```

A pill appears top-right: **“Listening for scans”** (green) once the backend
login succeeds. Open `barcodes.html`, focus any *other* app (a text editor,
Notes — standing in for Farmakon), and scan a barcode with the Eyoyo. The card
pops with the patient, drug, and colour-coded checks — **without** taking focus
from the app you're in. That's the whole point.

### Test scenarios

`barcodes.html` has one barcode per curated prescription. The headliner is
**RX2024-005** (Maria Stavrou, Warfarin): a red **BLOCK** for an amiodarone
interaction plus an amber aspirin review.

### Scanning real medicine packs (the Eyoyo)

Your Eyoyo packs are **GS1 medicine packs** (GTIN / serial / lot / expiry) with
**no prescription attached** — so a raw pack scan can't resolve to a real rx. The
agent handles this: any scanned code that isn't an `RX2024-xxx` is
**deterministically mapped to a demo prescription** (`config.json → demo`). Same
pack → same scenario every run, so you can script a session ("scan the blue pack →
they see the Warfarin BLOCK"). The overlay shows only the real-looking
prescription; the pack→scenario mapping is logged to the console for the
facilitator, never shown to the research subject.

So: scan any pack with the Eyoyo and you get a real-feeling safety verdict. The
printed `RX2024-xxx` barcodes (`npm run barcodes`) still resolve directly to
their own scenario.

### Simulated scan (no scanner / no permission)

`⌘/Ctrl + Alt + 1…8` each fire a specific demo scenario directly — no scanner
and **no Accessibility grant needed** (global hotkeys use a different API). `1`
is the Warfarin BLOCK headliner. Use these for UX-only sessions, or as a backup
if the Eyoyo isn't to hand.

### Hotkeys

- `⌘/Ctrl + Alt + 1…8` — fire demo scenario 1–8 (simulated scan)
- `⌘/Ctrl + Alt + Enter` — open the current prescription's **full review** in the web app (`webAppUrl` in config; needs the SPA running + a logged-in browser)
- `⌘/Ctrl + Shift + H` — hide / show the overlay
- `⌘/Ctrl + Shift + C` — dismiss the current card
- `⌘/Ctrl + Shift + Q` — quit the daemon

## Permissions (first run)

Global keyboard capture needs OS permission:

- **macOS:** System Settings → Privacy & Security → **Accessibility** → enable
  the app you launched it from (Electron, or your terminal). Without it the
  overlay still shows but no scans are captured. Re-launch after granting.
- **Windows:** no prompt; SmartScreen may warn on an unsigned build (see below).

## No scanner handy?

Use the simulated-scan hotkeys (`⌘/Ctrl + Alt + 1…8`) above — they fire the demo
scenarios directly, need no scanner and no Accessibility permission. You can also
type an rx_id fast and press Enter into any field: the burst detector treats a
fast-typed `RX2024-005⏎` as a scan.

## Packaging (later)

`npm run dist:mac` / `npm run dist:win` (electron-builder). Distribution needs
code-signing — an unsigned build trips Gatekeeper/SmartScreen and, more
importantly, a global keyboard hook + always-on-top overlay is exactly the
behavioural signature AV/EDR flags. Budget for a signing cert + keeping the hook
scoped to sentinel-framed scans (see `config.json` → `scan.sentinelPrefix`).

## How a scan is detected

`src/scanner.js` reconstructs a string **only** from keystrokes that arrive
scanner-fast (`scan.interKeyMs`, default 120 ms apart) and end in Enter, past a
minimum length. Human typing is slower and never assembled or emitted — this is
deliberately *not* a general keylogger. Production should set a
`sentinelPrefix` and program the Eyoyo to frame every scan with it, so only
sentinel-framed input is ever considered.
