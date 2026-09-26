# PharmAssist B2B Core API (/v1) — Integrator Reference

The narrative companion to the machine-readable spec. Open
[`api-reference.html`](api-reference.html) (standalone Redoc, generated from
[`openapi-v1.json`](openapi-v1.json) by `backend/scripts/export_openapi_v1.py`)
for the per-endpoint request/response schemas; this document explains the
cross-cutting rules a first integration needs: auth, the error envelope, consent
attestation, the 609/ΕΟΠΥΥ rule, rate limits, coverage semantics, pagination,
and the sandbox identifiers.

> **Scope.** Tier-1 "Core": patient lookup + insurances + intolerances +
> medicine history, national drug catalogue + formulary alternatives, an
> explicit-list safety check, and per-location patient conditions — plus the
> `clinical_only` base tier below it and locations provisioned without ΗΔΥΚΑ
> credentials (§2.1–2.2). Dispense and HMVS are **not** in this surface; the
> Tier-2 AI + ADR routes are gated at `clinical` (see the spec).

---

## 1. Base URL & transport

- **Live:** `https://api.<your-domain>` — assigned at go-live (FT-10, target
  AWS EU + public TLS; not yet deployed).
- **Sandbox:** the mock-mode stack (see §9). Same image, deterministic fixtures.

**TLS only.** API keys are bearer credentials. Never send a key over plain HTTP
outside local development; the production front end redirects HTTP→HTTPS and a
key sent in cleartext should be considered compromised and rotated
([KEY-MANAGEMENT.md](KEY-MANAGEMENT.md)).

## 2. Authentication — `X-API-Key`

Every endpoint except the liveness probe (`GET /health/v1`) requires a
per-location key in the `X-API-Key` header
(`backend/app/routers/v1/deps.py:52-58`):

