# Finish Tier-1 B2B — gap audit + tickets (BC-16 → first paying integrator)

**Status:** 📋 **Phase 0 — audit + plan only.** This document is the deliverable; nothing
here is built. Paused for review before any Phase 1 work starts.
**Date:** 2026-06-10
**Baseline:** BC-1…BC-16 merged to `main` (PR #135) — `docs/b2b-core/TICKETS.md` is the
record of what shipped. 156 backend tests green incl. the /v1 suite
(`tests/test_v1_*.py`); pytest runs in CI (`.github/workflows/lint.yml:40-73`).
**Scope driver:** `docs/PharmAssist_Pricing.md` → Motion A, Tier 1 "Core"
(€15/location/month) + the cross-cutting ΗΔΥΚΑ/ΕΟΠΥΥ/609 notes.
**Constraint:** B2C stays untouched and green. Every ticket below is additive; the two that
touch shared code (FT-5, FT-7) carry explicit B2C-regression guards.
**Numbering:** tickets are FT-*n* ("finish Tier-1"); decisions continue TICKETS.md's
D-1…D-7 as **D-8…D-13**.

Audited 2026-06-10 against the live codebase; every claim carries file:line evidence, same
discipline as the BC audit.

---

## 0. What "ready to onboard a paying integrator" means

The gap is not the API surface — that exists, is tested, and has a runnable Postman
contract suite. The gap is everything around it:

1. The API can be reached at a **public TLS URL in live (non-mock) mode** — doesn't exist
   today (the only prod-flavour deployment is the Tailscale-only **mock** pilot box).
2. Abuse from one tenant can't degrade the others (**per-key rate limiting** — missing).
3. We can **see** error-rate/uptime and get paged before the customer notices
   (observability is opt-in and not enabled in any prod compose).
4. Operations are **runbook-driven**: provision a tenant, rotate a compromised key,
   re-sync the catalogue — all possible today via CLI, none written down.
5. The integrator gets **docs, a sandbox, and paper** (API reference beyond Postman,
   sandbox keys with defined semantics, ToS + GDPR DPA).
6. The two pricing-doc claims the data can't fully back yet — **co-pay %** and
   **coverage-filtered formulary** — are either delivered honestly or re-worded (D-9,
   D-10). We do not fake either.

---

## 1. Audit — gap item vs what exists today

| # | Item | Status | Evidence |
|---|---|---|---|
| A1 | /v1 per-API-key rate limit | **PARTIAL** | slowapi is installed app-wide (`main.py:179`, `app/observability.py:156-171`) but the only decorated endpoint is B2C `POST /auth/login` (`routers/auth.py:59`), keyed by client IP with `AUTH_LOGIN_RATE_LIMIT=10/minute` (`observability.py:153`). The /v1 envelope already maps 429→`rate_limited` (`routers/v1/errors.py:40`) — nothing ever emits it. `get_api_context` does an unthrottled DB lookup + AES decrypt per request (`routers/v1/deps.py:48-79`). |
| A2 | Co-pay % on insurance | **PARTIAL** | Drug-level co-pay **exists and is exposed**: masterdata `participationPercentage` → `drug_catalog.participation_pct` (`services/drug_catalog.py:81`, model `db/models/drug_catalog.py:43`) → `/v1/drugs` `participationPct` (`routers/v1/drugs.py:38`, `schemas/v1.py:74`). Patient/insurance-level co-pay is **absent from every integrated surface**: insurances payload has fund identity + flags only (`schemas/patient_insurances.py:15-24`; raw passthrough `services/pharmapi.py:938-959`); search JSON carries no participation field (`pharmapi.py:799-831`); the retrieval CDA parser extracts none and documents the source CDA doesn't surface it (`services/cda.py:358-377`). Never verified: the **full raw key-set** of `/getpatient/insurances` (our schema silently drops unknown keys; BC-13a probed masterdata only). |
| A3 | Formulary "filtered by ΕΟΠΥΥ coverage" | **PARTIAL** (code complete, data unpopulated) | Tri-state coverage + `coverageFilter=strict\|lenient` + ranking + `dataCaveats` all implemented (`services/formulary.py:90-93`, `:32`, `:182-187`; endpoint `routers/v1/drugs.py:64-94`). `positiveList` **is** in masterdata — no external ΕΟΦ import needed (`docs/b2b-core/masterdata-probe.md:7-10`, mapping `:14-19`). Gaps are operational: rows synced pre-BC-13 and the 20 seed rows have `eopyy_coverage=NULL` until the next **full** sync (`masterdata-probe.md:45-48`), and test-env values are placeholders — production value **quality** is unverified (`masterdata-probe.md:43-45`). |
| A4 | Collapse 3 inline `PHARMAPI_MOCK` reads | **MISSING** (deliberately deferred — has a safety nuance) | The three reads remain: `services/pharmapi.py:403` (credential verify), `:669` (dispense), `:1071` (masterdata) — all default **LIVE** (`"false"`), the opposite of `is_mock_pharmapi()`'s mock default (`app/utils/environment.py:6`). The divergence is intentional fail-live behaviour (see `pharmapi.py:662-668` and commit 3fcf012); a naive collapse would flip dispense to mock-by-default — a patient-safety regression. |
| A5 | Consent attestation **recording** (D-5 follow-through) | **PARTIAL** — found during this audit | D-5 (TICKETS.md) says "we **record** the attestation and pass `patientsConsent=true` upstream only then". The gate is enforced (`routers/v1/patients.py:68-74`, used at `:120`, `:138`) but the attestation is **never persisted** — no audit row, no log line ties (location, patient, timestamp, consent=true) together. GDPR lawful-basis evidence for relayed PHI reads is currently zero. Folded into FT-6. |
| B1 | Per-location session store | **PARTIAL by design** | In-process `PharmapiSessionStore` with per-key `asyncio.Lock` and an explicit narrow seam for Redis (`services/pharmapi.py:103-134`). Single worker pinned: `Dockerfile.prod:41` (`--workers 1`), documented in `docs/test-env-runbook.md:34-36` and `docs/pilot-runbook.md:305`. slowapi notes the same Redis swap path (`observability.py:133-137`). B2B sessions are lazy (`pharmapi.py:228-241`) so a restart costs one `/user/me` per location, not an outage. |
| B2 | Paid-API observability (error-rate / uptime) | **PARTIAL** | Request-id middleware exists (`observability.py:36-45`); JSON logging and Sentry are **opt-in and not enabled in the prod compose** (`observability.py:87-99`, `:105-128`; `compose.prod.yaml:73-102` sets neither `LOG_FORMAT` nor `SENTRY_DSN`). No per-request access log, no tenant attribution in any log line, no uptime monitoring, no error-rate alerting. `/health` exists but reports the **legacy** session, not /v1 health (`routers/health.py`). The only usage signal is `api_keys.last_used_at`, throttled to 5-minute granularity (`routers/v1/deps.py:25`, `:76-79`). |
| B3 | API-key rotation / revocation | **PARTIAL** | Mint + revoke CLI work end-to-end (`scripts/b2b_admin.py:98-126`); multiple active keys per location are supported (only `key_hash` is unique — `db/models/api_key.py`), so zero-downtime rotation (mint → deploy → revoke) is already possible. No runbook exists: no documented rotation procedure, no compromised-key procedure, no cadence. |
| B4 | Stable TLS-fronted /v1 deployment | **MISSING** | The only prod-flavour stack is the **mock pilot**: `compose.prod.yaml:79` hard-sets `PHARMAPI_MOCK: "true"`; the AWS box is Tailscale-only with `CADDY_TLS="tls internal"` (`deploy/aws/user-data.sh`, `docs/pilot-runbook.md:301-311`) — not publicly reachable, not live-mode. Caddy auto-HTTPS capability is wired but unused publicly (`compose.prod.yaml:42-46`). No deployment target exists where an integrator's `pa_live_…` key would work. |
| B5 | Masterdata sync operations | **PARTIAL** — found during this audit | `run_sync` swallows every exception into a `print` (`services/drug_catalog.py:149-159`); the admin trigger 202s regardless and says "check container logs" (`routers/admin.py:69-84`); there is no schedule (the pilot cron covers DB dumps only, `docs/pilot-runbook.md:216-224`) and no recorded last-sync status. Formulary quality silently decays if the sync stops. |
| C1 | Per-tenant provisioning runbook | **PARTIAL** | The tooling is complete: `create-customer` / `create-location --verify` (validates creds against ΗΔΥΚΑ + warns on unit-id mismatch, `scripts/b2b_admin.py:60-73`) / `mint-key` / `revoke-key` / `list`. `postman/README.md` contains a 3-step demo skeleton. Not written: how to collect a location's ΗΔΥΚΑ creds securely, how to establish the ΕΟΠΥΥ category (`--eopyy` ⇄ ΗΔΥΚΑ isIka, the 609 rule), sandbox-vs-prod sequencing, post-mint verification, who runs it. |
| C2 | Sandbox vs prod key separation | **PARTIAL** (cosmetic only) | `mint-key --env test\|live` only changes the `pa_<env>_` prefix string (`services/api_keys.py:22-24`, `scripts/b2b_admin.py:41-43`, `:189`) — both kinds resolve identically against the same DB and the same upstream (`pharmapi_base` is a single deployment-wide setting, `app/config.py:155`, consumed in `routers/v1/deps.py:71`). "Sandbox" has no enforced semantics today. |
| D1 | API reference docs (beyond Postman) | **PARTIAL** | FastAPI auto-generates OpenAPI, but `/openapi.json` mixes /v1 with the **entire B2C surface** (one app, all routers — `main.py:115-132`, `:185-186`); there is no integrator-consumable v1-only reference, no auth/consent/error-code narrative. The Postman collection + env with per-request contract tests is real and runnable (`postman/README.md`). |
| D2 | API terms + GDPR DPA | **MISSING** | No legal documents anywhere in the repo (checked `docs/` and root). Pricing doc's cross-cutting AI/GDPR note doesn't apply to Tier-1 (no LLM features in Core) — but proxying ΗΔΥΚΑ PHI and storing `b2b_patient_conditions` absolutely does. |

**Audit surprises that shaped the plan:**

- **BC-13a's probe result reframes two of the asked questions.** The ΕΟΦ positive-list
  import is *not* needed for coverage (A3) — `positiveList` is in masterdata — and
  drug-level co-pay (A2) is already shipped on `/v1/drugs`. What remains for A2 is
  *patient-level* co-pay (exemption categories etc.), which no integrated surface
  carries, and one cheap unknown: the raw insurances key-set was never captured.
- **The "collapse the mock reads" cleanup is a footgun if done naively** — the three
  inline reads deliberately default live; `is_mock_pharmapi()` defaults mock. FT-5
  collapses the *duplication* while keeping the fail-live default (a second helper, not a
  behaviour change).
- **The prod-flavour stack is the mock pilot.** "Deploy /v1" is not "reuse
  compose.prod.yaml" — that file pins `PHARMAPI_MOCK=true` and the box has no public
  ingress. FT-10 is a real (if small) deployment work item, not a config tweak.
- **D-5's consent "recording" was never implemented** — the flag is checked and dropped.
  For a paid API relaying PHI, the attestation trail is the GDPR story (A5 → FT-6).
- **`--env test` keys are live keys with a different name.** Until FT-13, never hand a
  "sandbox" key to anyone you wouldn't hand a production key.

---

## 2. Tickets

Sizing vocabulary: **days** = 0.5–2 dev-days; **week** = 3–5+ dev-days. Estimates assume
one dev who knows the codebase, tests included.

### A — Functional / data

---

**FT-1 · Per-API-key rate limiting on /v1** — *build on wired infra* · **days (1–2)**

- Per-key limiter for every /v1 endpoint, keyed on the **hashed** `X-API-Key` (never the
  raw key, never client IP — integrators call from NAT'd server farms). Default e.g.
  `V1_RATE_LIMIT=120/minute` per key, env-overridable (same pattern as
  `AUTH_LOGIN_RATE_LIMIT`, `observability.py:153`).
- 429 must render in the **/v1 envelope** — slowapi's stock handler returns its own
  `{"error": "Rate limit exceeded…"}` shape, which violates the BC-5 contract. Either a
  custom `RateLimitExceeded` handler that branches on `/v1` paths, or skip the decorator
  approach and enforce inside `get_api_context` (cleaner: the key is already resolved
  there, and it avoids slowapi's pytest-passthrough hack `observability.py:188`).
  Include `Retry-After`.
- In-process counters share FT-7's single-worker constraint — fine now, note it; the
  Redis swap (FT-7) upgrades both together.
- Document the limit in the API reference (FT-12) + Postman README.
- AC: contract test (N+1th request 429s in envelope, key A's burst never throttles
  key B); B2C `/auth/login` limiter behaviour unchanged.

**FT-2 · Co-pay: close the evidence gap, then implement D-9** — *probe + decision-dependent* · **days (0.5 probe + 0.5–1 follow-up)**

- **Step 1 (codebase-answerable, do regardless):** BC-13a-style timeboxed probe of the
  raw `/api/v1/common/getpatient/insurances` response on testeps — dump the full key-set
  (our `PatientInsurancePayload` filters unknown keys, so the schema is not evidence of
  absence). Extend `scripts/pharmapi_live_probe.py`-pattern; output a findings note in
  `docs/b2b-core/` (this file's D-9 gets updated with the verdict).
- **Step 2 (after D-9):** (a) if the probe finds a participation/exemption field → map it
  into the insurances response (small schema + fixture change); (b) if not → docs-only:
  pricing-doc line re-worded to what we deliver (fund identity + drug-level
  `participationPct`), endpoint docstring already states the limitation
  (`routers/v1/patients.py:102-104`).
- Hard rule (per scope owner): **we do not synthesize a patient co-pay** from drug-level
  participation — exemption categories (chronic disease, low income, EKAS) change the
  real rate and we'd be wrong exactly when it matters.

**FT-3 · Formulary coverage: production-sync gate + data-quality check** — *operational, not an import* · **days (1–2; contingency separately priced in D-10)**

- Make "first full masterdata sync completed + coverage populated" an explicit
  **onboarding prerequisite** (lands in FT-11's runbook): run full sync (no `since`),
  then report — % of `active=true` rows with non-NULL `eopyy_coverage`, price coverage,
  `participation_pct` coverage. Expose those counts from the FT-4 sync-status row so the
  check is one query, not a vibe.
- First sync against **production** masterdata (testeps values are placeholders —
  `masterdata-probe.md:43-45`): re-verify value quality (spot-check N known drugs:
  positiveList/price/participation look sane). Needs production-base creds — realistically
  this happens with the first onboarded location's creds unless we obtain our own
  production account first (note in runbook).
- ΕΟΦ positive-list import is the **contingency only** (see D-10 for the scoped
  price tag), triggered by evidence of junk production values — not by default.
- AC: documented gate + a `scripts/` or admin-endpoint coverage report; formulary
  `dataCaveats` already warns on unknown coverage (`formulary.py:182-187`) — unchanged.

**FT-4 · Masterdata sync hardening: status row + schedule + failure surfacing** — *build* · **days (1–2)**

- `catalog_sync_runs` table (started_at, finished_at, mode full/incremental, fetched /
  upserted / skipped, error text, triggered_by). `run_sync` writes it instead of
  swallowing into `print` (`drug_catalog.py:149-159`). Register the model in the three
  places (`alembic/env.py`, `models/__init__.py`, runtime) per BC-1's checklist.
- `GET /admin/sync-drug-catalog/status` returns the last run (the 202 endpoint
  `routers/admin.py:69-84` stops saying "check container logs").
- Nightly incremental sync (`since=<last success>`): host-cron `docker compose exec -T
  backend …` line in the runbook, same pattern as the pilot DB-dump cron
  (`pilot-runbook.md:216-224`). No in-app scheduler — keep the process boring.
- Stale-sync alert hook: FT-8's checks read the status row ("last successful sync > 48h
  ago" = warn).
- AC: failed sync visible via the status endpoint + log line; nightly line documented;
  B2C untouched.

**FT-5 · Collapse the 3 inline `PHARMAPI_MOCK` reads — preserving fail-live defaults** — *refactor* · **days (0.5)**

- Add `is_mock_pharmapi_strict()` (or `is_mock_pharmapi(default_live=True)`) to
  `app/utils/environment.py` — env-var **absent ⇒ LIVE**, mirroring the three sites'
  current semantics. Replace the inline reads at `pharmapi.py:403`, `:669`, `:1071`.
  `environment.py` stays the single read point for the flag (CLAUDE.md convention);
  the safety rationale comments move with it.
- **The trap this ticket exists to avoid:** pointing the three sites at the existing
  `is_mock_pharmapi()` would flip dispense + credential-verify + masterdata to
  mock-by-default when the env var is unset — re-introducing the bug fixed in 3fcf012.
- AC: unit tests pin both helpers' env-unset behaviour; dispense tests green; grep shows
  zero `os.getenv("PHARMAPI_MOCK")` outside `environment.py` and the throwaway probe
  script.

### B — Production-readiness / scale

---

**FT-6 · /v1 structured access log (tenant-attributed) + consent attestation record** — *build* · **days (1)**

- Middleware (or extension of `RequestIdMiddleware`) emitting one JSON log line per /v1
  request: `request_id`, `api_key_id`, `location_id`, `customer_id`, method, path
  template, status, duration_ms — **never** the raw key, never AMKA in the path (log the
  route template, not the rendered URL).
- This line is the substrate for everything in FT-8 (error-rate, per-tenant usage, SLA
  disputes, abuse forensics after a key compromise) — and, with `patientConsent=true`
  query flag included, it **is** the D-5 attestation record (closes A5: who attested,
  for which patient-key request, when, under which key).
- Needs `LOG_FORMAT=json` actually enabled in the deployment (FT-10's compose sets it).
- AC: log line asserted in a contract test (capture handler); PHI review of the emitted
  fields; B2C request logging unchanged.

**FT-7 · Redis-backed session store + limiter backend (the existing seam)** — *refactor behind an interface* · **week (~1); timing is D-8** 

- Implement `PharmapiSessionStore` against Redis: session entries as JSON values keyed
  `pharmapi:session:<session_key>`, TTL = session window; per-key locking via a Redis
  lock (establishment/G14-refresh path) while keeping the in-process `asyncio.Lock` as
  the fast path within one worker. The call-site surface (`get/lock/invalidate`,
  `pharmapi.py:103-134`) does not change — that seam was built for exactly this.
- Same change unlocks: `--workers N` in `Dockerfile.prod:41`, slowapi
  `storage_uri=redis://…` so FT-1's limits hold across workers
  (`observability.py:133-137`), and zero-downtime restarts (sessions survive).
- Watchlist: the legacy B2C path aliases the module-level `pharmapi_session` dict by
  object identity (`pharmapi.py:114-131`) and `routers/pharmapi.py` + `routers/health.py`
  read it by name — the legacy entry likely **stays in-process** (B2C is single-worker
  cookie-auth anyway) while `location:*` entries move to Redis; decide in-ticket.
  While in there: one shared `httpx.AsyncClient` (today every call builds a client —
  `pharmapi.py:290`, `:690`, `:757` — paying TLS handshake per request).
- **When it becomes mandatory** (state for D-8): the in-process store is correct at
  exactly **1 uvicorn worker × 1 instance** — any second worker/instance silently splits
  sessions and rate-limit counters per process (more upstream re-auths; limits become
  N× looser). Hard trigger: an SLA contract requiring zero-downtime deploys or HA; soft
  trigger: sustained traffic that saturates one async worker (rough order: hundreds of
  locations with counter-frequency traffic, given each call is upstream-I/O-bound).
  First-integrator pilot scale does **not** require it.
- AC: full suite green in single-worker mode without Redis (fallback stays in-process);
  two-worker compose smoke with interleaved tenants; G14 double-refresh test passes
  cross-process.

**FT-8 · Observability for a paid API: enable, watch, alert** — *configure + small build* · **days (2–3)**

- Turn on what exists: `LOG_FORMAT=json`, `SENTRY_DSN` (+`SENTRY_ENVIRONMENT=b2b-prod`)
  in the FT-10 compose. Sentry region/PII stance feeds the FT-14 subprocessor list
  (`send_default_pii=False` already set — `observability.py:126`).
- `GET /health/v1` (unauthenticated, cheap): DB reachable, last FT-4 sync age, app
  version. Keep the existing `/health` untouched for the pilot box.
- External uptime monitor (healthchecks.io / UptimeRobot tier) on the public
  `/health/v1` + one authenticated synthetic check (a dedicated monitoring key hitting
  `GET /v1/status`) — measures what the customer experiences, not what the box thinks.
- Error-rate alert: Sentry issue-rate alert + a log-derived 5xx-rate threshold over the
  FT-6 access log. Page → email/phone per D-11's support commitment.
- Write `docs/b2b-core/OPERATIONS.md`: dashboards, alert meanings, first-response steps
  (incl. "ΗΔΥΚΑ is down, we are fine" triage — upstream_error rate vs internal rate are
  distinguishable in the envelope codes).
- AC: kill the DB in staging → alert fires; synthetic check green from outside the VPC.

**FT-9 · API-key rotation / revocation runbook** — *write + tiny CLI polish* · **days (0.5–1)**

- `docs/b2b-core/KEY-MANAGEMENT.md`: standard rotation (mint second key → customer
  deploys → verify `last_used_at` moves → revoke old; zero-downtime because multiple
  active keys per location are supported — `db/models/api_key.py` has no
  one-active-key constraint, evidence in §1/B3); compromised-key procedure (revoke
  immediately → grep FT-6 access log by `api_key_id` for the exposure window → notify
  per DPA); recommended cadence (annual or on staff change).
- CLI polish, optional: `b2b_admin rotate-key --key-id …` = mint sibling + print both
  ids; keep revoke explicit/manual (a one-shot auto-revoke invites lockouts).
- AC: runbook dry-run executed once against the dev stack, transcript pasted into the doc.

**FT-10 · Public TLS-fronted live-mode /v1 deployment target** — *build (deploy)* · **days (2–4) after D-11**

- What exists vs what's needed: `compose.prod.yaml` is mock-mode + SPA-fronting + private
  (`:79` mock pin; Tailscale-only `tls internal` per `user-data.sh`); an integrator needs
  public DNS + real auto-HTTPS + `PHARMAPI_MOCK=false` + the FT-8 env enabled.
- Deliverable: a B2B deployment definition — either `compose.b2b.yaml` (backend + db +
  Caddy `api.<domain>` JSON-API vhost, no SPA) or a parameterised compose.prod — plus a
  `deploy/` bootstrap mirroring `user-data.sh` and a runbook section. Caddy already
  handles ACME when `CADDY_TLS` is empty + a real `PILOT_DOMAIN` (`compose.prod.yaml:44-46`).
- Separate box vs shared with the B2C pilot: recommendation **separate** (pilot box is
  Tailscale-only by design, runs mock mode, and has tester-driven deploy cadence;
  a paying tenant shouldn't share its blast radius) — cost input in D-11. EU region
  (GDPR/data-residency feeds FT-14).
- Single worker stands (FT-7 deferred) — document the restart story: deploys drop
  in-process sessions; B2B sessions self-heal lazily (`pharmapi.py:228-241`) so impact is
  +1 upstream call per location, no manual step.
- AC: full Postman/newman collection green against the public URL in live mode with a
  `pa_live_` key against a real test location; HTTP→HTTPS redirect; key over plain HTTP
  never accepted.

### C — Onboarding (operational)

---

**FT-11 · Per-tenant provisioning runbook** — *write* · **days (1–2)**

- `docs/b2b-core/ONBOARDING.md`, the operator-facing sequence:
  1. **Collect** per location: ΗΔΥΚΑ pharmacy unit id, Basic-Auth username, password
     (secure channel — never email plaintext; password is prompted via getpass and
     AES-GCM-encrypted at rest, `scripts/b2b_admin.py:56`, `:84-85`), ΕΟΠΥΥ category
     yes/no.
  2. **ΕΟΠΥΥ (609) verification**: `--eopyy` mirrors ΗΔΥΚΑ's isIka; if the customer is
     wrong about it, intolerances/history 403 cleanly (`routers/v1/patients.py:77-84`) —
     document that the flag can be corrected later and that PharmAssist **cannot grant**
     the category (customer ↔ Hd@idika.gr, per the pricing doc's 609 note).
  3. **Mint**: `create-customer` → `create-location --verify` (creds validated upstream +
     unit-id cross-checked, `b2b_admin.py:60-73`) → `mint-key` — sandbox key first
     (FT-13), live key after the sandbox run passes.
  4. **Verify**: `GET /v1/status` with the new key (tenant identity + ΕΟΠΥΥ flag echo,
     `routers/v1/__init__.py:23-39`); one patient lookup; FT-3 catalogue-coverage gate
     checked.
  5. **Hand off**: docs link (FT-12), key-management expectations (FT-9), support
     channel + SLA (D-11), signed DPA on file (FT-14/D-13).
- AC: a colleague (not the author) provisions a tenant end-to-end from the doc alone
  against the dev stack.

### D — Integrator-facing

---

**FT-12 · API reference beyond Postman** — *build (docs pipeline)* · **days (2–3)**

- v1-only OpenAPI artifact: script filters `app.openapi()` to `/v1*` paths +
  `b2b-v1`-tagged components (today `/openapi.json` exposes the whole B2C surface
  alongside — `main.py:115-132`) → `docs/b2b-core/openapi-v1.json` + a static Redoc
  HTML. Add `X-API-Key` securityScheme + per-endpoint descriptions where thin.
- `docs/b2b-core/API.md` narrative an integrator actually needs: auth (header, TLS-only),
  the error envelope + the stable code table (`routers/v1/errors.py:32-41` + the
  `consent_required` / `upstream_session_expired` semantics), consent attestation
  (D-5: what you assert when you send `patientConsent=true`), the 609/ΕΟΠΥΥ rule, rate
  limits (FT-1), tri-state coverage + `dataCaveats` philosophy ("absence of an alert ≠
  safe" — `routers/v1/safety.py:42-46`), pagination envelopes, mock/sandbox identifiers
  (reuse `postman/README.md` table).
- Hosting: in-repo static is fine for the first integrator (send the HTML or a
  GitHub-pages-style link from the FT-10 box); a docs site is not Tier-1.
- AC: an external dev makes a first successful call (sandbox key) using only these docs —
  trial-run it on someone internal who hasn't touched /v1.

**FT-13 · Sandbox tier with real semantics** — *build (small deploy + convention)* · **days (1–2) for the mock-mode variant**

- Today's `pa_test_` prefix is decoration (§1/C2). Give it meaning: a **sandbox stack** —
  same image, `PHARMAPI_MOCK=true`, own DB, own (or path/subdomain-separated) endpoint
  on the FT-10 box (`sandbox.api.<domain>`), keys minted there are `pa_test_` and only
  exist there. Deterministic fixtures already exist and are documented
  (`services/v1_mock.py`, identifiers in `postman/README.md`), and mock-parity is pinned
  by the contract suite — the sandbox is therefore credible without ΗΔΥΚΑ.
- Explicitly defer the ΗΔΥΚΑ-testeps-backed sandbox (needs per-location test creds from
  ΗΔΥΚΑ per customer — an external dependency with unknown lead time); revisit if an
  integrator demands end-to-end upstream realism. Note the pricing doc sells "Dedicated
  sandbox environment — €5,000 setup": the mock-mode stack is what that buys at Tier-1.
- AC: newman run green against the sandbox URL with a `pa_test_` key; a `pa_test_` key
  401s on the live endpoint (separate DBs make this structural, assert it anyway).

**FT-14 · API terms + GDPR DPA — engineering inputs (legal text is D-13)** — *write* · **days (1–2 eng); legal external**

- `docs/b2b-core/DATA-PROCESSING.md`, the technical annex a DPA template needs:
  - **Data inventory**: what /v1 receives/returns/stores — AMKA/EKAA + demographics
    (transit only), medicine history + intolerances (transit, consent-gated),
    `b2b_patient_conditions` (stored, soft-delete = indefinite today — set a retention
    stance), access logs incl. consent attestations (FT-6 — define retention),
    encrypted location ΗΔΥΚΑ creds.
  - **Roles**: customer = controller; PharmAssist = processor; ΗΔΥΚΑ = the state system
    we relay to under the IT-supplier agreement (D-12 — resolved).
  - **Subprocessors**: AWS (EU region per D-11), Sentry **if** enabled (EU-hosted org or
    it stays off), uptime monitor. No LLM processors at Tier-1 (Core has no AI features —
    keeps this DPA simple; pricing doc's AI/DPA note bites at Tier-2).
  - **Security measures**: AES-256-GCM creds at rest, SHA-256 keys + show-once mint,
    TLS-only, single-401 no-oracle auth, PHI-free error envelopes + logs.
- ToS skeleton inputs: SLA (D-11), rate limits (FT-1), acceptable use, key custody
  (FT-9), liability stance on clinical decisions ("suggests, never decides" — the
  formulary/safety wording already in code comments is the right register).
- AC: annex reviewed against the actual code paths cited; handed to whoever D-13 selects.

---

## 3. §Decisions — needs Alex / the business

> Numbering continues TICKETS.md. Each entry: the technical context found in this audit,
> a recommendation, and exactly what's needed from you.

### D-8 · Scale target → Redis now or later

**Context:** the swap seam is built and narrow (`PharmapiSessionStore`,
`pharmapi.py:103-134`); the deployment is pinned to one uvicorn worker
(`Dockerfile.prod:41`, `docs/test-env-runbook.md:34-36`). At 1 worker the store is
*correct*; restarts self-heal lazily (one `/user/me` per location, `pharmapi.py:228-241`).
What single-worker actually costs: no HA, deploys briefly drop sessions, FT-1's rate
counters and sessions silently fork per process the moment workers > 1.
**✅ RESOLVED (2026-06-10, per Alex): DEFER.** The single-worker pilot stands; Redis
becomes **required** at >1 worker / HA / any SLA commitment (the trigger above is now the
commitment of record). Sizing basis from Alex: **~5,000-user ceiling** for the product's
horizon → **one shared Redis instance, no sharding** — at that scale session entries and
rate counters are a few MB and a single Redis is over-provisioned, so FT-7's scope is
deliberately the simplest shape (one instance, JSON values, TTL = session window, no
cluster mode). FT-7 stays **scoped, not built**, in this and subsequent batches until a
trigger fires.

### D-9 · Co-pay: source it or re-word it

**Context:** drug-level co-pay is **delivered** (`participationPct` on `/v1/drugs` —
masterdata `participationPercentage`). Patient-level co-pay (what the pricing line
"Patient insurance details (ΕΟΠΥΥ coverage, co-pay %)" most naturally reads as) exists in
**no** integrated ΗΔΥΚΑ surface: not insurances (fund identity + flags only), not search,
not the retrieval CDA (evidence in §1/A2). The real rate also depends on exemption
categories, so synthesizing it from drug-level data would be **wrong for exactly the
patients where it matters** — we won't fake it. One cheap unknown remains: the raw
insurances key-set was never captured (FT-2 step 1, ~0.5 day).
**✅ RESOLVED (2026-06-10, probe + Batch-1 directive "surface the field if present, else
reword; never fake"):** the probe (`docs/b2b-core/insurances-probe.md`) found **no numeric
patient-level co-pay %** anywhere in the read tier — but it found two real fields our
schemas were dropping, and both are now surfaced: **`patientPartExceptions`** (patient
co-pay **exemption** records — reason + validity window) → `participationExceptions` on
`GET /v1/patients/{key}`, and **`socialInsurance.eopyy`** (the fund-is-ΕΟΠΥΥ coverage
flag) → `eopyy` on the insurances response. The pricing line was re-worded to exactly
that (fund identity + ΕΟΠΥΥ flag + exemptions + drug-level `participationPct`). Nothing
synthesized: the effective payable % stays upstream's dispense-time computation.

### D-10 · Formulary: tri-state at launch vs ΕΟΦ-import-first

**Context:** this question has partly answered itself since it was first raised — the
BC-13a probe (`masterdata-probe.md:7-10`) showed `positiveList` ships **in** masterdata,
so coverage filtering needs no external import; the code already filters
(`strict|lenient`) and discloses unknowns via `dataCaveats`. The remaining honest gaps:
coverage is NULL until the first **full** sync on a given environment, and production
value quality is unverified (test rows are placeholders). The ΕΟΦ positive-list
import, if we ever need it: source the ΕΟΦ/ΕΟΠΥΥ θετικός-κατάλογος bulletin (Excel/ΦΕΚ,
revised periodically), parse + reconcile by EOF code/barcode against `drug_catalog`,
maintain per revision — realistically **2–3 weeks** initial + recurring per-bulletin
upkeep, and a second source of truth to keep consistent with masterdata.
**✅ RESOLVED (2026-06-10, per Alex): tri-state at launch.** Confirmed via the Batch-1
build directive ("production full-sync + value-quality check (tri-state launch)"). The
launch gate is FT-3's machinery — full-sync + coverage/quality report — which ships in
Batch 1; the report runs against production masterdata at first onboarding. The ΕΟΦ
positive-list import stays a **priced contingency** (~2–3 weeks + per-bulletin upkeep),
triggered only by evidence of junk production values. The `lenient`-default footnote
rides FT-12.

### D-11 · Hosting + SLA for the paid endpoint

**Context:** there is currently no deployment a paying integrator could call — the only
prod-flavour stack is the Tailscale-only **mock** pilot (`compose.prod.yaml:79`,
`user-data.sh`). FT-10 is scoped and small (2–4 days) but every one of its inputs is a
business choice: public domain (e.g. `api.pharmassist.gr`), AWS account/region (**EU
region** — feeds the D-13 DPA), **separate box vs shared with the pilot**
(recommendation: separate — different blast radius, deploy cadence, and mock-vs-live
posture), and the SLA/support promise (a number like 99.5% + business-hours support
defines FT-8's alerting depth and whether FT-7 moves up — see D-8). The sandbox's
commercial shape (pricing doc: "€5,000 dedicated sandbox setup") rides the same
decision: FT-13's mock-mode stack is the Tier-1 deliverable for that line.
**✅ RESOLVED (2026-06-10, per Alex) — target recorded, go-live deferred.** Target: **AWS
EU region, public domain + TLS, separate box from the B2C pilot**. **SLA: TBD** — to be
set at contract time; the number drives FT-8's alerting depth and is one of D-8's Redis
triggers. FT-10 (live deployment) and the FT-13 sandbox *stack* remain **scoped, not
deployed** — explicitly out of Batch 1; the FT-13 *key-semantics code* (env-prefix
enforcement) ships now so the day-one sandbox deployment is config, not code. Concrete
domain + AWS account details land when go-live is scheduled.

### D-12 · ΗΔΥΚΑ IT-supplier agreement — multi-pharmacy API proxying

**✅ RESOLVED (2026-06-10, per Alex):** multi-pharmacy API proxying is **confirmed
permitted under our IT-supplier agreement**. Recorded here on that basis; this closes the
open question carried in `docs/b2b-core/TICKETS.md` §2 ("needs contractual confirmation
with ΗΔΥΚΑ before production B2B onboarding").
**What this covers, technically:** the shipped model — one vendor `Api-Key` shared across
tenants ("per-app, shared across all pharmacists using your software", `main.py:14-15`)
with each location transacting under its **own** ΗΔΥΚΑ Basic-Auth identity and unit id
(`PharmapiContext`, `pharmapi.py:65-83`; threaded per request in
`routers/v1/deps.py:66-74`). Per-location `api_key` is already a data field, not a
refactor, if ΗΔΥΚΑ ever asks for per-location keys (`pharmapi.py:71-73`).
**No engineering action.** No open flag.

### D-13 · DPA / ToS templates — procurement

**Context:** nothing exists in the repo (§1/D2). Tier-1 keeps the legal surface
comparatively small — no LLM subprocessors (Core has no AI features), processing =
ΗΔΥΚΑ PHI relay + stored patient conditions + access logs. FT-14 produces the technical
annex (data inventory, subprocessors, security measures) so whoever drafts the legal text
starts from facts, not interviews. This is the **longest external lead time** in the whole
plan — lawyer or template-service turnaround is weeks regardless of our velocity.
**⏸ RESOLVED AS DEFERRED (2026-06-10, per Alex):** handed to the team, **owner TBD**.
Explicit framing: legal **gates contract signature, not build** — engineering proceeds at
full speed; FT-14's technical annex stays on the shelf ready for whoever picks up
ownership. Re-flag at the first serious integrator conversation: lawyer/template
turnaround is weeks, so the owner decision becomes urgent the moment a signature date
exists.

---

## 4. Dependency order + sizing

```
Wave 0 (now, parallel, no deps):
  FT-5 mock-flag collapse (0.5d)      FT-2.1 insurances probe (0.5d)
  FT-4 sync hardening (1-2d)          FT-6 access log + consent record (1d)
  FT-9 key runbook (0.5-1d)           FT-14 DPA annex (1-2d)
  FT-12 API reference draft (2-3d)    [D-13 legal procurement starts — external clock]

Wave 1 (after wave-0 pieces):
  FT-1 rate limiting (1-2d)           [after FT-6 ideally — tuning data; not blocked]
  FT-3 coverage gate + report (1-2d)  [after FT-4 — status surface]
  FT-2.2 co-pay follow-up (0.5-1d)    [after D-9]

Wave 2 (after D-11):
  FT-10 public live deployment (2-4d)
    └─→ FT-8 observability on the real target (2-3d)
    └─→ FT-13 sandbox stack (1-2d)
    └─→ FT-12 publish (docs URL) + FT-11 onboarding runbook final (1-2d)

Scheduled by trigger (D-8), not by wave:
  FT-7 Redis store + limiter backend (~1w) — before any SLA contract / 2nd big tenant
```

| Ticket | Size | Blocked by |
|---|---|---|
| FT-1 rate limit | days (1–2) | — (FT-6 helpful) |
| FT-2 co-pay probe → follow-up | days (0.5 + 0.5–1) | step 2: D-9 |
| FT-3 coverage gate | days (1–2) | FT-4; prod creds at first onboarding |
| FT-4 sync hardening | days (1–2) | — |
| FT-5 mock collapse | days (0.5) | — |
| FT-6 access log + consent | days (1) | — |
| FT-7 Redis swap | **week (~1)** | D-8 trigger |
| FT-8 observability | days (2–3) | FT-10 |
| FT-9 key runbook | days (0.5–1) | — |
| FT-10 live deployment | days (2–4) | **D-11** |
| FT-11 onboarding runbook | days (1–2) | FT-10/FT-13 shape (draft earlier) |
| FT-12 API reference | days (2–3) | publish step: FT-10 |
| FT-13 sandbox | days (1–2) | FT-10 |
| FT-14 DPA annex | days (1–2) | — (legal text: D-13, external) |

**Total engineering ≈ 15–24 dev-days (~3–5 weeks single-dev), or ~2.5–4 weeks with FT-7
deferred per D-8.** The likely real-world long pole is not code: it's **D-11 (hosting
decision) gating wave 2, and D-13 (legal) gating contract signature** — both can start
today at zero engineering cost.

**Critical path to a signed, onboarded integrator:**
D-11 → FT-10 → FT-8/FT-13 → FT-11 ‖ FT-12, with FT-1 + FT-6 done before the endpoint is
public, and D-13/FT-14 running in parallel from day one.

---

## 5. Explicitly out of scope (unchanged from TICKETS.md §5)

Dispense/execution, HMVS, and every Tier-2/Tier-3 capability (SPC agents, AI
explanations, ADR, adherence, recalls, pre-auth, pharmacovigilance). Nothing in this plan
adds /v1 surface area — it finishes the operational, data, and commercial shell around
the Tier-1 surface that BC-1…16 built. B2C behaviour and tests stay green throughout;
FT-5 and FT-7 are the only tickets touching shared code paths and both carry explicit
regression guards.

## 6. Phase gate

**Phase 0 (this document) is complete on commit.** No FT ticket starts until this plan is
reviewed — open items for that review: confirm/adjust D-8…D-11 and D-13 (D-12 is
resolved), bless the ticket cut + ordering, and pick what lands in the first wave.
