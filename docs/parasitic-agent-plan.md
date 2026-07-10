# Parasitic Safety Agent — thesis + execution plan

> Status: **thesis validated in reasoning, not yet built.** This doc is the
> pickup point for a future build session. Nothing here has been implemented;
> the backend loop it builds on is partially live (see "What already exists").
>
> Related research: [`going-real-live-mode-ux.md`](going-real-live-mode-ux.md)
> (branch `docs/live-mode-ux` — the scan/PIN retrieval findings) and decision
> **D-19** in [`b2b-core/TIER2-AUDIT.md`](b2b-core/TIER2-AUDIT.md) (pull-vs-push
> dispense data — the *cooperative* alternative this plan deliberately avoids).

## The problem this solves

A Greek pharmacist lives inside an incumbent pharmacy OS — **Farmakon** (CSA /
Epsilon Net, >50% market share, ~5,200 of ~10,400 pharmacies). Its clinical
layer (`f-anazitisi`) is a **passive drug-reference encyclopedia**, not an
active safety engine. PharmAssist's differentiator is the *active, contextual*
safety engine. But a separate SPA the pharmacist must alt-tab into and re-scan
is a workflow tax they won't pay.

**The parasite removes the tax entirely:** the pharmacist keeps scanning into
Farmakon exactly as today and does *nothing* extra; we ride the scan they
already make and pop a safety verdict beside Farmakon. No Farmakon integration,
no CSA deal, no ΗΔΙΚΑ capability that doesn't exist.

## Why it's buildable — every load-bearing question is retired

| Question | Answer | Evidence |
|---|---|---|
| Get the prescription without Farmakon? | Yes — scan → ΗΔΥΚΑ `GET /api/v1/prescriptions/get/{barcode}` | `pharmapi.py:717` (`pharmapi_get_prescription`), live + real CDA parse |
| Run safety without the incumbent's data? | Yes — own `patient_conditions` + on-prescription drug-drug both live | `patient_condition.py`, `safety_engine.py:221-239`; B2B `/v1/safety/check` |
| Ride the existing scan with zero extra action? | Yes — barcode scanner is a keyboard-wedge HID device; a local hook sees the same keystrokes | design, this plan |
| Can a browser do it? | **No** — sandbox blocks global key capture + always-on-top overlay; WebHID blocks keyboard-class devices | structural |
| Will ΗΔΙΚΑ let our agent read alongside Farmakon? | Yes — stateless per-request auth (Basic Auth + Api-Key each call), soft account-level 24h window, `G14` self-heals; multi-terminal single-account pharmacies already prove same-account concurrency | `pharmapi.py:199-296`; empirical market fact |

What's left is **execution, not architectural risk.** Nothing below is gated by
CSA, ΗΔΙΚΑ, or a partnership.

## What already exists (build on, don't rebuild)

- **Scan → retrieve → safety is one call, live where it's DB-rule-based.**
  `GET /prescriptions/{barcode}` (`routers/prescriptions.py:126`) resolves the rx
  and attaches `safetyChecks` inline via `checks_for_prescription`.
- **B2B `/v1` surface is the natural agent API** — designed for an external
  caller with its own software: `POST /v1/safety/check` (`routers/v1/safety.py:55`)
  takes explicit meds + co-meds, resolves ATCs, runs `evaluate_safety`. API-key
  per location.
- **Safety engine**: `services/safety_engine.py`, 18 seeded rules
  (`scripts/seed_data.py`): 12 interactions, 4 contraindications, 2 duplicate-therapy.
- **Live today**: drug-condition contraindications (own `patient_conditions`),
  B2B explicit-list drug-drug interactions.
- **Mock-only / stubbed today** (the bounded gap): live ΗΔΥΚΑ intolerances are
  *fetched but not evaluated* — engine reads hardcoded `MOCK_INTOLERANCES`
  (`safety_engine.py:22-32,198-219`) because `activeSubstance → ATC` mapping is
  unbuilt; live co-med drug-drug doesn't fire because upstream history lacks
  barcodes (`safety_engine.py:170-173`).

