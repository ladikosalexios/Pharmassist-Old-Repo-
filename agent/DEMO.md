# PharmAssist Agent — demo runbook

A copy-paste script for running the scan-riding safety overlay in front of a
pharmacist (user research). Read it once; then the **Quickstart** + **Scenario
cheat-sheet** are all you need at the table.

---

## The one-liner (what you're showing)

> "You keep working in your own pharmacy software. When you scan a pack, a safety
> check quietly pops up beside it — drug interactions, contraindications,
> allergies — without you switching apps or typing anything. Nothing changes
> about how you dispense."

That's the whole pitch: **a safety co-pilot that rides your existing scan.**

---

## Quickstart (every session)

From the repo root:

```bash
docker compose up -d backend db      # 1. mock backend
cd agent && npm start                # 2. the agent (npm install once, first time)
```

You want the corner pill to read **"Listening for scans"** with a green dot.
That means the backend login worked and the scanner is armed. You're ready.

To fire a scenario: **scan a pack with the Eyoyo**, or press **⌘+Alt+1** (the
Warfarin BLOCK). The card pops top-right.

---

## One-time setup (first machine only)

```bash
cd agent
npm install
npm run barcodes     # optional: printable test barcodes → open barcodes.html
```

**macOS permission (required for real scanning):** System Settings → Privacy &
Security → **Accessibility** → turn on the app you launch from (Electron, or your
Terminal). Without it the overlay still shows but the Eyoyo won't be captured.
Re-launch after granting. *(The ⌘+Alt hotkeys work even without this.)*

---

## Pre-session checklist (60 seconds)

1. `docker compose up -d backend db` — backend up.
2. `cd agent && npm start` — pill shows **green "Listening for scans"**.
3. Open a **stand-in for the pharmacy software** — Notes, TextEdit, a browser —
   and click into it so *it* has focus, not the overlay. (This is the point:
   the overlay rides alongside whatever's focused.)
4. Have the Eyoyo paired, or know your hotkeys (below).
5. Do one silent dry-run: ⌘+Alt+1 → the red BLOCK card should appear. Then
   ⌘+Shift+C to dismiss.

---

## Running the demo (say / do)

**Frame it (10s).** *"This is a prototype. Work like you normally would — I'll
have you scan a couple of packs."* Keep focus in the stand-in app.

**Beat 1 — a clean one.** DO: scan a pack (or ⌘+Alt+2). SAY: *"Scan a pack like
usual."* → a green **Clear** card. *"When there's nothing to flag, it just
confirms and gets out of your way."*

**Beat 2 — the catch.** DO: scan the "block" pack (or ⌘+Alt+1). → red **Do not
dispense** card (Maria Stavrou / amiodarone + warfarin). SAY nothing at first —
let them read it. Then: *"You didn't do anything different. You scanned. It
caught an interaction with something already on her record."*

**Beat 3 — the point.** SAY: *"Notice you never left your software. No login, no
typing, no second screen. Same scan you already do."*

**Then shut up and ask:**
- "Would this help or get in the way at your counter?"
- "Is the timing right — before you hand it over?"
- "Too much on the card, too little?"
- "Where would you *want* it to appear?"

Let silence do the work. You're testing whether a passive, scan-triggered safety
layer fits their real workflow — not selling it.

---

## Scenario cheat-sheet

Each hotkey (and each real pack, mapped deterministically) shows one scenario:

| Key | Patient | Verdict | The catch |
|---|---|---|---|
| **⌘+Alt+1** | Maria Stavrou | 🔴 **BLOCK** | Amiodarone + warfarin — over-anticoagulation. *The headliner.* |
| ⌘+Alt+2 | Sarah Johnson | 🟢 Clear | Nothing to flag — the "gets out of the way" case. |
| ⌘+Alt+3 | James Martinez | 🟠 Review | Overlapping anticoagulants (acenocoumarol on file). |
| ⌘+Alt+4 | Maria Garcia | 🟢 Clear | No duplicate ACE inhibitor. |
| **⌘+Alt+5** | Nikos Papadopoulos | 🔴 **BLOCK** | eGFR 24 — metformin contraindicated (renal). *Second strong one.* |
| ⌘+Alt+6 | Eleni Demetriou | 🟢 Clear | No duplicate statin. |
| ⌘+Alt+7 | Andreas Vasilakis | 🟠 Review | Overlapping antiplatelets (aspirin). |
| ⌘+Alt+8 | Sofia Ioannidou | 🟠 Review | Paediatric weight-based dose — verify weight. |

*(On Windows swap ⌘ for Ctrl.)*

**Two ways to trigger, same result:**
- **Real Eyoyo pack** — the authentic feel. Your packs are GS1 medicine packs
  with no prescription attached, so the agent maps each pack to a scenario
  *deterministically* — the **same pack always shows the same card**. Scan a pack
  once during setup to learn which scenario it lands on, then use it on purpose.
- **Hotkeys** — exact control, no hardware. Best when you want to guarantee the
  BLOCK lands at the right beat.

---

## Hotkeys

- `⌘/Ctrl + Alt + 1…8` — fire scenario 1–8
- `⌘/Ctrl + Shift + C` — dismiss the current card
- `⌘/Ctrl + Shift + H` — hide / show the overlay
- `⌘/Ctrl + Shift + Q` — quit the agent

---

## Reset between subjects

Just ⌘+Shift+C to clear the card. The agent keeps running — no restart needed.
To hide it entirely between sessions, ⌘+Shift+H.

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| Pill says **"Backend login failed"** | Backend isn't up. `docker compose up -d backend db`, wait ~10s, restart the agent. |
| Scanning does nothing (pill stays green) | macOS Accessibility not granted to the launcher app → grant it and re-launch. Verify with a hotkey (⌘+Alt+1) — if *that* works, it's the Accessibility grant. |
| A hotkey does nothing | Another app owns that shortcut. Check the launch log for `hotkey … FAILED`. |
| Card shows **"No prescription found"** | You scanned a printed `RX2024-xxx` barcode whose id has no mock data — use the packs/hotkeys, or the barcodes from `npm run barcodes`. |
| Overlay off-screen / wrong monitor | Quit (⌘+Shift+Q) and relaunch; it re-anchors top-right of the primary display. |

---

## What this is / isn't

- **Is:** a research prototype on **mock data** — every verdict is a curated
  scenario, not a live ΗΔΥΚΑ call. Perfect for testing the *experience*.
- **Isn't:** production. Real scanning needs the ATC-normalization + a live
  ΗΔΥΚΑ credential (separate track), and shipping needs code-signing (a global
  hook + always-on-top overlay is exactly what AV/Gatekeeper flag). See
  `../docs/parasitic-agent-plan.md`.
