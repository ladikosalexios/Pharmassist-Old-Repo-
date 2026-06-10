# Data Processing — technical annex (FT-14)

**Status: engineering annex, ready for legal author.** This document is the
*factual* substrate a GDPR Data Processing Agreement (DPA) and API Terms of
Service need — data inventory, roles, subprocessors, security measures. The
**legal text itself is D-13** (owner TBD); nothing here is the contract. Every
code path cited was re-checked to exist as described (FT-14 AC).

Scope: the Tier-1 B2B `/v1` surface. Tier-1 "Core" has **no LLM/AI features**, so
there are no AI subprocessors and the pricing doc's AI/DPA note does not bite
here (it applies at Tier-2).

---

## 1. Data inventory

### 1a. In transit only (relayed from ΗΔΥΚΑ, not persisted by PharmAssist)

| Data | Endpoint | Notes |
|---|---|---|
| AMKA / EKAA + demographics (name, DOB, sex, contact, address) | `GET /v1/patients/{key}` | Relayed from ΗΔΥΚΑ; not stored. |
| Insurance / fund coverage (fund identity, `eopyy` flag, co-pay **exemptions**) | `GET /v1/patients/{key}/insurances` | No numeric patient co-pay upstream (D-9). |
| Recorded intolerances/allergies | `GET /v1/patients/{key}/intolerances` | **Consent-gated + ΕΟΠΥΥ-gated** (§4 of API.md). |
| Executed-prescription (medicine) history | `GET /v1/patients/{key}/medicine-history` | **Consent-gated + ΕΟΠΥΥ-gated.** Cross-pharmacy. |
| Prescriptions, national drug catalogue | `GET /v1/prescriptions*`, `GET /v1/drugs*` | Catalogue is non-personal reference data. |

These pass through the request and are returned to the caller; PharmAssist keeps
no copy. The safety check (`POST /v1/safety/check`) evaluates a caller-supplied
drug list in memory and persists nothing patient-identifying.

### 1b. Stored at rest (PharmAssist database)

| Data | Where | Retention stance (TODO — legal to confirm) |
|---|---|---|
| **Patient conditions**, keyed by **stored AMKA** + `location_id`, with `condition_code`, `name`, `severity`, `notes`, `created_via_api_key_id` | `b2b_patient_conditions` (`backend/app/db/models/b2b_patient_condition.py`) | **Soft-delete** (`active=false`) — rows are retained indefinitely today (kept for audit). A retention period must be set. |
| **Access logs incl. consent attestations** — `api_key_id`, `location_id`, `customer_id`, method, route **template**, status, duration, and on consent-gated reads a patient **HMAC pseudonym** + the `patientConsent` flag | structured log stream (FT-6, `backend/app/observability.py:99-124`) | Retention to be defined (these are the GDPR lawful-basis + SLA/forensics record). |
| **Encrypted ΗΔΥΚΑ credentials** per location (username + password) | `locations.pharmapi_username/password`, AES-256-GCM (`app/crypto.py`) | Lifecycle = the customer relationship. |
| **API key hashes** (SHA-256, never the raw key) + key metadata | `api_keys` (`app/db/models/api_key.py`) | Lifecycle = the key (see KEY-MANAGEMENT.md). |
| Customer / location identity (names, contact email, ΗΔΥΚΑ unit id, ΕΟΠΥΥ flag) | `customers`, `locations` | Lifecycle = the customer relationship. |

**The one stored patient identifier is the AMKA inside `b2b_patient_conditions`**
— conditions are inherently keyed by patient, so that table holds AMKA at rest
(per-location isolated by a uniqueness constraint on `location_id, amka,
condition_code`). Everywhere else AMKA is transit-only or appears as an HMAC
pseudonym.

## 2. Roles

- **Customer (pharmacy / chain) = data controller.** They determine the purpose
  of each patient lookup and hold the patient relationship + consent.
- **PharmAssist = data processor.** We relay and provide the safety/formulary
  tooling on the controller's instructions; we do not decide treatment
  ("suggests, never decides").
