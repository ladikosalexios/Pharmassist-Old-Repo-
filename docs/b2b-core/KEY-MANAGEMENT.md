# B2B API-key management — rotation & revocation (FT-9)

Operator runbook for the lifecycle of a location's `X-API-Key`. Pairs with
[ONBOARDING.md](ONBOARDING.md) (minting at provisioning) and
[OPERATIONS.md](OPERATIONS.md) (the access log this runbook greps).

## What a key is

- `pa_<env>_<token>` — `pa_live_…` or `pa_test_…` — shown **once** at mint,
  stored only as a SHA-256 hash (`backend/app/services/api_keys.py:31-37`,
  model `backend/app/db/models/api_key.py`). There is **no recovery**: a lost
  key is re-minted, never read back.
- A key belongs to one **location**. Multiple **active** keys per location are
  fully supported — `api_keys.key_hash` is the only unique constraint
  (`db/models/api_key.py:26`), there is no one-active-key rule — which is what
  makes zero-downtime rotation possible.
- The `pa_test_` / `pa_live_` prefix is **enforced**: a key only authenticates
  on a deployment whose mode matches (sandbox = mock = `pa_test_`, live =
  `pa_live_`). A mismatch returns the same indistinguishable 401 as any bad key
  (`services/api_keys.py:58-65`).
- **Entitlement tier is NOT a key property** — it lives on the *customer* (T2-1 /
  D-14: the whole estate is one tier), so a key inherits its customer's tier and
  rotation/revocation never changes it. To grant or revoke Tier-2/Clinical
  access, move the tier, not the key:

  ```bash
  python -m scripts.b2b_admin set-tier --customer-id <customer-uuid> --tier clinical
  ```

  The change takes effect on the next request (the gate reads the customer tier
  per call). A `core` customer's keys get `tier_required` (403) on every
  Clinical route; ordinal `platform ≥ clinical ≥ core`. `list` shows each
  customer's `tier=…`.

All commands run inside the backend container:
`docker compose exec backend python -m scripts.b2b_admin …`.

## Standard rotation (zero-downtime, planned)

Because a location can hold several active keys at once, rotate by **adding
before removing** — never revoke first.

1. **Mint a sibling** on the same location. `rotate-key` does this and prints
   both ids; it deliberately does **not** revoke the old one (auto-revoke would
   lock out a customer who hasn't deployed yet):

   ```bash
   python -m scripts.b2b_admin rotate-key --key-id <old-key-id>
   ```

2. **Hand the new key to the customer** over a secure channel; they deploy it.
3. **Confirm the cutover** — `list` shows the new key's `last_used_at` advancing
   and (ideally) the old one going quiet:

   ```bash
   python -m scripts.b2b_admin list
   ```

   (`last_used_at` is throttled to ~5-minute granularity —
   `backend/app/routers/v1/deps.py:29`, `:100-102` — so allow a few minutes.)
4. **Revoke the old key** explicitly, once traffic has moved:

   ```bash
   python -m scripts.b2b_admin revoke-key --key-id <old-key-id>
   ```

### Dry-run transcript (dev stack, 2026-06-10)

```text
$ python -m scripts.b2b_admin rotate-key --key-id 7c9983e5-ff29-42c8-ac02-4900b16e256d
[b2b-admin] rotated location key — old id 7c9983e5-…-4900b16e256d (still ACTIVE), new id f7bcae35-…-b9c955dfcbf5
[b2b-admin] Deploy the new key, confirm its last_used moves, THEN:
[b2b-admin]   python -m scripts.b2b_admin revoke-key --key-id 7c9983e5-ff29-42c8-ac02-4900b16e256d
[b2b-admin] This is the ONLY time the new key is shown — store it now:

    pa_test_waHpxAMklrcbl_…            # truncated; shown once

# Both keys authenticate during the cutover window:
old key  GET /v1/status -> 200
new key  GET /v1/status -> 200

$ python -m scripts.b2b_admin list
    key 7c9983e5-…  label='batch2-dryrun'          active  last_used=2026-06-10 19:03:09+00:00
    key f7bcae35-…  label='batch2-dryrun-rotated'  active  last_used=2026-06-10 19:06:02+00:00

$ python -m scripts.b2b_admin revoke-key --key-id 7c9983e5-ff29-42c8-ac02-4900b16e256d
[b2b-admin] key 7c9983e5-… revoked (label='batch2-dryrun')

# After revoke — old key is dead, new key still serves:
old key  GET /v1/status -> 401
new key  GET /v1/status -> 200
```

## Compromised key (incident — revoke first)

A leaked key is the one case where you revoke **immediately**; availability is
secondary to stopping the abuse.

1. **Revoke now:**

   ```bash
   python -m scripts.b2b_admin revoke-key --key-id <compromised-key-id>
   ```

   The next request on that key 401s (resolution rejects inactive keys —
   `services/api_keys.py:73`).

2. **Scope the exposure** from the FT-6 access log. Every `/v1` request emits a
   structured line carrying `api_key_id` (never the raw key, never PHI —
   `backend/app/observability.py:99-124`). Grep by the compromised key's id over
   the exposure window to see what it touched (which routes, which tenants,
   which patient pseudonyms):

   ```bash
   # JSON logs (LOG_FORMAT=json, FT-10): filter by api_key_id
   docker compose logs backend | grep '"api_key_id": "<compromised-key-id>"'
   ```

   `patient_ref` is an HMAC pseudonym, not an AMKA; recompute it for a known
   patient with the same `SECRET_KEY` to answer "was patient X exposed" without
   the log ever holding the identifier (`observability.py:56-70`).

3. **Issue a replacement** with `rotate-key` (or a plain `mint-key`) and deliver
   it over a secure channel.

4. **Notify** per the Data Processing Agreement breach-notification clause —
   inventory and roles in [DATA-PROCESSING.md](DATA-PROCESSING.md).

## Cadence

- **Routine rotation:** annually, or on any staff change at the customer who had
  access to the key.
- **On suspected exposure:** immediately, via the compromised-key procedure.
- A key never expires on its own — rotation is operator-driven by design (no
  silent lockouts).

## Operator audit trail

Every state-changing `b2b_admin` command (`create-customer`, `set-tier`,
`create-location`, `mint-key`, `rotate-key`, `revoke-key`) appends one
append-only row to `b2b_admin_audit` **in the same transaction as the change** —
so a mutation never lands without its audit row, and a failed audit rolls the
whole thing back. Each row records the actor, action, target id, and a
before→after `details` payload (e.g. `set-tier` stores `{"tier":{"from":"core",
"to":"clinical"}}`). The trail is **never** written a raw key or a ΗΔΥΚΑ
credential.

- **Actor** defaults to the OS user running the CLI; pass `--actor "name"` to
  attribute a shared-account session to a person.
- **Read it back** with `list-audit` (most recent first):

  ```bash
  python -m scripts.b2b_admin list-audit --limit 20
  python -m scripts.b2b_admin list-audit --target-id <customer|location|key uuid>
  ```

  `target_id` is plain text (no FK), so a row survives its target's deletion —
  you can still answer "who revoked this key / moved this tier" after the fact.

## Notes & limits

- `last_used_at` is a coarse usage signal (5-minute throttle), not an audit
  trail — use `list-audit` for operator actions and the FT-6 access log for
  per-request `/v1` forensics.
- In-process rate-limit counters and ΗΔΥΚΑ sessions are per-worker today
  (single worker, FT-7 deferred per D-8); rotation is unaffected (keys resolve
  from the DB on every request).
