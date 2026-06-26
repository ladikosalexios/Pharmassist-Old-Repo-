# HMVO IQE Testbook — Readiness Assessment & Runbook

## Context

PharmAssist is pursuing HMVO (Hellenic Medicines Verification Organisation) IT-supplier
qualification. The gate is a **Testbook on the IQE platform** (`portal-gr-iqe.nmvo.eu`),
declaring **API 3.1**, **UTC datetimes**, **HMVS release R18**. The flow under test is the
"Επαλήθευση συσκευασίας φαρμάκου" DataMatrix scan → verify + decommission against the NMVS/HMVS.

This document is a **readiness assessment + execution runbook** produced from a read-only
review of the codebase. The fixes it identifies — **G1**, **G2**, and the **`hmvs-scope.md`
rewrite** (PC-1/PC-2/PC-3 below) — are **planned items for a separate implementation pass**,
each approved individually; this document does not change any code or config.

**Mock vs live:** dev runs `HMVS_MOCK=true` (canned responses); the testbook MUST run live
(`HMVS_MOCK=false`) against IQE. Divergences are flagged ⚠️.

**Scenario source (testbook received):** the authoritative scenario definitions are the **EMVS
ITE Test Book V15.1 [API v3.1]** (the ITE reference document) plus HMVO's IQE test packs (the
**IDIKA ePrescription DataMatrix sheet**, received 12 Jun 2026 — GTIN `05060917518062`, serials
`SN_IDIKA/…`). The **binding** list for certification is the **self-service qualification
testbook generated on the IQE portal**, which is **scoped to your client role** (pharmacy vs
wholesaler). Generating it resolves exactly which sections apply (see Q-F0).

---

## 0. Testbook #146 — execution checklist (definitive scope)