- **ΗΔΥΚΑ (ΙΔΙΚΑ) = the state e-prescription system we relay to**, under our
  IT-supplier agreement. Multi-pharmacy API proxying is **confirmed permitted**
  under that agreement (D-12, resolved) — one vendor `Api-Key`, each location
  transacting under its own ΗΔΥΚΑ Basic-Auth identity.

## 3. Subprocessors

| Subprocessor | Purpose | Status |
|---|---|---|
| **AWS (EU region)** | Hosting (FT-10 target, D-11) | EU region pinned for data residency. Not yet deployed. |
| **Sentry** | Error monitoring | **Only if enabled AND EU-hosted org.** Off in every current compose; `send_default_pii=False` already pinned (`observability.py` `configure_sentry()`). |
| **Uptime monitor** (UptimeRobot / healthchecks.io tier) | External liveness on `/health/v1` | Rides FT-10. Sees no PHI (the probe is keyless and tenant-free). |
| ~~LLM provider~~ | — | **None at Tier-1** (no AI features). |

Any subprocessor added later (esp. an LLM at Tier-2) requires a DPA update +
controller notification.

## 4. Security measures (technical & organisational)

All verified against code:

- **Credentials encrypted at rest** — location ΗΔΥΚΑ username/password under
  AES-256-GCM, 12-byte random nonce prepended, base64 (`app/crypto.py`).
  Decrypted in-memory per request only, never logged (`routers/v1/deps.py:90-92`).
- **API keys** — `pa_<env>_<256-bit token>`, shown **once** at mint, stored only
  as a SHA-256 hash; no recovery path (`app/services/api_keys.py:31-37`).
- **TLS only** — keys are bearer credentials; the production front end is
  HTTPS-only with HTTP→HTTPS redirect (FT-10).
- **No auth oracle** — every authentication failure (missing/unknown/revoked
  key, inactive location/customer, env-prefix mismatch) returns one
  indistinguishable 401 (`services/api_keys.py:58-81`, `routers/v1/deps.py:32-36`).
- **PHI-free error envelopes** — `/v1` errors carry `{code, message,
  request_id}`; messages never contain AMKA or patient names, and upstream
  bodies are truncated (`routers/v1/errors.py`).
- **PHI-free logs** — the access log carries the route **template**
  (`/v1/patients/{patient_key}`), never the rendered path; patient identity
  appears only as a keyed HMAC-SHA256 pseudonym (`observability.py:56-70`,
  `:78-116`).
- **Consent attestation recorded** — consent-gated reads require
  `patientConsent=true` and the attestation (who/which-patient-pseudonym/which-
  key/when) is logged as the lawful-basis evidence
  (`routers/v1/patients.py:68-74`, `observability.py:112-116`).
- **Per-tenant isolation** — keys resolve to a single location; the conditions
  table is uniqueness-constrained per location so tenants cannot collide.
- **Boot-time fail-fast** — required secrets and the mock flag are validated at
  startup (`app/config.py`), so a misconfigured live box fails to boot rather
  than silently mis-serving (FT-15).

## 5. ToS skeleton inputs (for the D-13 author)

- **SLA / support** — TBD at contract time (D-11). Drives FT-8 alerting depth.
- **Rate limits** — per API key, default `120/minute`, deploy-configurable
  (`V1_RATE_LIMIT`, FT-1). Documented in [API.md](API.md) §6.
- **Acceptable use** — server-to-server integration; no scraping/abuse; one
  tenant's burst must not be engineered to degrade others.
- **Key custody** — customer safeguards keys; rotation/compromise procedure in
  [KEY-MANAGEMENT.md](KEY-MANAGEMENT.md).
- **Clinical liability stance** — PharmAssist provides decision support;
  "absence of an alert ≠ safe", intolerance screening is the caller's separate
  step, and the formulary **suggests, never decides** (`routers/v1/safety.py:36-46`).
- **Data residency** — EU (AWS EU region, D-11).

## 6. Open items for legal (D-13)

- Set a **retention period** for `b2b_patient_conditions` soft-deleted rows
  (indefinite today) and for the access logs.
- Confirm the **Sentry EU-hosting** requirement before enabling it.
- Author the DPA + ToS legal text from this annex (owner TBD; longest external
  lead time in the plan — re-flag at the first serious integrator conversation).
