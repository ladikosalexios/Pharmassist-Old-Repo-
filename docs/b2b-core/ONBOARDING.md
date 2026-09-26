# B2B per-tenant provisioning runbook (FT-11)

The operator-facing sequence to onboard one paying location end-to-end. A
colleague who didn't write this should be able to follow it cold against the dev
stack. Pairs with [KEY-MANAGEMENT.md](KEY-MANAGEMENT.md) (key lifecycle after
mint), [API.md](API.md) (what you hand the integrator), and
[OPERATIONS.md](OPERATIONS.md) (the FT-3 coverage gate).

All commands run inside the backend container:
`docker compose exec backend python -m scripts.b2b_admin …`.

> **Sandbox first.** The intended sequence mints a **sandbox** (`pa_test_`) key,
> runs the integrator's sandbox tests, and only then mints the **live**
> (`pa_live_`) key. The sandbox *stack* is a mock-mode deployment that lands with
> FT-10 (deferred per D-11); until it exists, the **dev stack is the sandbox**
> for this rehearsal (it runs mock mode, so it mints `pa_test_` keys by default).
> The steps below are written for the live target and annotated where the
> mock dev stack differs.

> **No ΗΔΥΚΑ credentials?** A location can be onboarded without any ΗΔΥΚΑ
> identity (safety check + drug catalogue only; retrieval answers 409). Skip
> steps 1–2 and follow the short path in [§6](#6-short-path--a-location-without-ηδυκα-credentials).

## 1. Collect (per location, secure channel)

| Field | Notes |
|---|---|
| ΗΔΥΚΑ pharmacy **unit id** | integer, e.g. `70466`. Cross-checked by `--verify`. |
| ΗΔΥΚΑ Basic-Auth **username** | the location's own ΗΔΥΚΑ identity. |
| ΗΔΥΚΑ **password** | **never** by email/chat. Prompted via `getpass` and AES-256-GCM-encrypted at rest (`backend/scripts/b2b_admin.py:61`, `:89-90`; `app/crypto.py`). |
| ΕΟΠΥΥ category? | yes/no — drives `--eopyy` (step 2). |

The password is the one field you must move over a secure channel (a password
manager share, not plaintext). It is encrypted before it touches the DB and is
never printed or logged.

## 2. Establish the ΕΟΠΥΥ (609) category

`--eopyy` mirrors ΗΔΥΚΑ's `isIka`. It gates intolerances + medicine history: a
non-ΕΟΠΥΥ location gets a clean `forbidden` (403, upstream 609) on those two
reads (`backend/app/routers/v1/patients.py:77-84`), everything else works.

- **PharmAssist cannot grant the category** — it is a property of the customer's
  ΗΔΥΚΑ account. If the customer needs it, they arrange it with ΗΔΥΚΑ
  (Hd@idika.gr). Document the expectation; don't block onboarding on it.
- The flag is **correctable later** — if the customer is wrong about it, re-mint
  the location or update the row; the 403 is clean, not a crash.

## 3. Mint

```bash
# a. customer (tenant root) — once per customer, not per location.
#    --tier sets the entitlement (default core). clinical/platform unlock the
#    Tier-2 /v1 routes; clinical_only is the base tier below core (safety check
#    + drug catalogue only, D-20). Per D-14 the tier is customer-level (the
#    whole estate), correctable later with `set-tier`.
python -m scripts.b2b_admin create-customer --name "Chain SA" --email ops@chain.gr \
    --tier core            # or clinical_only / clinical / platform

# b. location — --verify validates creds against ΗΔΥΚΑ + cross-checks the unit id
python -m scripts.b2b_admin create-location \
    --customer-id <customer-uuid> --name "Store 12" \
    --pharmapi-unit-id 70466 --pharmapi-username chain12 --eopyy --verify
#   (password prompted via getpass)

# c. sandbox key first (pa_test_ on a mock stack), then the live key once the
#    integrator's sandbox run is green
python -m scripts.b2b_admin mint-key --location-id <location-uuid> --label "chain12-pos"
```

- `--verify` calls ΗΔΥΚΑ live and warns if the unit id isn't in the account's
  units (`b2b_admin.py:65-78`). **It always hits the real upstream**, so it only
  works with real production creds — **skip `--verify` on the mock dev/sandbox
  stack** (fake creds would 401). Use it for the live mint.
- `mint-key` defaults its env to the **stack's mode**, not `ENV` (FT-13,
  `b2b_admin.py:41-48`): a mock stack mints `pa_test_`, a live stack mints
  `pa_live_`. It warns if you force the other env. The raw key is shown **once**.
- Every command above is **audited** — one append-only `b2b_admin_audit` row per
  mutation, committed atomically with the change (never a raw key or credential).
  Add `--actor "name"` on a shared box; review with
  `b2b_admin list-audit`. See [KEY-MANAGEMENT.md](KEY-MANAGEMENT.md).

