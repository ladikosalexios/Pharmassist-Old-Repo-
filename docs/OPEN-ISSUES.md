# Open Issues — Engineering Backlog

> **Trello is the source of truth for sprint tickets.** This file is the running
> *engineering* backlog: the smaller open problems, caveats, and follow-ups that
> surface during implementation — the companion to the board, not a replacement.
> Keep it a register: one line per item, a status, and a dependency/owner where
> known. Status vocabulary: `open` · `blocked-on-<X>` · `done-pending-<Y>`.

_Last touched: 2026-09-23._

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

- `resolved 27.09.2026` — **T0-1 was a hard external dependency** for Second Opinion (the
  doctor product, its own repo at `~/Desktop/second-opinion`), which consumes this repo's
  `/v1` as an ordinary external customer presenting no ΗΔΥΚΑ credentials. T0-1…T0-4 merged in
  #181, so its SO-7 is unblocked. It buys tier **`core`**, not `clinical_only`: it needs
  `/v1/drugs/{barcode}/alternatives` to answer the host's commercial-name gate, and that
  route is `require_tier("core")`. Nothing else here depends on that product, and its plan is
  not tracked in this repo.
- `open` — **T0-5 now blocks Second Opinion's clinical half, and it is the last thing between
  us and a true pitch.** `routers/v1/safety.py` exposes none of the safety engine's 36 SPC
  references, so every `/v1` caller gets rule-based findings with no citations. Second
  Opinion requires outward provenance (source document, section, authority, retrieval date)
  on every clinical finding and cannot populate it from the API until T0-5 lands. Per
  `TIER0-RETRIEVAL-FREE.md` §4, do not demo the clinical half in this window: uncited
  rule-based findings are the one thing f-anazitisi already does better.
- `partly done` — **Tier-0 "clinical-only" /v1 tier** (ships without production ΗΔΥΚΑ) — see
  `docs/b2b-core/TIER0-RETRIEVAL-FREE.md`. **T0-1…T0-4 merged in #181** (27.09.2026): the
  unconditional 500 is gone, retrieval routes answer 409 `retrieval_unavailable`, `TIER_ORDER`
  is `("clinical_only","core","clinical","platform")`, and `create-location --no-retrieval`
  provisions a credential-less location. D-20/D-21 decided. **T0-5 (SPC over `/v1`) and T0-6
  (un-stale `TIER2-AUDIT.md`) remain open.** Still open inside T0-4: no CLI command adds
  credentials to an existing location — provision a new one.
- `open` — **`TIER2-AUDIT.md` is stale on SPC** (T0-6): it claims the safety engine has zero
  SPC references; there are 36 since #178, and T2-8's proposed `spc_sections` table diverged
  from the shipped `sections` JSONB design — re-spec T2-9 before building from it.
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
