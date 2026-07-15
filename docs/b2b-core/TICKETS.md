# B2B Core (Tier-1) — Engineering Tickets

**Status:** ✅ Delivered on `feat/b2b-core` (Phases 1–3 complete, BC-1…BC-16).
156 backend tests green; B2C suite unchanged and passing. Approved decisions:
D-3 (separate `b2b_patient_conditions` table), D-6 (expose real
MILD/MODERATE/SEVERE — pricing-doc CRITICAL is a doc fix, not a code level).
**BC-13a outcome:** the live masterdata payload *does* carry `positiveList`
(ΕΟΠΥΥ coverage), `retailPrice`/`referencePrice`, and `participationPercentage`
— **no external ΕΟΦ price-bulletin import was needed** (see
`docs/b2b-core/masterdata-probe.md`).
**Date:** 2026-06-09 (delivered 2026-06-10)
**Source of truth for scope:** `docs/PharmAssist_Pricing.md` → Motion A, Tier 1 "Core"
(€15/location/month) and the B2B Feature Matrix "Core" column only.
**Supersedes:** the old **B1–B6 MVP backlog** (Trello; referenced from
`docs/OPEN-ISSUES.md` § "B2B (post-pilot)"). This file is now the B2B Core plan of record.
**Branch:** `feat/b2b-core`

Out of scope, explicitly: **prescription execution / dispense** (Tier-3 add-on), **HMVS**
(Tier-3), and every Tier-2/Tier-3 capability (SPC agents, AI explanations, ADR, adherence,
recalls, pre-auth). The B2C app keeps all existing behaviour and tests green — this work is
**additive**.

---

## 1. Audit — Core capability vs what exists today

Audited 2026-06-09 against the live codebase (7-agent sweep + adversarial gap check; every
claim verified against file:line).

