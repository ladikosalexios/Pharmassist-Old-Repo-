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

### Hotkeys

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

You can still exercise the pipe: with `barcodes.html` open, focus it and use a
phone/other scanner, or temporarily type an rx_id fast and press Enter into any
field (the burst detector treats a fast-typed `RX2024-005⏎` as a scan). For
pure-UI iteration, scans are the only trigger by design (real parasitic
behavior) — flip on a simulated trigger later if UX-only testing is needed.

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