Generated qualification testbook **#146** (NMVS Qualification Test Book v3.1) defines 13 cases.
The testbook **explicitly allows per-step results of Pass / Fail / N/A** (N/A = "not applicable to
the IT Supplier's solution"), so PharmAssist's dispense-only scope is handled by declaring the
unsupported cases **N/A**. **CONFIRMED by the Filippidis call (24 Jun 2026):** private pharmacy runs
**3.5–3.12 except 3.8** → **05/06/07/09/10/11/12**, with **08 (Decommission) wholesaler-only → N/A**;
bulk (01–04) and Report (13) out. Matches our plan.

### 0.1 — The 13 cases

| # | Case | Plan | Notes / flags |
|---|---|---|---|
| 01 | BULK_VERIFY | **N/A** | bulk not built (G8) |
| 02 | BULK_SUPPLY | **N/A** | G8 |
| 03 | BULK_REACTIVATE | **N/A** | G8 |
| 04 | BULK_DECOMMISSION | **N/A** | G8 |
| 05 | SINGLE_VERIFY | **RUN** | ⚠️ step 7 needs **NMVO Non-FMD rule**; ⚠️ **G10** (extra-AI parsing) |
| 06 | SINGLE_SUPPLY | **RUN** | our dispense; screenshot step 7 (+ steps 2,5 if double-dispense limit ≤1) |
| 07 | SINGLE_REACTIVATE | **RUN** | < 10 days, **same location** only |
| 08 | SINGLE_DECOMMISSION (Destroyed/Free Sample) | **N/A** | G9, dispense-only (step 8 Non-FMD rule moot if N/A) |
| 09 | ALERTS | **RUN** | screenshot-heavy (**steps 1–15**). UI **displays the registry `warning`/`information`** (`DispenseWizard` → `pack.error`, PackRow red text) ✓; **`alertId` is NOT surfaced in the UI** (minor — it's in the transaction logs; consider adding it for stronger evidence) |
| 10 | MANUAL ENTRY | **RUN** | `HmvsSecureInput` manual entry supported |
| 11 | CHARACTER_SET (GS1 set 82) | **RUN** | ⚠️ **G10 confirmed** — CS_4 packs carry **extra AIs** (NHRN/prod-date/potency) → parser must skip unknowns. Also: scanner must transmit **FNC1/GS** (CS_6 AI-like sequences) + read **inverse-colour** matrix (CS_5). PPN sub-step N/A. Backend already percent-encodes special chars (CS_1). |
| 12 | INVALID_GS1_ELEMENTS | **RUN** | ✅ all four invalid packs now **sent → registry 422** (61020008/11/06/07, confirmed live; G11 / PR #153); operationCode shown in the pack row (G12) |
| 13 | REPORT API | **N/A** | no Reporting API in scope |

→ **Run: 05, 06, 07, 09, 10, 11, 12.  N/A: 01–04, 08, 13.**

> **Evidence surface:** all live scenarios run through the **Dispense wizard** (`DispenseWizard.tsx`)
> — the only UI that calls HMVS. **`/hmvs-check` never calls HMVS** (it's the input-guard demo only,
> used for the already-accepted Caps Lock / layout recording). Don't capture verify/supply/alert
> evidence there.

### 0.2 — Prerequisites
- [ ] **NMVO to create Non-FMD Rules** for `05` step 7 (and `08` step 8 if not N/A) — ask HMVO
- [x] Location approved (Create active) · [x] Equipment + Client ID/Secret saved & in `backend/.env`
- [x] R18 CA present (probe TLS OK) · [x] Pre-flight probe passed (token + verify 200 Active + NHRN)
- [ ] **Container pointed at IQE for the UI run** — `compose.yaml` hardcodes `HMVS_MOCK=true` and the
      container does **not** read `backend/.env`; the live UI run needs the container in live mode
      (compose override / env). The probe worked via injected env only.

### 0.3 — Evidence (per the testbook)
- [ ] Screenshots for every alert-generating step: **06.7** and **all of 09 (steps 1–15)** (01–04 N/A)
- [ ] Extra screenshots if double-dispense limit ≤1: **06.2, 06.5**
- [ ] Transaction **logs**; **start/end test datetime in UTC** (§2.5 + portal)
- [ ] Per case: applicability (Yes/No), completion datetime (UTC), per-step result (Pass/Fail/N/A), comments
- [ ] Submit via portal categories: Test Book / Screenshot / Log / Other

### 0.4 — HMVO confirmations (Filippidis call, 24 Jun 2026)
- [x] **Q1 (gate) — RESOLVED:** private pharmacy = run **3.5–3.12 except 3.8** → **05/06/07/09/10/11/12**; **08 (Decommission) wholesaler-only → N/A**; bulk (01–04) + Report (13) out.
- [x] **Q2 — equipment is pharmacy / with-NHRN** (verify returns NHRN live).
- [x] **Q3 (Non-FMD) — RESOLVED, no code:** scan the QR; HMVO handles non-FMD their side (through the firewall, collects the call).
- [x] **Q4 (double-dispense) — procedure clear:** supply the same pack twice; the 2nd call returns the error/alert (limit is HMVO config).
- [x] **Q5 / case 12 (G11) — RESOLVED:** invalid packs are **sent** so the 422 shows (expected behaviour confirmed). Implemented — PR #153 on main.
- [ ] **Scanner config (case 11):** confirm the Eyoyo transmits **GS/FNC1** + reads an **inverse-colour** DataMatrix (CS_5) — hardware test.
- [x] PPN sub-steps → N/A (GS1-only).  · [x] Location / API-version — resolved.

---

## A. Readiness matrix

### Requirements 1–6

| # | Requirement | Status | Where (verified) | Gap |
|---|---|---|---|---|
| 1 | Entire UI in Greek (e.g. "Serial Number" → "Σειριακός Αριθμός"), not just data | ⚠️ **Partial — must-fix** | `el.json` comprehensive; verify/dispense copy all i18n'd. **But** `lib/i18n.ts:15-19` detection order `["querystring","localStorage","navigator"]`, `fallbackLng:"el"` → a non-Greek browser renders **English**. And the **serial renders unlabeled & truncated** (`DispenseWizard.tsx:735-736`, `⋯{serial.slice(-8)}`) — no "Σειριακός Αριθμός" label exists. | **G1 + G2 (must-fix before run).** |
| 2 | NHRN (Κωδικός ΕΟΦ) visible to end user | ✅ **Yes** | Label `dispense.nhrnLabel` = "Κωδικός ΕΟΦ"; pack row (`DispenseWizard.tsx:745-748`) + step-2 summary (`534-540`); value from verify response (`lib/hmvs.ts:114`). | Conditional on response carrying `nhrn` — confirm IQE packs return it (mock pins `GR-0000-0000-0000`). |
| 3 | No send when Caps Lock on + blocking warning | ✅ **Built & approved** | `useCapsLockState.ts` (latch), `HmvsSecureInput.tsx`; `hmvs.capsLockWarning`. Latch fix `c7710d5`. | None. |
| 4 | No send when keyboard layout ≠ English + blocking warning | ✅ **Built & approved** | `useNonLatinInputDetector.ts` (`/[^\x00-\x7F]/`), `HmvsSecureInput.tsx`; `hmvs.layoutWarning`. | None. |
| 5 | No send during inventory (απογραφή) / price-check (ένδειξη τιμών) / orders (παραγγελίες) | ✅ **Satisfied — evidence re-based** | **Verified facts:** (a) ESLint `no-restricted-imports` (`eslint.config.js:37-61`) blocks every `**/lib/hmvs*` import across `src/**`, with the **sole** override `src/components/DispenseWizard.tsx:59-60`; (b) full-source search finds **no** inventory/price/order page, route, or backend router; (c) HMVS is invoked only at `DispenseWizard.tsx:236/316/384`. | None (code). Needs a written attestation **citing the ESLint gateway + absent features**, NOT the prose doc (which is stale — see PC-3). |
| 6 | Compatible with HMVS R18 / API 3.1 | ⚠️ **Likely yes, confirm** | R18 H-cert TLS probe at boot (`services/hmvs.py:270-303`); EMVS `emvs-data-entry-mode` header live-confirmed vs IQE (`:56-69`); responses parsed structurally. **No explicit `3.1` marker in requests.** | Confirm per-request version header need (Q-F2, do not assume); close F2 (429); confirm IQE H-cert probe host. |

### Testbook operations

| Operation | Implemented | Where (verified) | Notes |
|---|---|---|---|
| Pack **verify / check** | ✅ Yes | FE `lib/hmvs.ts:152`; BE `routers/hmvs.py:91` `GET …/product/gs1/{gtin}/pack/{serial}?batch&expiry`; svc `services/hmvs.py:323` | GS1 percent-encoded; `emvs-data-entry-mode: manual\|non-manual`. |
| **Supply** (→ `Supplied`, on dispense) | ✅ Yes | FE `lib/hmvs.ts:165`; BE `routers/hmvs.py:146` `PATCH {"state":"Supplied"}`; svc `:346` | Idempotency guard (`services/hmvs.py:379-487`, unique `idempotency_key`). |
| **Decommission → `Destroyed` / `Sample`** | ❌ **Not implemented** | — | **New gap (G9).** Testbook table 69 — a *pharmacy* may set Active/Supplied/**Destroyed**/**Sample**; testbook has a dedicated **"GS1 - Decommission Single Pack Tests"** section (¶459-460). PharmAssist is **dispense-only** → sends only Supplied/Active by design. Conditional on role scope (Q-F0). |
| **Reactivate / undo** (→ `Active`) | ✅ Yes | FE `lib/hmvs.ts:184`; BE same PATCH `{"state":"Active"}` | Reversal window **confirmed by ITE Test Book V15.1 ¶480/¶1833**: succeeds only if decommissioned/supplied **< 10 days ago at the same location**, else 409. Code doesn't hard-code it; defers to the registry. |
| **Bulk-of-pack** | ❌ **Not implemented** | FE has a `statusVerifiedBulk` *display* badge only; **no** backend bulk endpoint | Testbook **"GS1 - Linked Tests" → Bulk-of-pack** + **"Bulk Common Error Tests"** (¶1618). Single-pack only here. Conditional on role scope (Q-F0). |
| **Exception / alert-state** | ⚠️ **Display-only** | `alertId`, `warning`, `information` surfaced read-only (`services/hmvs.py:181-217`, `lib/hmvs.ts`); no lifecycle/mutation | Matches the testbook expectation — alerts are *raised by the NMVS and shown* (¶139); the client highlights the `alertId`. Likely sufficient; verify the repeated-supply→alert row. |
| **UTC datetimes** | ✅ Yes | `services/hmvs.py` `datetime.now(UTC)`; Retry-After normalised to UTC | No client-sent request timestamp. |
| **OAuth2 auth** | ✅ Yes | Client-credentials → Bearer; token cache + skew (`services/hmvs.py:223-256`); creds per-pharmacy (encrypted) or env fallback (`services/hmvs_credentials.py`) | |
| **Audit trail** | ✅ Yes | `HMVS_VERIFIED / _DECOMMISSIONED / _REACTIVATED` (`services/audit.py`); logs serial, not full QR | |

---

## B. Gap list (ranked)

**G1 — i18n defaults to browser language, not Greek. (Req 1, MUST-FIX before testbook).**
`lib/i18n.ts:15-19` uses `["querystring","localStorage","navigator"]`; a non-Greek browser
renders English, failing Req 1. **Planned fix:** drop `"navigator"` from the detection order
→ `["querystring","localStorage"]`, keep `fallbackLng:"el"`. Result: defaults to Greek while
still honouring an explicit `?lng=…` or a stored `pharmassist_lang` preference (so `en` stays
reachable for internal use). *(Heavier alternative: hard-pin `lng:"el"` — not preferred, kills the switcher.)*

**G2 — Serial unlabeled & truncated. (Req 1, MUST-FIX before testbook).**
Serial shows as `⋯<last 8 chars>` with no label (`DispenseWizard.tsx:735-736`). HMVO named
this exact term, so it is **in-scope, not optional.** **Planned fix:** add
`dispense.serialLabel = "Σειριακός Αριθμός"` (el) / "Serial Number" (en) and render the
**full** serial (labeled) on the verify result.

**G3 — 429 Retry-After parsed but not auto-replayed (audit F2). (Req 6, MEDIUM).**
`services/hmvs.py` returns `queued`/`retryAfterSeconds` but has no scheduler; replay is manual.
IQE throttling during a fast run could surface a queued state. *Close:* honour the delay with a
background replay, or document the manual-replay behaviour for the testbook.

**G4 — No explicit API-3.1 version marker in requests. (Req 6, LOW–MED, unconfirmed).**
Code parses responses structurally; version is likely declared via portal/equipment, not per
request. *Resolve via Q-F2 — do not assume either way.*

**G5 — Mock cannot exercise 403/422/429 (audit F4). (LOW for the live run).**
The testbook runs live, so IQE exercises these; relevant only to dry-run coverage and FE
error paths. *Close:* optional mock sentinels.

**G6 — No prod-vs-IQE endpoint guard. (Operational, LOW — not testbook-blocking).**
Only the `/identity`-suffix boot check exists (`config.py:65-88`). *Close:* optional ENV↔host assertion.

**G7 — `data_entry_mode` not persisted on store-and-forward rows. (LOW).**
Replays re-issue as `"manual"` (`OPEN-ISSUES.md`). Matters only if a queued pack replays mid-testbook.

**G8 — Bulk-of-pack not implemented. (Conditional on role scope — Q-F0).**
Testbook has Bulk-of-pack (Linked Tests) + Bulk Common Error sections (¶1618). PharmAssist is
single-pack only. Needed only if the IQE pharmacy testbook generates bulk scenarios.

**G9 — Decommission to Destroyed/Sample not implemented. (Conditional on role scope — Q-F0).**
A pharmacy client may set Destroyed/Sample (testbook table 69); the testbook has a
"GS1 - Decommission Single Pack Tests" section (¶459-460). PharmAssist is **dispense-only** —
it sends only Supplied/Active, by design and enforced by `hmvs-scope.md`. *Note:* closing this
collides with the deliberate dispense-only scope, so it is a **product decision**, not just a
build task. Needed only if the IQE pharmacy testbook requires the Decommission section.

**G10 — `parseGs1` aborts on unknown / additional AIs. (CONFIRMED — required to pass case 11).**
`parseGs1` (`lib/gs1.ts:67-70`) **`break`s on the first unknown AI**, so an extra AI before one of
the four required AIs drops fields → `isCompletePack` false → "scanMalformed", verify never fires.
*(Any order of the four known AIs is already handled.)* **Confirmed by testbook #146:** case
**11_CHARACTER_SET / CS_4** is *"verify a pack… containing additional data elements, such as NHRNs,
production date, and active potency"* → extra AIs → our parser breaks. So the fix is **required for
case 11**, not optional. **Fix:** skip unknown AIs via a GS1 AI length/format table (treat unknown
variable-length as FNC1-terminated). *(IDIKA scanner-check packs and the 05/06/07/09 packs are
standard 01/21/10/17 — no extras — so they're unaffected; the issue is case 11.)*
**Status: ✅ fixed on main (PR #150).**

**G11 — Invalid-GS1 handling (case 12). ✅ DONE (PR #153).**
`parseGs1` no longer validates 01/17 content, so all four invalid packs (GTIN/serial/batch/expiry)
are now **sent → registry 422** — confirmed live on IQE: GTIN **61020008**, serial **61020011**,
batch **61020006**, expiry **61020007**. The operationCode surfaces in the pack row (G12).
Missing-AI scans are still rejected locally via `isCompletePack`.

**G12 — Show the HMVS response body to the user. ✅ DONE (PR #152).**
Filippidis call: the registry response must be visible on the flagged steps. The status badge already
gives green/red; the pack row now also shows `operationCode` (success + failure) and the success
`information` message. Display-only.

---

## C. Testbook runbook

### C.1 — Point the app at IQE (production untouched)

Cleanest path: the **local stack with `backend/.env`**, which `backend/.env.example` already
pre-fills for IQE (`api-gr-iqe.nmvo.eu`, client `PharmAssist-IQE-1`). `compose.prod.yaml`
is left alone. *(Note: `config.py` code defaults to ITE — `:181/216` — so the IQE URLs must be
set explicitly; `.env.example` already does this.)*

1. `cp backend/.env.example backend/.env` (if absent).
2. In `backend/.env` set:
   - `HMVS_MOCK=false`  ← **critical: live, not mock**
   - `HMVS_IDENTITY_URL=https://api-gr-iqe.nmvo.eu`  *(host only — no `/identity` suffix)*
   - `HMVS_VERIFICATION_URL=https://api-gr-iqe.nmvo.eu/verification`
   - `HMVS_CLIENT_ID=<IQE equipment client id>` · `HMVS_CLIENT_SECRET=<IQE equipment secret>`  *(never commit; SSM in prod)*
   - `PHARMAPI_MOCK=true` (ΗΔΥΚΑ is separate; testbook is HMVS-only); `ENV=development` + `COOKIE_SECURE=false` for local.
3. Restart backend; confirm at boot: no `_validate_hmvs_identity_url` failure; and
   `[HMVS][TLS] developer-ite reachable …` (R18 H-cert) — ⚠️ if FAILED, the trust store lacks
   the NMVO CA; fix before running.
4. Pre-flight with the existing live probe `backend/scripts/hmvs_iqe_probe.py` (token-mint + one verify).
5. UI in Greek: launch with `?lng=el` (or, after G1, default Greek).

> ⚠️ **Do not** edit `compose.prod.yaml`. For a dedicated test box, use `compose.test.yaml` +
> `.env.test` overriding the URLs to `api-gr-iqe.nmvo.eu` (compose.test defaults to ITE).
> Secrets always via env/SSM, never the repo.

### C.2 — Testbook scenarios

> **Status:** the IQE test packs **were received** (IDIKA ePrescription DataMatrix sheet, 12 Jun
> 2026 — GTIN `05060917518062`, serials `SN_IDIKA/…`). The illustrative row table below stays
> illustrative until the **IQE self-service testbook is generated** — that defines the exact,
> role-scoped scenario list. The **"Code covers?"** column reflects the current build.

**ITE Test Book V15.1 section → PharmAssist coverage** (the binding subset is whatever the IQE
self-service testbook generates for the **pharmacy** role):

| Testbook section | PharmAssist | Note |
|---|---|---|
| GS1 — Verify Single Pack | ✅ | |
| GS1 — Supply Single Pack | ✅ | dispense |
| GS1 — Reactivate Single Pack | ✅ | < 10 days, same location |
| GS1 — Decommission Single Pack (Destroyed/Sample) | ❌ **G9** | dispense-only |
| GS1 — Inactive Batch / Product State | ⚠️ | response surfaced, no special flow |
| GS1 — Linked / **Bulk-of-pack** | ❌ **G8** | single-pack only |
| GS1 — Common / Bulk Common Errors | ⚠️ | structural error handling |
| GS1 — Connector-Specific Errors | ➖ | we're a **direct** pharmacy, not a connector → likely N/A |
| GS1 — Non-FMD Operation Codes | ⚠️ | codes passed through, not special-cased |
| GS1 — Character Set 82 | ⚠️ | serials percent-encoded; verify full set |
| **PPN** (all sections) | ➖ | German coding scheme; Greece is GS1 → likely N/A |

Scan surface for the manual UI run: **`/hmvs-check`** (no PHI, ideal for capture) and the real
**Dispense wizard** (`DispenseWizard.tsx`, steps 1/2 → 2/2). Illustrative scenarios:

| # | Pack (GTIN/serial/batch/expiry/NHRN) | Action | Expected HMVS | Expected UI (Greek) | Code covers? |
|---|---|---|---|---|---|
| 1 | Genuine, Active — `<PACK-A>` | verify | `200 state=Active`, `nhrn` | "Επαληθεύτηκε"; "Κωδικός ΕΟΦ: …"; submit enabled | ✅ Yes |
| 2 | Pack #1 | supply | `200 state=Supplied` | "Απενεργοποιημένη"; "Επιτυχής εκτέλεση" | ✅ Yes |
| 3 | Pack #1 re-scan | verify | `409` already-supplied | "Η επαλήθευση συσκευασίας απέτυχε" | ✅ Yes |
| 4 | Pack #1 | reactivate (in window) | `200 state=Active` | back to Active | ✅ Yes |
| 5 | Unknown serial — `<PACK-404>` | verify | `404 NMVS_NC_PCK_22` | verify-failed | ✅ Yes |
| 6 | Batch/expiry mismatch — `<PACK-B>` | verify | `404`/mismatch | verify-failed | ✅ Yes |
| 7 | Recalled/expired/stolen (alert) — `<PACK-ALERT>` | verify | alert/`alertId`+`warning` | warning shown; submit blocked | ⚠️ **Display-only** (no alert lifecycle) |
| 8 | Intermarket — `<PACK-IM>` | verify | `isIntermarket=true` | per response | ✅ Yes |
| 9 | Guard demo (recorded/approved) | Caps Lock / Greek layout → scan | **not sent** | blocking warnings | ✅ Yes |
| 10 | **Bulk** scenario (if HMVO requires) — `<PACK-BULK…>` | bulk verify/supply | n/a | n/a | ❌ **NOT built** — escalate (Q-F0) |

> ⚠️ Mock only branches on serials containing `"404"`/`"409"`; all real codes
> (403/422/429/alerts) appear **live only**. Run rows 5–8 against IQE.

### C.3 — Evidence capture
Per scenario: (a) UI screenshot (Greek, result/warning visible), (b) backend `audit_log` row
(action + `pharmapi_status`), (c) dry-run request/response log (Section E). Keep `?lng=el` and
result messages in frame.

---

## D. Targeted checks — findings

- **Req 5 (block during inventory/price/orders):** ✅ Satisfied, evidence **re-based on code**:
  ESLint `no-restricted-imports` (`eslint.config.js:37-61`) blocks all `**/lib/hmvs*` imports
  with the sole override `DispenseWizard.tsx:59-60`; no inventory/price/order feature exists in
  source (pages, routes, routers); HMVS called only at `DispenseWizard.tsx:236/316/384`.
  **No runtime guard needed.** ⚠️ `docs/hmvs-scope.md` is **stale** (its "Status — stubs until
  H6" section, lines 48-55, predates the build) — do **not** cite it as evidence until corrected
  (PC-3).
- **R18 / API 3.1:** H-cert TLS probe (`services/hmvs.py:270-303`); EMVS data-entry-mode header
  live-confirmed vs IQE (`:56-69`; `2d_two_dimensional_barcode` rejected 422/61020013 — never
  send). Structural parsing. ⚠️ No explicit `3.1` marker (Q-F2, unconfirmed); ⚠️ probe host is
  `developer-ite.nmvo.eu` — confirm IQE equivalent; ⚠️ F2 (429) open.
- **"Σειριακός Αριθμός" on step 2/2:** ❌ Not rendered (serial unlabeled/truncated,
  `DispenseWizard.tsx:735-736`). → **G2 (must-fix)**.
- **NHRN visible:** ✅ "Κωδικός ΕΟΦ" shown from the verify response (`lib/hmvs.ts:114`).
- **Caps Lock / keyboard guards intact:** ✅ Both call sites gated; latch fix `c7710d5` live.
- **Reactivation window:** **confirmed by the ITE Test Book V15.1 itself** (¶480/¶1833) — reversal
  succeeds only if decommissioned/supplied **< 10 days ago at the same location**, else 409. Code
  defers to the registry (aligns with Reg. (EU) 2016/161 Art. 13). Earlier "10 min" was wrong.
- **Testbook scope vs dispense-only design:** the testbook's full pharmacy surface includes
  **Decommission→Destroyed/Sample** (table 69) and **Bulk** (Linked/Bulk sections). PharmAssist is
  deliberately dispense-only (`hmvs-scope.md`), so these are **conditional gaps G8/G9** — real only
  if the IQE self-service testbook generates them for the pharmacy role. This is the central open
  question (Q-F0).
- **Connector vs direct:** Greece's NMVS supports a connector model (¶300-306) needing a
  `connector-location-id`; PharmAssist is a **direct** pharmacy integration (own Location +
  Equipment OAuth2), so **Connector-Specific** tests are likely N/A. Confirm the equipment role is
  registered as **pharmacy, with NHRN** (the testbook ships distinct credential sets per role, ¶190-218).

---

## E. Proposed dry-run harness (describe only — do not build yet)

A **live-IQE** pre-validation script, building on `backend/scripts/hmvs_iqe_probe.py` /
`hmvs_smoke.py`:
- **Input:** test-pack manifest (`iqe_packs.json|csv`: GTIN, serial, batch, expiry, expected
  state/code) — from the IQE test-pack list.
- **Behaviour:** force `HMVS_MOCK=false`; per pack call the **real** `services/hmvs.verify` →
  `change_state` (Supplied) → optional reactivate; assert status + `operationCode`/`state`.
- **Output:** append-only JSONL, UTC timestamps, request URL/method/headers (secrets redacted)
  + full response body — one line per op — as testbook evidence.
- **Guards:** refuse to run if `is_mock_hmvs()` (must hit IQE); redact `Authorization`; stop on
  auth failure with a clear message.

---

## Planned corrections (separate implementation pass — approve individually)

**Status: PC-1/PC-2/PC-3 implemented in PR #149** (branch `hmvo/greek-default-serial-label-scope-doc`,
pending review/merge). G8/G9 (bulk, decommission-states) remain conditional pending Q-F0.

These are surfaced by the assessment and are **not** part of producing this document:

- **PC-1 (G1):** `frontend/src/lib/i18n.ts` — remove `"navigator"` from `detection.order` →
  `["querystring","localStorage"]`, keep `fallbackLng:"el"`. Defaults to Greek; `?lng`/stored pref still honoured.
- **PC-2 (G2):** add `dispense.serialLabel` ("Σειριακός Αριθμός" / "Serial Number") to
  `el.json`/`en.json`; render the **full**, labeled serial on the verify result
  (`DispenseWizard.tsx` ~735 / step-2 summary).
- **PC-3 (hmvs-scope.md):** rewrite/remove the stale "Status — stubs until H6" section
  (lines 48-55) so it reflects the **built** integration (live `lib/hmvs.ts` GET/PATCH + full
  OAuth2 `services/hmvs.py`). **Keep** the Commitment, Single-gateway, ESLint-enforcement, and
  Out-of-scope sections intact.

---

## F. Open questions / what is needed

- **Q-F0 (RESOLVED → confirmation ask):** Testbook **#146 generated** — 13 cases (see §0). It
  includes Bulk (01-04), Decommission Destroyed/Free-Sample (08), and Report API (13), none of which
  PharmAssist implements. The testbook **explicitly allows Pass/Fail/N/A** per step. Plan: **declare
  01-04, 08, 13 N/A** and run 05/06/07/09/10/11/12. **Pending HMVO confirmation** that dispense-only
  N/A scope is accepted (email drafted) + equipment is **pharmacy, with NHRN**.
- **Q-F1 (G2):** Confirm "Σειριακός Αριθμός" labeled full serial on the verify result is the
  intended presentation (treating it as in-scope per direction given).
- **Q-F2 (API version):** The testbook is titled "API Version: 3.1" and HMVO's onboarding email
  declares 3.1 + UTC **at testbook submission** (step 9) — so likely **no per-request header**.
  Confirm against the `developer-ite.nmvo.eu` API docs; do not add a header unless required.
- **IQE credentials:** `HMVS_CLIENT_ID` / `HMVS_CLIENT_SECRET` from the IQE "Equipment" step
  (never in doc/repo; into `backend/.env` / SSM).
- **R18 probe host:** confirm whether the IQE H-cert host differs from `developer-ite.nmvo.eu`.
- **G1 default:** confirm OK to default the qualified build to Greek (drop `navigator`).

---

## Run-day checklist (execute the testbook)

**Environment — ready.** The backend runs **live against IQE** via the overlay (prescriptions stay
mock); probe confirmed token + verify 200 + NHRN from the container's own env:
```
docker compose -f compose.yaml -f compose.iqe.yaml up -d backend   # → live IQE
docker compose up -d backend                                       # → revert to mock
```

1. **Start.** Record the **start time (UTC)**. Open `http://localhost:5173` (login; Greek UI).
2. **Run the in-scope cases** — open a mock prescription → **Dispense** → scan the #146 packs:
   - **05** Verify · **06** Supply (+ double-dispense = supply the same pack twice) · **07** Reactivate (use the reactivate action)
   - **09** Alerts (screenshot each of the 15) · **10** Manual (hand-key) · **11** CharSet · **12** Invalid GS1 (→ 422)
   - Per step: confirm `state` / `operationCode` matches the expected value (now shown in the pack row); **screenshot** the flagged (red/green) + alert steps.
3. **Mark N/A:** 01–04 (bulk), 08 (decommission, wholesaler), 13 (report) — with a one-line comment.
4. **End.** Record the **end time (UTC)**.
5. **Fill the #146 doc:** per case — applicability (Yes / N/A), completion datetime (UTC), per-step result (Pass/Fail/N/A), comments; §2.5 IT-supplier info + start/end.
6. **Submit on the portal:** upload the completed testbook (**Test Book**) + **Screenshots**. The system auto-gathers the transaction logs from your start/end window (HMVO collects the call). Submit → HMVO reviews.

**Optional pre-validate** (learn each pack's operationCode before scanning):
```
docker compose exec backend python -m scripts.iqe_dryrun --manifest scripts/<packs>.json
#   add --supply --reactivate to exercise 06/07 (state-reversible)
```