```http
GET /v1/status HTTP/1.1
Host: api.<your-domain>
X-API-Key: pa_live_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

- Keys are `pa_<env>_<token>` (~256 bits), shown **once** at mint, stored only
  as a SHA-256 hash — there is no recovery, only re-mint
  (`backend/app/services/api_keys.py:31-37`).
- **One indistinguishable 401** for every auth failure — missing key, unknown
  key, revoked key, inactive location/customer, or an env-prefix mismatch
  (`deps.py:32-36`, `services/api_keys.py:58-81`). The API never reveals which.
- The key identifies a single **location** (pharmacy unit). One customer can
  hold many locations and many keys; keys do not carry a user identity.
- A location transacts under its **own** ΗΔΥΚΑ Basic-Auth identity, resolved
  server-side from the key — you never send ΗΔΥΚΑ credentials. A location can
  also be provisioned with **no** ΗΔΥΚΑ identity at all (§2.2).

`GET /v1/status` is the auth smoke test: it echoes your customer identity and
entitlement `tier` (`clinical_only` | `core` | `clinical` | `platform`), your
location identity, the ΕΟΠΥΥ flag, whether the location can reach ΗΔΥΚΑ
(`location.retrievalAvailable`), and whether the upstream session is warm
(`backend/app/routers/v1/__init__.py`). `pharmapiConnected: false` before your
first patient call is normal — ΗΔΥΚΑ sessions are established lazily — and it is
always `false` when `retrievalAvailable` is `false`.

### 2.1 Tiers

Routes above your tier return `tier_required` (403, §3). The tier is ordinal
(`platform ≥ clinical ≥ core ≥ clinical_only`), so a higher tier reaches every
lower tier's routes.

| Tier | Adds |
|---|---|
| `clinical_only` | Explicit-list safety check (`POST /v1/safety/check`), drug catalogue search (`GET /v1/drugs`), per-location patient conditions |
| `core` | Formulary alternatives (`GET /v1/drugs/{barcode}/alternatives`) and ΗΔΥΚΑ retrieval (patients, prescriptions) |
| `clinical` | Tier-2: AI safety explanations (`POST /v1/safety/explain`), ADR reports |
| `platform` | Everything above |

### 2.2 Locations without ΗΔΥΚΑ credentials

Retrieval is **independent of tier**: any tier can be bought for a location that
has no ΗΔΥΚΑ credentials (e.g. an integrator that has no ΗΔΥΚΑ account).
Such a location reports `location.retrievalAvailable: false` on `/v1/status`,
and:

- **Works as normal** (subject to tier): `GET /v1/drugs`,
  `GET /v1/drugs/{barcode}/alternatives`, `POST /v1/safety/check`, the
  `/v1/patients/{amka}/conditions` CRUD (conditions are stored by PharmAssist,
  not ΗΔΥΚΑ, and feed the safety check), and the Tier-2 routes.
- **Answers `retrieval_unavailable` (409)**: the six routes that read ΗΔΥΚΑ —
  `GET /v1/patients/{key}`, `…/insurances`, `…/intolerances`,
  `…/medicine-history`, `GET /v1/prescriptions`, `GET /v1/prescriptions/{barcode}`.
  The sandbox enforces this too, so a sandbox run shows exactly what live will
  answer.

For a location without ΗΔΥΚΑ access, supply the patient's medications (and
co-medications) explicitly in the safety-check body, and record conditions
through the conditions endpoints.

## 3. Error envelope

Every `/v1` error renders in one stable shape (`backend/app/routers/v1/errors.py`):

```json
{ "error": { "code": "not_found", "message": "Patient not found", "request_id": "..." } }
```

- `code` is the **stable, partner-facing contract** — branch on it, not on the
  prose `message` (which may be reworded) and not on bare HTTP status.
- `request_id` echoes the `X-Request-Id` response header — quote it in support
  tickets; it ties to the access-log line for your request.
- `upstream_code` appears only when a ΗΔΥΚΑ G-code was identified (e.g. `G14`).

### Stable code table

| `code` | HTTP | Meaning | Your move |
|---|---|---|---|
| `validation_failed` | 400/422 | Malformed input (bad AMKA/EKAA, bad query param) | Fix the request. |
| `consent_required` | 422 | A consent-gated read was called without `patientConsent=true` | Attest consent (§4), resend. |
| `unauthorized` | 401 | Bad/missing/revoked key, or env mismatch | Check the key; one 401 covers all causes. |
| `forbidden` | 403 | Location not in the ΕΟΠΥΥ category for a 609-gated read (§5) | Establish the category (operator), or stop calling intolerances/history. |
| `tier_required` | 403 | The route needs a higher entitlement tier than this customer holds (T2-1) | Upgrade the customer's tier (contact sales); ordinal `platform ≥ clinical ≥ core ≥ clinical_only` (§2.1). |
| `not_found` | 404 | No such patient / drug / prescription / condition | — |
| `conflict` | 409 | Duplicate (e.g. same condition already recorded at this location) | Treat as already-exists. |
| `retrieval_unavailable` | 409 | This location has no ΗΔΥΚΑ credentials, so a patient/prescription retrieval route can't run (§2.2) — a provisioning state, not an entitlement denial | Don't retry. Use the retrieval-free routes, or have the location's ΗΔΥΚΑ credentials added through onboarding. |
| `gone` | 410 | Resource withdrawn upstream | — |
| `rate_limited` | 429 | Per-key limit exceeded (§6) | Back off; honour `Retry-After`. |
| `upstream_session_expired` | 401/409 | ΗΔΥΚΑ session lapsed (G12/G14) — transient | **Retry**; a fresh session is established automatically. |
| `upstream_error` | 5xx (usu. 502) | ΗΔΥΚΑ itself errored or is down | Retry with backoff; not your bug, not ours. |
| `ai_unavailable` | 503 | An AI (Tier-2) feature's LLM call timed out or failed (T2-2) — AI endpoints only; deterministic endpoints never emit it | Retry shortly; the deterministic surfaces (safety check, formulary, ADR CRUD) are unaffected. |
| `internal` | 500 | A bug on our side | Retry once; if it persists, send us the `request_id`. |

`upstream_session_expired` and `upstream_error` are deliberately distinct from
`internal` so you (and our operators) can tell "ΗΔΥΚΑ is down" from "PharmAssist
is down" — `errors.py:84-106`.

## 4. Consent attestation (D-5)

Two reads relay sensitive ΗΔΥΚΑ PHI and are **consent-gated**: patient
intolerances and medicine history. They require `?patientConsent=true`
(`backend/app/routers/v1/patients.py:68-74`, `:118`, `:134`); omitting it
returns `consent_required` (422).

Sending `patientConsent=true` is a **legal attestation**: you assert that the
patient has consented to their PharmAssist-mediated record being retrieved at
this location, now. We **record** that attestation — the access log captures
which location attested, for which patient (as a keyed HMAC pseudonym, never the
raw AMKA), under which API key, and when
(`backend/app/observability.py:109-116`). That record is the GDPR lawful-basis
evidence for the relayed read; do not assert consent you do not hold.

## 5. The 609 / ΕΟΠΥΥ rule

Intolerances and medicine history are only available to locations whose ΗΔΥΚΑ
account is in the **ΕΟΠΥΥ category** (ΗΔΥΚΑ `isIka`). A non-ΕΟΠΥΥ location gets a
clean `forbidden` (403) with upstream code 609
(`backend/app/routers/v1/patients.py:77-84`). The category is a property of the
ΗΔΥΚΑ account — PharmAssist cannot grant it (the customer arranges it with ΗΔΥΚΑ;
see [ONBOARDING.md](ONBOARDING.md)). Demographics, insurances, drugs, safety,
and conditions do **not** require it.

## 6. Rate limits (FT-1)

Every `/v1` endpoint is limited **per API key** — default `120/minute`,
deploy-configurable via `V1_RATE_LIMIT`
(`backend/app/routers/v1/deps.py:74-82`). One key's burst never throttles
another's. Over the limit you get the standard envelope with `code:
"rate_limited"` (429) and a `Retry-After` header in seconds. Integrators call
from NAT'd server farms, so the limit is keyed on the **key**, never the client
IP. Back off and retry; do not hammer.

## 7. Drug coverage — tri-state + `dataCaveats`

`eopyyCoverage` on a drug is **tri-state** (`backend/app/db/models/drug_catalog.py:34-42`,
`schemas/v1.py:80`):

- `true` — on the ΕΟΠΥΥ positive list,
- `false` — not covered,
- `null` — **unknown** (not yet populated for that row; e.g. before the first
  full masterdata sync on an environment).

`GET /v1/drugs/{barcode}/alternatives` ranks therapeutic substitutes and takes
`coverageFilter=strict|lenient` (default `lenient`,
`backend/app/routers/v1/drugs.py:64-94`):

- `strict` — only drugs known to be covered (`null` excluded),
- `lenient` — includes unknowns, and every response lists where catalogue data
  was too thin to enforce a constraint in **`dataCaveats`**.

**`null` ≠ "not covered"** and **absence of an alert ≠ "safe"**: the safety
check evaluates interactions/duplication/contraindications but does **not**
screen ΗΔΥΚΑ intolerances/allergies — that caveat is returned in the response
and you must screen `GET /v1/patients/{amka}/intolerances` separately
(`backend/app/routers/v1/safety.py:36-46`). Treat these reads as decision
support: PharmAssist suggests, it never decides.

## 8. Pagination

List endpoints return an envelope, not a bare array. Two shapes:

- **Catalogue search** (`GET /v1/drugs`): `items`, `total`, `page`, `size`,
  `lastPage` (`backend/app/routers/v1/drugs.py:54-61`).
- **Medicine history** (`GET /v1/patients/{amka}/medicine-history`): `items`,
  `page`, `totalPages`, `lastPage`, `totalEntries`, and `blocked` — `blocked:
  true` signals an upstream 609 block rather than an empty history
  (`backend/app/routers/v1/patients.py:144-164`).

`page` is 0-based; `size` defaults to 50 (max 200). Loop until `lastPage: true`.

## 9. Sandbox & mock identifiers

The sandbox is the mock-mode stack (`PHARMAPI_MOCK=true`): same image, same
shapes and envelopes (pinned by the contract suite), backed by deterministic
fixtures (`backend/app/services/v1_mock.py`). Sandbox keys are `pa_test_…` and
authenticate **only** on a sandbox stack; `pa_live_…` keys authenticate **only**
on a live stack — a mismatch 401s like any bad key (FT-13,
`backend/app/services/api_keys.py:58-65`). Reuse these identifiers from
[`postman/README.md`](../../postman/README.md):

| Fixture | Value |
|---|---|
| Patient AMKA | `15031962456` |
| Prescription barcode | `1262602210000100` |
| Drug barcodes | `3661001`, `3661002` |

Against a live backend, replace these with real test-environment values — the
shapes are identical by design.

## 10. First call (sandbox)

```bash
# 1. Auth smoke
curl -s https://sandbox.api.<domain>/v1/status \
  -H "X-API-Key: pa_test_..."          # → customer/location identity + isEopyy

# 2. Patient demographics
curl -s https://sandbox.api.<domain>/v1/patients/15031962456 \
  -H "X-API-Key: pa_test_..."

# 3. Consent-gated read (note patientConsent)
curl -s "https://sandbox.api.<domain>/v1/patients/15031962456/intolerances?patientConsent=true" \
  -H "X-API-Key: pa_test_..."
```

A complete runnable contract suite (success **and** error cases) lives in
[`postman/`](../../postman/README.md).
