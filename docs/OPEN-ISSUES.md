# Open Issues — Engineering Backlog

> **Trello is the source of truth for sprint tickets.** This file is the running
> *engineering* backlog: the smaller open problems, caveats, and follow-ups that
> surface during implementation — the companion to the board, not a replacement.
> Keep it a register: one line per item, a status, and a dependency/owner where
> known. Status vocabulary: `open` · `blocked-on-<X>` · `done-pending-<Y>`.

_Last touched: 2026-07-15._

> **Retrieval-only:** prescription execution (eDispensation + HMVS/FMD) was
> removed at tag `hmvs-certified` — the HMVS-qualification and ΗΔΥΚΑ-dispense
> sections that lived here went with it (see the tag for the historical list).

---

## ΗΔΥΚΑ retrieval

- `open` — **X-DOCTOR-IP must be the pharmacist's real client IP** (`X-Forwarded-For` behind Caddy) for `get/{barcode}` — currently the server egress IP. _(dep: Caddy proxy header config)_
- `open` — **nopaper (AMKA+PIN) fallback + re-enable the paperless tab** (Phase 2). The Dashboard tab is hidden behind `SHOW_PAPERLESS=false`; the barcode path already resolves paperless prescriptions, so this is a fallback only.
- `open` — **`_fetch_live_rx` `/search` fallback:** confirm it adds real coverage beyond `get/{barcode}` or drop it. _(routers/prescriptions.py)_
- `open` — **Enrich the safety engine** with the prescription CDA's ICD-10 diagnoses + dosage instructions (richer than the search JSON now used).

## Frontend

- `open` — **Stub endpoints not implemented on the backend** (`updateProfile`, others under FR-0.5 #7). _(lib/api.ts)_
- `open` — **Final Greek-UI (H3) + NHRN / κωδικός ΕΟΦ (H4) QA pass.**

## Security

- `open` (pre-prod) — **Invite token in the URL path** lands in access logs / browser history. Move to a POST body or short-lived signed param once the SPA flow is finalized. _(routers/auth.py)_
- `open` (pre-prod) — **Invite token printed to stdout** leaks into container/aggregated logs. Replace with an email service before prod. _(routers/admin.py)_

## Deployment / infra

- `open` — **Merge PR #133** (credential rotation); **delete the throwaway probe** (`backend/scripts/pharmapi_live_probe.py`) when this work lands.

## B2B (post-pilot)

- `open` — **B2B Core (Tier-1) backlog** — see `docs/b2b-core/TICKETS.md` (supersedes the
  old B1–B6 Trello backlog) and `docs/b2b-core/FINISH-TIER1.md` (gap audit → FT-* tickets).
- `done` — **`PHARMAPI_MOCK` typo footgun** (FT-15): an unrecognized value (e.g. `flase`)
  silently routed verify/masterdata to MOCK on a live box. Now boot-validated
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