## 4. Verify

```bash
# a. auth + identity echo (customer/location, ΕΟΠΥΥ flag)
curl -s https://api.<domain>/v1/status -H "X-API-Key: <key>"

# b. one patient lookup (sandbox: the mock fixture AMKA 15031962456)
curl -s https://api.<domain>/v1/patients/15031962456 -H "X-API-Key: <key>"

# c. FT-3 catalogue-coverage gate (admin session, not the tenant key) —
#    a recent `success` sync with with_coverage ≈ totalActive. See OPERATIONS.md.
curl -s https://api.<domain>/admin/sync-drug-catalog/status   # admin cookie
```

`GET /v1/status` returns customer identity + its `tier` (T2-1), location
identity, `isEopyy`, `mockMode`, and `pharmapiConnected`
(`backend/app/routers/v1/__init__.py:23-39`). `pharmapiConnected: false` before
the first upstream call is normal. A `core` customer's key gets `tier_required`
(403) on a Tier-2/Clinical route; raise the tier with `set-tier` to unlock them.

## 5. Hand off

- The API docs: [API.md](API.md) + [`api-reference.html`](api-reference.html)
  (and the runnable [`postman/`](../../postman/README.md) suite).
- Key-management expectations: [KEY-MANAGEMENT.md](KEY-MANAGEMENT.md).
- Support channel + SLA (D-11, TBD at contract time).
- Signed DPA on file before live PHI flows (FT-14/D-13 —
  [DATA-PROCESSING.md](DATA-PROCESSING.md)).

## 6. Short path — a location without ΗΔΥΚΑ credentials

For a customer with no ΗΔΥΚΑ account (an integrator, or a `clinical_only`
buyer — TIER0-RETRIEVAL-FREE.md T0-4). Nothing to collect over a secure
channel, no ΕΟΠΥΥ question, no `--verify`.

```bash
# a. customer — pick the tier explicitly. clinical_only = safety check + drug
#    catalogue search + conditions. core adds formulary alternatives (and
#    retrieval, which this location can't use). clinical adds Tier-2.
python -m scripts.b2b_admin create-customer --name "Integrator SA" --tier clinical_only

# b. location with NO ΗΔΥΚΑ identity — --no-retrieval is required; it refuses
#    every ΗΔΥΚΑ flag (--pharmapi-*, --eopyy, --verify) rather than drop one.
python -m scripts.b2b_admin create-location --customer-id <customer-uuid> \
    --name "Integrator (no ΗΔΥΚΑ)" --no-retrieval

# c. keys as normal
python -m scripts.b2b_admin mint-key --location-id <location-uuid> --label "integrator-prod"
```

- The location is audited as `CREATE_LOCATION_NO_RETRIEVAL` (its own verb, so
  the trail shows the missing credentials were intended — `list-audit --action
  CREATE_LOCATION_NO_RETRIEVAL`), and `b2b_admin list` shows it as
  `retrieval=none`.
- Verify with `GET /v1/status` → `location.retrievalAvailable: false`, then one
  `POST /v1/safety/check`. Patient/prescription routes answer
  `retrieval_unavailable` (409) by design ([API.md §2.2](API.md#22-locations-without-ηδυκα-credentials)).
- Adding ΗΔΥΚΑ credentials to such a location later has no CLI command yet —
  provision a new credentialed location instead.

---

## Dev-stack dry-run transcript (2026-06-10, mock mode = sandbox substitute)

Executed end-to-end against the running dev compose stack. `--verify` omitted
(mock stack has no real upstream — see step 3); PHI-free mock fixture used.

```text
$ b2b_admin create-customer --name "Batch2 DryRun SA" --email ops@batch2.example
[b2b-admin] customer created: id=147b977f-…-460c342fac15 name='Batch2 DryRun SA'

$ b2b_admin create-location --customer-id 147b977f-… --name "Batch2 Store 1" \
      --pharmapi-unit-id 70466 --pharmapi-username batch2demo --pharmapi-password demopass --eopyy
[b2b-admin] location created: id=9180c5c9-…-f3016889adfb name='Batch2 Store 1' unit=70466 eopyy=True

$ b2b_admin mint-key --location-id 9180c5c9-… --label "batch2-dryrun"
[b2b-admin] API key minted for location 'Batch2 Store 1' (key id 7c9983e5-…)
[b2b-admin] This is the ONLY time the key is shown — store it now:
    pa_test_…                         # mock stack → pa_test_ by default

# Verify — GET /v1/status with the new key:
{
  "customer": { "id": "147b977f-…", "name": "Batch2 DryRun SA" },
  "location": { "id": "9180c5c9-…", "name": "Batch2 Store 1", "isEopyy": true },
  "mockMode": true,
  "pharmapiConnected": false
}

# One patient lookup (mock fixture AMKA 15031962456) → HTTP 200, demographics returned.
```
