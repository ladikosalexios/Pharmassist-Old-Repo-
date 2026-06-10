# Open Issues — Engineering Backlog

> **Trello is the source of truth for sprint tickets.** This file is the running
> *engineering* backlog: the smaller open problems, caveats, and follow-ups that
> surface during implementation — the companion to the board, not a replacement.
> Keep it a register: one line per item, a status, and a dependency/owner where
> known. Status vocabulary: `open` · `blocked-on-<X>` · `done-pending-<Y>`.

_Last touched: 2026-06-10._

---

## HMVS / FMD qualification

- `done-pending-Solidsoft-signoff` — **emvs-data-entry-mode value.** Scan → `non-manual`, keyboard → `manual` (live-confirmed 200 on IQE `api-gr-iqe.nmvo.eu`); `2d_two_dimensional_barcode` is rejected (422/61020013). Confirm the canonical value set with Solidsoft. _(set in `services/hmvs.py`)_
- `open` — **data_entry_mode not persisted on the store-and-forward row.** Replay re-issues with `manual` (conservative — never over-claims a scan). Add a column to `HmvsOperation` (+ register in `alembic/env.py` & `main.py`) to make replay byte-honest. _(dep: small migration)_
- `open` — **ITE dry-run: 12 nhrn-assertion fails on GTIN combined-state supply packs** = Solidsoft sandbox quirk, not our bug. Optional written report. _(owner: Solidsoft)_
- `blocked-on-Filippidis` — **IQE qualification:** create Test Book in `portal-gr-iqe` → run scenarios → submit (API 3.1 + UTC). Needs the IQE pack list + keyboard-method confirmation.
- `blocked-on-real-IQE-packs` — **H7 HMVS end-to-end tests** await real IQE packs (current tests use mock + scanner-check packs).
- `blocked-on-Filippidis` — **Keyboard-layout detection** (character-analysis) pending; desktop-wrapper fallback if rejected.

## ΗΔΥΚΑ dispense

- `done-pending-matching-pack` — **Live eDispensation 200** needs a real pack whose HMVS Product Code matches the prescribed medicine. Not a code gap — verified `400/10018` (synthetic lot) → `400/10074` (pack↔Rx product match) with a mismatched test pack. _(see PR #132)_
- `open` — **X-DOCTOR-IP must be the pharmacist's real client IP** (`X-Forwarded-For` behind Caddy), for both `get/{barcode}` and `dispense` — currently the server egress IP. _(dep: Caddy proxy header config)_
- `open` — **nopaper (AMKA+PIN) fallback + re-enable the paperless tab** (Phase 2). The Dashboard tab is hidden behind `SHOW_PAPERLESS=false`; the barcode path already resolves paperless prescriptions, so this is a fallback only.
- `open` — **`_fetch_live_rx` `/search` fallback:** confirm it adds real coverage beyond `get/{barcode}` or drop it. _(routers/prescriptions.py)_
- `open` — **execution_case ∈ {0,2,3} (partial dispense) + reversal/cancel CDA** are out of scope today (`build_dispense_cda` raises on non-1). _(services/cda.py P3-followup)_
- `open` — **Enrich the safety engine** with the prescription CDA's ICD-10 diagnoses + dosage instructions (richer than the search JSON now used).

## Frontend

- `open` — **Pass the `counsel` flag to `approvePrescription`** once the approve body accepts a counseling flag; today the checkbox records intent only. _(DispenseWizard.tsx FR-3)_
- `open` — **Stub endpoints not implemented on the backend** (`updateProfile`, others under FR-0.5 #7). _(lib/api.ts)_
- `open` — **Final Greek-UI (H3) + NHRN / κωδικός ΕΟΦ (H4) QA pass** before qualification.

## Security

- `open` (pre-prod) — **Invite token in the URL path** lands in access logs / browser history. Move to a POST body or short-lived signed param once the SPA flow is finalized. _(routers/auth.py)_
- `open` (pre-prod) — **Invite token printed to stdout** leaks into container/aggregated logs. Replace with an email service before prod. _(routers/admin.py)_

## Deployment / infra

- `open` — **AWS pilot:** set `HMVS_*` SSM params; confirm the box trusts the R18 Sectigo chain + pulls the `certifi-2026.05.20` image.
- `open` — **`HMVS_MOCK` hardcoded `false` in `user-data.sh`** — parameterize via SSM if a mock-only internal pilot is wanted.
- `open` — **Merge PR #133** (credential rotation); **delete the throwaway probe** (`backend/scripts/pharmapi_live_probe.py`) when this work lands.

## B2B (post-pilot)

- `open` — **B2B Core (Tier-1) backlog** — see `docs/b2b-core/TICKETS.md` (supersedes the
  old B1–B6 Trello backlog) and `docs/b2b-core/FINISH-TIER1.md` (gap audit → FT-* tickets).
- `done` — **`PHARMAPI_MOCK` typo footgun** (FT-15): an unrecognized value (e.g. `flase`)
  silently routed dispense/verify/masterdata to MOCK on a live box. Now boot-validated
  fail-fast in `app/config.py`. _(Batch 2)_
- `blocked-on-D-11` — **FT-8 monitoring wiring** (LOG_FORMAT=json/SENTRY_DSN in a prod
  compose, external uptime monitor, error-rate alert) — needs the public live target.
  `GET /health/v1` + the OPERATIONS.md triage section shipped (FT-8 partial, Batch 2).
- `blocked-on-D-11` — **FT-10 public TLS live-mode deployment** + the FT-13 sandbox stack +
  the FT-12 docs URL ride it. Doc/paper shell (FT-9/FT-11/FT-12/FT-14) shipped in Batch 2.
- `done-pending-cleanup` — **dev-stack dry-run tenant** ("Batch2 DryRun SA") was created in
  the dev DB while validating the FT-9/FT-11 runbooks; inert mock data, safe to leave.
- `blocked-on-D-13` — **DPA/ToS legal text** — engineering annex (`DATA-PROCESSING.md`)
  ready for the legal author; owner TBD (longest external lead time).