| # | Core capability (pricing doc) | Status | Where it lives today | /v1 verdict |
|---|---|---|---|---|
| 1 | Patient lookup by AMKA | **EXISTS** | `GET /patients/{id}` → `services/patients.resolve()` → `pharmapi_get_patient` (`services/pharmapi.py:764`) | **Reuse** service, new /v1 router + typed schema |
| 2 | Patient lookup by EKAA | **EXISTS** | Same path; non-11-digit key → `patientekaa` param (`services/patients.py:802-808`) | **Reuse**; add EKAA mock fixture (none exist) |
| 3 | Prescription search (pending + history by AMKA) | **EXISTS** | `pharmapi_search_prescriptions` (`services/pharmapi.py`) — the old `/pharmapi/prescriptions/{queue,history}` routes were removed (caller-less); /v1 calls the service directly | **Reuse**; fix silent history degrade w/o AMKA |
| 4 | Patient insurance details (ΕΟΠΥΥ, co-pay %) | **PARTIAL** | `GET /patients/{id}/insurances` (`routers/patients.py:171`) — payload has fund identity but **no co-pay % field** (`schemas/patient_insurances.py:15-24`) | **Reuse**; co-pay % is a contract decision (see D-7) |
| 5 | Patient intolerances (ΗΔΥΚΑ) | **PARTIAL** | Service exists (`pharmapi.py:851`) but only embedded inside the profile response; pharmacy id read from the **global session** | **Reuse** service + **build** standalone endpoint; needs BC-4 |
| 6 | Patient medicine history (ΗΔΥΚΑ) | **PARTIAL** | `GET /patients/{id}/prescriptions` (`pharmapi.py:866`, 609→`blocked` envelope) — pharmacy id from **global session** | **Reuse**; keep pagination + `blocked` envelope; needs BC-4 |
| 7 | Drug catalog / masterdata | **PARTIAL** | Sync exists (`services/drug_catalog.py`, `pharmapi.py:901`); **no read/search endpoint at all**; `gns_code` column actually stores the EOF **barcode** | **Reuse** sync, **build** the search endpoint + index |
| 8 | Pharmapi error handling G01–G15 + session mgmt + 24h refresh | **PARTIAL** | G01–G07 + G11/G12/G14/G15 only (`pharmapi.py:39-47, 201-218`); **one global session for the whole process** | **Refactor** — this is BC-4 + BC-5 |
| 9 | Boot-time version check | **EXISTS** | `pharmapi_check_version` (`pharmapi.py:424`), called from lifespan | **Reuse** as-is (operator-level, not per-tenant) |
| 10 | Drug-drug interaction checking | **PARTIAL** | Engine + 12 seeded rules work, but history ATCs resolve via `MOCK_PRESCRIPTIONS` only — **dead code in live mode** (`safety_engine.py:156-168`) | **Reuse** rule matching; **build** an explicit-drug-list entrypoint (revives it live — see BC-12) |
| 11 | Duplicate therapy detection | **PARTIAL** | Same code path, 2 seeded rule pairs; same live-mode dead-code problem | Same as #10 |
| 12 | Condition-based contraindication alerts | **EXISTS** | The one check genuinely live end-to-end (`safety_engine.py:203-217` + DB conditions) | **Reuse**; note exact ATC-level-5 matching limits coverage |
| 13 | Severity levels MODERATE/SEVERE/CRITICAL | **PARTIAL** | Code has MILD/MODERATE/SEVERE (`constants.py:18-21`); **CRITICAL doesn't exist**; raw severity is dropped from API payloads (`schemas/safety.py:10-19`) | Contract decision D-6 + expose severity in /v1 payload |
| 14 | Patient conditions CRUD | **EXISTS** | Full CRUD (`routers/patients.py:70-168`), partial unique index, soft delete | **Reuse** with tenancy adjustments — see D-3 (cross-tenant 409 leak + `recorded_by` FK) |
| 15 | Formulary substitution | **MISSING** | Zero code. Catalog lacks price, ΕΟΠΥΥ coverage, form, structured strength (`db/models/drug_catalog.py:10-25`) | **Build** — schema + sync + probe + service + endpoint (BC-13/14) |
| 16 | API-key auth | **MISSING** | Only stored-secret precedent is the **plaintext** invitation token — do not copy | **Build** (BC-3) |
| 17 | Customers / locations tenancy | **MISSING** | No tenant-shaped tables; `pharmacies` is TRUNCATEd by `scripts/seed.py:177-181` — unsafe to reuse | **Build** (BC-1) |
| 18 | Per-location ΗΔΥΚΑ session | **MISSING** | One module-global session dict + import-time env creds; every call authenticates as the single env identity (`pharmapi.py:31-37, 51-57, 172`) | **Refactor** (BC-4) — load-bearing, highest risk |
| 19 | /v1 error envelope + request_id | **MISSING** | FastAPI default `{detail}`; no request-id middleware anywhere | **Build** (BC-5) |

**Audit surprises that shaped the plan** (verified):

- The global session is **already a latent B2C bug**: two pharmacists from different
  pharmacies overwrite `pharmacy_id` (last-login-wins), and intolerances/history URLs then
  embed the wrong ΗΔΥΚΑ unit id (`routers/auth.py:102` → `pharmapi.py:852,880`). BC-4 fixes
  a real defect, not just a B2B prerequisite.
- The conditions unique index `(amka, condition_code) WHERE active` is **global** — tenant A
  recording a condition 409-blocks tenant B *and leaks that the condition exists* (PHI
  inference). See D-3.
- `checks_for_prescription` serves curated `MOCK_SAFETY_CHECKS` for demo rx ids **regardless
  of `PHARMAPI_MOCK`** (`safety_engine.py:109-121`) — /v1 must call `evaluate_safety`
  directly, never that wrapper.
- Mock parity is broken where /v1 will trip: EKAA has no mock fixture, insurances return
  `[]` in mock, masterdata sync is a mock no-op, and `pharmapi.py` has three inline
  `os.getenv("PHARMAPI_MOCK")` reads with **inconsistent defaults** (`:274` live, `:522`
  mock, `:912` live).
