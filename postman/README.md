# Postman — PharmAssist B2B Core (/v1)

Import-and-run collection for the Tier-1 Core API (`docs/b2b-core/TICKETS.md`).
Covers every Core endpoint with success **and** error cases; each request carries
tests asserting the HTTP status and the `{"error": {code, message, request_id}}`
envelope, so a full collection run doubles as a contract smoke test.

## Run it (3 steps)

1. **Stack up + tenant minted** (mock mode is the default):

   ```bash
   docker compose up -d
   docker compose exec backend python -m scripts.b2b_admin create-customer --name "Demo SA"
   docker compose exec backend python -m scripts.b2b_admin create-location \
       --customer-id <customer-uuid> --name "Demo Store" --pharmapi-unit-id 70466 \
       --pharmapi-username demo --pharmapi-password demo --eopyy
   docker compose exec backend python -m scripts.b2b_admin mint-key --location-id <location-uuid>
   ```

   Copy the key — it is shown exactly once.

2. **Import** `PharmAssist-B2B-Core.postman_collection.json` and
   `PharmAssist-B2B-Core.postman_environment.json`, select the environment, and
   paste the key into `api_key`.

3. **Run the collection** (Collection Runner, or newman:
   `newman run PharmAssist-B2B-Core.postman_collection.json -e PharmAssist-B2B-Core.postman_environment.json`).
   Run folders in order — "Patient Conditions (flow)" is a
   create → duplicate-409 → list → patch → soft-delete sequence that cleans up
   after itself, so repeated runs stay green.

## Notes

- **Mock vs live:** the demo identifiers (AMKA `15031962456`, prescription
  `1262602210000100`, barcodes `3661001`/`3661002`) target the mock fixtures +
  seeded drug catalog. Against a live backend (`PHARMAPI_MOCK=false`) replace
  them with real test-environment values; the shapes and envelopes are identical
  by design (contract tests pin this).
- **`--eopyy` matters:** intolerances + medicine history return a 403
  `forbidden` envelope for non-ΕΟΠΥΥ locations (upstream rule 609) — mint the
  demo location with `--eopyy` or expect those two requests to fail their 200
  tests.
- **Rate limit:** every /v1 endpoint is limited **per API key** (default
  `120/minute`, deploy-configurable via `V1_RATE_LIMIT`). Exceeding it returns
  the standard envelope with `code: "rate_limited"` and a `Retry-After` header
  (seconds) — back off and retry rather than hammering.
- **TLS:** API keys are bearer credentials — only ever send them over HTTPS
  outside local development.