---

## Execution plan

### Phase 0 — De-risk spikes (cheap, before any native code)
- [ ] **Concurrent-session smoke test** against test pharmacy `70014`: two
  authenticated clients hitting `/get/{barcode}` at once, watch for `G14`
  churn. Considered retired by reasoning + market fact; this is 30-min
  insurance, optional.
- [ ] **Scanner sentinel framing**: program the Eyoyo EY-H2 with a distinctive
  prefix/suffix (STX/ETX or rare sentinel). Confirm a scan burst is positively
  identifiable so the hook reacts ONLY to sentinel-framed input — never a
  general keylogger. (See memory: Eyoyo EY-H2 is the confirmed testbook scanner.)
- [ ] **Latency budget**: measure `/get/{barcode}` + `evaluate_safety`
  round-trip. Overlay must land before the pharmacist hands over the meds
  (target sub-second-ish).

### Phase 1 — Backend readiness (form-factor-independent plumbing)
- [ ] **Build the ATC-normalization layer** — the single change that flips the
  most mock-only checks to live. `activeSubstance` / `commercialName → ATC`
  resolver, plugged into:
  - the intolerance section (`safety_engine.py:198-219`) → live allergy checks
  - the co-med path (`safety_engine.py:170-185`) → live drug-drug from history
  - Source: EOF/ΕΟΦ drug registry or the ΗΔΥΚΑ medicine catalog. Decide + wire.
- [ ] **Confirm the agent's call surface.** Prefer the B2B `/v1` path (API-key,
  per-location identity) over B2C session-cookie. Agent authenticates as its
  own location context.

### Phase 2 — The native agent (thin Cluely-style shell)
- [ ] **Shell**: **Tauri** (Rust core + WebView2, small footprint — right for a
  machine whose day job is Farmakon). Electron only if reusing the SPA verbatim
  is faster for a first proof.
- [ ] **Global keyboard hook** (`WH_KEYBOARD_LL` on Windows), filtered to
  sentinel-framed bursts — sees the scan while Farmakon holds focus, logs
  nothing else.
- [ ] **On capture** → call the `/v1` safety endpoint → render an
  **always-on-top, click-through, non-focus-stealing overlay**. Reuse the React
  alert-card components from the SPA.
- [ ] Advisory only — beside Farmakon's transaction, cannot (and should not)
  block a dispense. Frame as co-pilot.

### Phase 3 — Distribution & trust
- [ ] **Code-signing cert** (EV preferred for SmartScreen), signed installer
  (MSI/NSIS), auto-update channel.
- [ ] **AV/EDR**: a global hook + always-on-top overlay is a malware signature.
  Scoped sentinel-only reaction + signing + a clear consent flow are the
  mitigations. Budget for false-positive triage with major AVs.
- [ ] **Consent/privacy**: pharmacy agreement; the hook must be demonstrably
  scoped to barcode input.

### Phase 4 — Pilot
- [ ] Single friendly pharmacy running Farmakon. Measure: overlay latency,
  false-positive rate, `G14` churn in the wild, pharmacist-perceived friction.

## Explicitly out of scope (deliberately)
- **AMKA + PIN `/nopaper` path** — does not exist in the codebase; barcode scan
  is the only wired retrieval path. Not needed for v1 parasite.
- **Farmakon dispense-event push (D-19)** — the *cooperative* track. Cleaner and
  can be in-transaction, but needs CSA to say yes. Keep as a future upgrade if a
  partnership ever materializes; the parasite is the no-permission wedge.
- **Blocking a dispense** — we're beside the transaction, not in it, by design.

## Open decisions to make at build time
1. ATC-normalization data source (ΕΟΦ registry vs ΗΔΥΚΑ catalog).
2. Tauri vs Electron for the first proof.
3. Overlay trigger: fire on every sentinel scan, or only when a rule matches
   (silent-unless-alert)?