- `patientsConsent=true` is asserted unconditionally on intolerances/history calls
  (`pharmapi.py:858-862, :886`) — fine at the counter, not for a relayed B2B call (D-5).
- `scripts/seed_drug_catalog.py:16` imports a function that doesn't exist (ImportError —
  pre-existing breakage, fix rides along with BC-13).
- pytest is **not in CI** (lint-only) — BC-15 adds the enforcement path for /v1 contract
  tests.

---

## 2. Key architecture decisions

### D-1 · Per-location ΗΔΥΚΑ session store — in-process dict keyed by location, Redis seam

**Accepted** (per spec). Replace the module-global `pharmapi_session` dict with a
`PharmapiSessionStore` keyed by a stable context key (`location:<uuid>` for B2B,
`legacy` for B2C), fronted by a narrow interface (`get/set/invalidate`) so a Redis
implementation can drop in later without touching call sites. Per-key `asyncio.Lock`
around session establishment and the G14 refresh (no locking exists today — two concurrent
G14s would double-refresh). Single uvicorn worker remains a deployment constraint until
Redis (already documented in `docs/test-env-runbook.md`).

**Credential threading:** a frozen `PharmapiContext` dataclass
(`username, password, api_key, base_url, pharmacy_unit_id, session_key`) passed explicitly
through `pharmapi_get`, `pharmapi_get_prescription` and everything built on them.
(`pharmapi_dispense` was in the original list; it was deleted with the execution path —
tag `hmvs-certified`.) A module-level `legacy_context()` built from today's env settings is the
default, so **every existing B2C call site keeps working unchanged**. The G14 auto-refresh
re-auths with the *context's* creds (today it would heal one tenant's call with another's
identity). `get_pharmacy_id()` becomes `ctx.pharmacy_unit_id`. The keepalive loop stays
legacy-only; B2B locations re-auth lazily on first use / after expiry (no N background
loops).

*Rejected alternatives:* per-request client objects (heavier diff, same effect);
Redis-now (premature — single-process pilot); contextvars (implicit state is how we got
here).

### D-2 · Separate `customers` / `locations` tables — do not reuse `pharmacies`

**Accepted.** Three code-grounded reasons: (a) `scripts/seed.py:177-181` TRUNCATEs
`pharmacies` CASCADE on every reseed — paying-customer rows must not FK into seeded
tables; (b) B2C resolves pharmacies **by name** with `.one_or_none()`
(`services/pharmacy.py:7-10`) — duplicate names across tenants would crash B2C; (c) ΗΔΥΚΑ
creds live on the pharmacist×pharmacy *link* row today, while B2B needs them on the
location itself. `locations` mirrors the useful pharmacy columns and copies the
`pharmapi_unit_id Integer NOT NULL` convention (the spec's `idika_pharmacy_id` — we keep
the codebase's `pharmapi_unit_id` name for consistency) and adds `is_eopyy` (the isIka
flag; gates intolerances/medicine-history per the 609 rule).

### D-3 · B2B patient conditions: separate table + engine seam (additive), not index surgery

**Proposed — please confirm.** The B2C `patient_conditions` unique index is global on
`(amka, condition_code) WHERE active` (`patient_condition.py:18-24`); `recorded_by` is a
NOT NULL FK to `pharmacists`; and the test suite *emulates this exact index* in fake
sessions (`tests/test_patient_conditions.py:401-441`). Changing the index or columns risks
the "B2C tests stay green, additive not rewrite" constraint.

So: a new `b2b_patient_conditions` table (same shape, `location_id` FK, unique on
`(location_id, amka, condition_code) WHERE active`, `created_via_api_key_id` instead of
`recorded_by`), and `evaluate_safety()` gains an optional `conditions=` parameter —
when provided (the /v1 path), the engine skips its own pharmacy-scoped DB read; when
omitted, B2C behaviour is byte-identical. Conditions are **per-location isolated**
(privacy-safe default; a location never sees or collides with another tenant's records).

*Trade-off accepted:* per-location isolation is clinically incomplete — a contraindication
recorded at location A won't fire at location B for the same patient. Per-customer sharing
is a one-line query change later if a customer asks; patient-global sharing is a GDPR
decision we should not make unilaterally.

*Alternative (rejected for now):* add nullable `location_id` to `patient_conditions` +
rebuild the unique index — touches B2C semantics and its tests directly.

### D-4 · API keys: SHA-256 at rest, show-once mint, prefixed plaintext

**Accepted.** Key = `pa_<env>_<secrets.token_urlsafe(32)>` shown exactly once by the mint
CLI. At rest: `sha256(key)` hex with constant-time comparison (keys are high-entropy, so
fast hashing is safe; bcrypt is for low-entropy passwords and too slow per-request).
Lookup by hash (indexed), then check `active` + location `active`. 401 in the BC-5
envelope for missing/invalid/revoked — same response for all three (no oracle).
Explicitly **not** copying the invitation-token pattern (stored plaintext, printed to
stdout — already flagged `TODO(security)`).

### D-5 · Consent is caller-attested in /v1

Intolerances and medicine history require `patient_consent=true` as an explicit query
parameter; we record the attestation and pass `patientsConsent=true` upstream only then.
Today's unconditional assertion stays B2C-only.

### D-6 · Severity vocabulary — needs your call

Pricing doc says `MODERATE / SEVERE / CRITICAL`; the codebase has
`MILD / MODERATE / SEVERE` and no CRITICAL anywhere. **Recommendation:** /v1 exposes the
real vocabulary (`MILD/MODERATE/SEVERE` + mapped `status: ok|review|block`) and the
pricing doc gets a one-word fix — inventing a CRITICAL level mid-flight changes clinical
semantics. Flag if you want the rename (`SEVERE→CRITICAL`) instead.

### D-7 · Insurance co-pay % — best-effort in v1.0

The upstream insurances payload has no co-pay/participation field
(`schemas/patient_insurances.py:15-24`) — participation normally lives per prescription
line. /v1.0 ships fund identity + flags as-is and documents the limitation; if the live
probe (BC-13a) finds participation data in masterdata or prescription lines, it becomes a
fast-follow. The pricing-doc line stays deliverable as "insurance details".

### Open question (not blocking)

ΗΔΥΚΑ `Api-Key` is documented in-code as "per-app, shared across all pharmacists using
your software" — we assume one vendor key across all tenant locations (per-location
**Basic Auth** carries the identity). Needs contractual confirmation with ΗΔΥΚΑ
(Hd@idika.gr) before production B2B onboarding.

---

## 3. Tickets

Dependency graph: BC-1 → BC-2/BC-3 → BC-4 → BC-5 → surface tickets (BC-6…BC-12) →
formulary (BC-13/14) → tests + Postman (BC-15/16). BC-13a (probe) can run any time.

### Phase 1 — tenancy + auth foundation

---

**BC-1 · Tenancy models: `customers`, `locations`, `api_keys`** — *build* (crypto + model patterns reused)

- `customers`: id UUID, name, contact_email, active, timestamps.
- `locations`: id UUID, customer_id FK, name, address fields, `pharmapi_unit_id`
  (int, the ΗΔΥΚΑ unit id — spec's `idika_pharmacy_id`), `pharmapi_username` /
  `pharmapi_password` (AES-256-GCM ciphertext via existing `app/crypto.py` — same
  pattern as `pharmacist_pharmacy.py:26-27`), `is_eopyy` bool, active, timestamps.
- `api_keys`: id UUID, location_id FK, `key_hash` (sha256 hex, unique indexed), label,
  active, last_used_at, timestamps.
- Register in **three places**: `alembic/env.py:10-22`, `app/db/models/__init__.py`,
  (runtime via `main.py:40`). One migration incl. `updated_at` BEFORE UPDATE triggers
  (per-table, `463cc54e7949` pattern).
- **No FK into any seeded table** (`scripts/seed.py` TRUNCATE hazard) — and add the new
  tables to a "never truncate" comment in `seed.py`.
- AC: `alembic upgrade head` clean on fresh + existing DB; autogenerate diff is empty
  after; B2C suite green.

**BC-2 · `scripts/b2b_admin.py` — mint / revoke CLI** — *build* (CLI pattern from `scripts/seed.py`)

- `python -m scripts.b2b_admin create-customer / create-location / mint-key / revoke-key /
  list`. Mint prints the plaintext key **once**; never logged or persisted plaintext.
  Encrypts location ΗΔΥΚΑ creds with `encrypt_credential`. Optional `--verify` flag calls
  `verify_pharmapi_credentials` against ΗΔΥΚΑ before saving.
- AC: full mint→use→revoke→401 loop demonstrable in compose; creds round-trip through
  AES-GCM; no plaintext secret in DB or logs.

**BC-3 · `X-API-Key` dependency → `ApiContext`** — *build* (parallels `deps.get_current_user`)

- `app/v1/deps.py`: `get_api_context(x_api_key: Header) → ApiContext{customer, location,
  decrypted creds, pharmapi_context}`. Hash → lookup → active checks → decrypt creds
  in-memory (never logged). Stamps `last_used_at` (fire-and-forget).
- 401 in the BC-5 envelope for missing/invalid/revoked — identical body for all three.
- Cookie auth (`deps.get_current_user`) untouched; the two dependencies never mix.
- AC: unit tests for valid/invalid/revoked/inactive-location; dependency override works
  with the existing `dependency_overrides` test pattern.

**BC-4 · ⚠️ Per-location ΗΔΥΚΑ session + credential threading (THE CRUX)** — *refactor* of `services/pharmapi.py`

> **Load-bearing, highest-risk ticket.** Everything in Phase 2 sits on it, it touches the
> regulator-facing upstream identity, and it rewires a 946-line module with ~14 caller
> files. It also fixes the existing last-login-wins B2C defect. Land it alone, smallest
> possible diff, pair-review level scrutiny, full B2C regression before anything stacks
> on top.

- Implement D-1: `PharmapiContext` (frozen dataclass) + `PharmapiSessionStore` (in-process
  dict keyed by `session_key`, per-key `asyncio.Lock`, clean seam for Redis).
- Thread `ctx` through `pharmapi_get` (fixes ~9 capabilities at once — search, patient,
  insurances, intolerances, history, masterdata, version, errorslist) and
  `pharmapi_get_prescription`. Default `ctx=legacy_context()` preserves every existing
  call site.
- G14 auto-refresh re-auths with `ctx` creds and updates only `ctx.session_key`'s entry;
  `get_pharmacy_id()` → `ctx.pharmacy_unit_id` (B2C legacy context keeps the
  session-derived value); keepalive stays legacy-only; B2B re-auths lazily.
- Breakage watchlist (from audit): `routers/pharmapi.py:42` reads the session dict
  directly; `routers/health.py:7` imports `PHARMAPI_API_KEY` by name;
  `scripts/pharmapi_live_probe.py`; import-time settings snapshot (`pharmapi.py:29-37`)
  means tests keep the env-before-import discipline.
- AC: full existing pytest suite green; new unit tests — two contexts interleaved never
  leak creds/unit-id across keys; concurrent G14 refreshes on one key serialize via lock;
  B2C login→queue→history flow identical in mock mode.

**BC-5 · /v1 error envelope + request-id middleware** — *build*

- Envelope: `{"error": {"code", "message", "request_id"}}` — distinct from B2C `{detail}`.
  Stable code strings: `unauthorized`, `not_found`, `conflict`, `gone`,
  `validation_failed`, `upstream_error`, `upstream_session_expired`, `consent_required`,
  `rate_limited`, `internal`.
- Request-id middleware (UUID per request, echoed as `X-Request-Id` header + envelope
  field + JSON log field). App-wide middleware, envelope shaping scoped to `/v1/*` paths
  so B2C responses don't change.
- Map upstream G-codes into envelope codes (G01–G07 → `not_found`/`conflict`/`gone`/
  `validation_failed` with the upstream code preserved in a `upstream_code` detail;
  G14 → `upstream_session_expired` after the one retry; G11/G15 → `upstream_error`).
  Translation layer catches the service-layer `HTTPException`s so B2C-shaped hints
  ("call POST /pharmapi/connect first") never reach API customers.
- PHI rule: envelope messages never contain AMKA/names; keep the existing 200-char
  upstream-body truncation.
- AC: contract tests assert the envelope on 401/404/409/422/502 across /v1; B2C error
  bodies unchanged.

### Phase 2 — the /v1 surface

Every endpoint: `APIRouter(prefix="/v1")` package (`app/routers/v1/`), behind BC-3,
scoped to the `ApiContext` location, mock-parity maintained, camelCase via the existing
`AppSchema` base (`schemas/base.py`).

---

**BC-6 · `GET /v1/patients/{amka_or_ekaa}`** — *reuse* `pharmapi_get_patient` + `clean_pharmapi_patient_data`
- Typed response model (today's B2C response is an untyped dict). Explicit AMKA/EKAA
  routing (validate 11-digit-numeric = AMKA, else EKAA format check — today any garbage
  goes upstream as EKAA). **Add EKAA mock fixture** (mock parity gap).
- AC: contract test mock+shape; tenant test: ctx creds used (assert via fake transport).

**BC-7 · `GET /v1/patients/{amka_or_ekaa}/insurances`** — *reuse* `pharmapi_get_patient_insurances`
- Reuse `PatientInsurancePayload`. Fix the mock-returns-`[]` parity gap with a fixture.
  Replace the `print()` at `pharmapi.py:805` with logger while there. Document the
  no-co-pay-% limitation (D-7).

**BC-8 · `GET /v1/patients/{amka_or_ekaa}/intolerances`** — *reuse* service, *build* standalone endpoint
- Today intolerances are only embedded in the profile. Requires
  `patient_consent=true` (D-5) else 422 `consent_required`. Unit id from
  `ctx.pharmacy_unit_id` (BC-4). 403-equivalent envelope when location `is_eopyy=false`
  (the 609 rule) rather than an opaque upstream error.

**BC-9 · `GET /v1/patients/{amka_or_ekaa}/medicine-history`** — *reuse* `pharmapi_get_patient_medicine_history`
- Keep the pagination envelope `{items, page, totalPages, lastPage, totalEntries,
  blocked}` — it's a good convention. `patient_consent=true` required. 609 → `blocked:
  true` stays. Same `is_eopyy` gating as BC-8.

**BC-10 · `GET /v1/prescriptions` + `GET /v1/prescriptions/{barcode}`** — *reuse* `pharmapi_search_prescriptions`
- Query: `amka`, `status=pending|dispensed`, `from`, `to`, `page`, `size`, `barcode`.
  **`status=dispensed` requires `amka`** (hard 422 — do not inherit B2C's silent
  degrade to mixed results, `routers/pharmapi.py:114-117`). Detail = search filtered by
  barcode, 404 envelope if absent (the rich CDA detail path stays out — it drifts toward
  dispense scope).

**BC-11 · `GET /v1/drugs` (catalog search)** — *build* endpoint over *reused* sync
- No read endpoint exists today. Query by `q` (name_gr/name_en ILIKE), `atc` (prefix),
  `barcode` (exact); paginated. Migration: **index on `atc_code`** (formulary needs it
  too). Contract field names honest: expose `barcode` (what `gns_code` actually stores)
  and `activeSubstance` (what `name_en` actually stores). Add mock masterdata fixtures
  (sync is a mock no-op today — formulary and this endpoint are otherwise untestable in
  mock). Fix `scripts/seed_drug_catalog.py` ImportError while there.

**BC-12 · `POST /v1/safety/check` + severity exposure** — *build* endpoint, *reuse* engine
- Body: `{patient: {amka?}, medications: [{barcode}|{atc}], comedications?:
  [{barcode}|{atc}]}` → per-medication findings `{checkType, severity, status, ruleCode,
  message, recommendedAction}` + overall status.
- Call `evaluate_safety` **directly** (never `checks_for_prescription` — its demo-rx-id
  short-circuit ignores `PHARMAPI_MOCK`). New thin engine entrypoint that takes the
  caller's explicit drug list as the co-medication set — **this revives drug-drug
  interaction + duplicate-therapy checks in live mode** (they're dead today because
  history→ATC resolution is mock-only). Conditions via D-3 seam
  (`evaluate_safety(..., conditions=)` loaded from `b2b_patient_conditions`).
- Expose raw `severity` (D-6) alongside mapped `status`. Unknown barcode → explicit
  `"unknownDrug": true` finding, **not** silent skip (today's silent-skip is a paid-API
  hazard).
- AC: contract tests for interaction pair, duplicate pair, condition contraindication
  (seeded rules), unknown drug, empty result.

**BC-12b · `/v1` conditions CRUD: `GET/POST/PATCH/DELETE /v1/patients/{amka}/conditions[/{id}]`** — *build* table (D-3), *reuse* CRUD shape
- `b2b_patient_conditions` + migration (unique `(location_id, amka, condition_code) WHERE
  active`, partial-index style from `4a91c2b5e3df`). Location-scoped queries from
  `ApiContext` (never by name). 409 within a location only. Soft delete. Feeds BC-12 via
  the engine seam. B2C `patient_conditions` untouched.

### Phase 2 — formulary (the capability gap)

---

**BC-13a · Live masterdata probe (prerequisite, timeboxed)** — *build* (throwaway, `scripts/pharmapi_live_probe.py` precedent)
- Dump the full key-set of real `/api/v1/masterdata/medicines` items (the repo has no
  fixture/doc of the complete payload). Decides whether price / ΕΟΠΥΥ coverage /
  pharmaceutical form / structured strength come from Pharmapi or need an external
  ΕΟΦ/ΕΟΠΥΥ price-bulletin import. **Output: a short findings note in `docs/b2b-core/`**
  + the field mapping for BC-13.

**BC-13 · Catalog schema + sync extension for formulary** — *build*
- Migration: add `form`, `strength_raw` (the upstream `content` string), `strength_value`
  / `strength_unit` (parsed, nullable), `price`, `reference_price`, `eopyy_coverage`
  (nullable bool — tri-state until data confirmed), `substance_code`, `package_size` —
  trimmed to what BC-13a confirms upstream actually supplies. Extend `_to_row` + the
  upsert update-set (`services/drug_catalog.py:21-38, 100-106`). Surface sync failures
  (today `run_sync` swallows everything and the admin endpoint 202s regardless — store
  last-sync status row).
- If coverage/price are NOT in masterdata: ship `eopyy_coverage` as nullable, rank
  without price, and open a follow-up data ticket for the ΕΟΦ positive-list import —
  **do not block Tier-1 on external data engineering**.

**BC-14 · Formulary substitution service + `GET /v1/drugs/{barcode}/alternatives`** — *build*
- Given a barcode (or `?atc=`): rank alternatives by (1) same ATC level-5 + same form ≈
  generic equivalence, (2) same ATC level-4 class, filtered by `active=true` and
  `eopyy_coverage` when known (`coverageFilter=strict|lenient` while data is tri-state).
  Dose notes: compare `strength_value/unit`; emit "same strength" / "X→Y conversion —
  verify dose" / "strength unparseable — manual check". Every response carries
  `dataCaveats` (e.g. "coverage unknown for N candidates").
- AC: unit tests on seeded catalog (the 20 seed rows have full ATC data); contract test;
  same-form constraint enforced; never recommends an inactive pack.

### Phase 3 — tests + Postman

---

**BC-15 · Test suite for /v1** — *build* on existing patterns
- Per-endpoint **contract tests** (request/response shape + error envelope), **auth tests**
  (valid/invalid/revoked/missing key — identical 401 body), **tenant isolation** (location
  A's key cannot read location B's conditions; A's calls carry A's creds/unit-id — fake
  transport assertion), **mock parity** (every /v1 endpoint returns shaped data with
  `PHARMAPI_MOCK=true`), unit tests (session store, context threading, key hashing,
  formulary ranking).
- Patterns honored: env-before-import preamble (`test_auth_db.py:17-29`), `create_app()`
  isolation (the `main.app` singleton carries a permanent fake-session override from
  `test_auth_db.py:150`), module-scoped TestClient for live-DB tests, fake sessions for
  pure-contract tests.
- **Add a pytest CI job** (lint-only today): fake-session contract tests run DB-less in
  CI; live-DB integration stays manual. Without this, /v1 contracts have no enforcement.

**BC-16 · Postman collection + environment** — *build* (net-new; no collections exist in-repo)
- `postman/PharmAssist-B2B-Core.postman_collection.json` +
  `postman/PharmAssist-B2B-Core.postman_environment.json` (`base_url`, `api_key` vars).
  Every Core endpoint with example requests + tests asserting status and envelope shape
  (success + one error case each: 401 bad key, 422 missing consent, 404 unknown patient).
  Import-and-run against the compose stack in mock mode. README in `postman/` with the
  3-step run instruction. This establishes `postman/` as the home the ΗΔΥΚΑ/HMVS
  collections can migrate into later.

---

## 4. Risk register

| Risk | Severity | Mitigation |
|---|---|---|
| **BC-4 regresses B2C upstream calls** (946-line module, ~14 caller files, regulator-facing identity) | High | Default `legacy_context()` keeps every call site source-compatible; land BC-4 alone; full suite + mock-mode manual flow before stacking; breakage watchlist in ticket |
| Pharmapi masterdata lacks coverage/price → formulary under-delivers vs pricing doc | High | BC-13a probe **before** BC-13 schema; tri-state coverage + `dataCaveats` in responses; external ΕΟΦ import as fast-follow, not a Tier-1 blocker |
| Two tenants interleaving on one process leak session/unit-id (concurrency) | High | Keyed store + per-key lock; explicit interleaving tests in BC-15; single-worker constraint documented until Redis |
| `scripts/seed.py` TRUNCATE wipes tenant data | Medium | B2B tables FK-isolated from seeded set (BC-1); guard comment in seed.py |
| Mock-parity gaps make /v1 untestable in mock (EKAA, insurances, masterdata) | Medium | Fixtures added in BC-6/7/11; consolidate the three inconsistent inline `PHARMAPI_MOCK` reads onto `is_mock_pharmapi()` while touching them |
| No pytest in CI → contracts unenforced | Medium | BC-15 adds the CI job (DB-less contract tier) |
| Single shared upstream `Api-Key` across tenants may be contractually wrong | Low (now) | Open question to ΗΔΥΚΑ; per-location Basic Auth carries identity meanwhile; `api_key` already lives in `PharmapiContext` so a per-location key is a data change |
| `X-API-Key` in logs/proxies | Low | Key never logged; hash-only at rest; document TLS-only in Postman README |

## 5. Explicitly out of scope (do not pull in)

Dispense/execution and HMVS were **deleted from the codebase entirely** (retrieval-only
pivot — tag `hmvs-certified`), so they are out of scope by construction. Also out: SPC
agents, AI explanations, ADR endpoints, adherence, recalls, pre-auth, pharmacovigilance.

## 6. Questions for review (blocking items marked ●)

1. ● **D-3** — separate `b2b_patient_conditions` table + engine seam (recommended) vs
   extending the B2C table?
2. ● **D-6** — severity vocabulary: expose code's `MILD/MODERATE/SEVERE` and fix the
   pricing doc (recommended), or rename `SEVERE→CRITICAL` in the /v1 contract?
3. D-7 — OK to ship insurances without co-pay % in v1.0 (documented limitation)?
4. Endpoint naming above (`/v1/patients/{amka_or_ekaa}/…`, `/v1/drugs/…`,
   `/v1/safety/check`) — any contract preferences before they're frozen in tests +
   Postman?
5. BC-13a needs ~30 min against live testeps with the rotated creds — fine to run during
   Phase 2?
