# PharmAssist — Test Environment Runbook

Operational guide for the **test stack** (`compose.test.yaml`) — a second,
production-flavour deploy pointed at the **real upstream test system**:
ΗΔΥΚΑ `testeps` for Pharmapi.

The pilot runbook (`docs/pilot-runbook.md`) covers the same stack against
**mock** upstreams; this document only documents what differs.

> **Retrieval-only note:** the HMVS/FMD and eDispensation sections that used
> to live here were removed with the execution path — see tag
> `hmvs-certified` for the full historical runbook.

> **Audience:** whoever operates the test box. Assumes Docker + Docker Compose
> v2 and a clone of this repo on the host.

> **Test data is synthetic but the stack stays HTTPS + access-restricted** —
> fronted by Caddy's auto-HTTPS at a public DNS name (or a free `<ip>.sslip.io`
> name) and login-gated. The upstream sandbox (testeps) contains no
> real-patient data, but pharmacist credentials can still link back to real
> accounts, so do not expose this stack on an open internet without auth.

---

## 0. What this gives you vs. the mock pilot

| Concern | `compose.prod.yaml` (mock pilot) | `compose.test.yaml` (test stack) |
|---|---|---|
| ΗΔΥΚΑ Pharmapi | `PHARMAPI_MOCK=true` — canned data | `PHARMAPI_MOCK=false` — live `testeps.e-prescription.gr/pharmapiv2` |
| Compose project | `pharmassist-pilot` | `pharmassist-test` |
| Postgres volume | `pgdata` | `pgdata_test` (separate — never shares rows) |
| Observability | optional | **Sentry + JSON logs**, slowapi rate limit on `/auth/login` |

The single-uvicorn-worker constraint still applies — the in-process Pharmapi
session tracker (`pharmapi_session`) is per-process state. Bumping workers
above 1 is gated on moving that to Redis (post-pilot B4).

---

## 1. Prereqs

* A working ΗΔΥΚΑ account on **testeps**, plus its API key.
* (Optional) A Sentry DSN. Unset → no init, no overhead.

---

## 2. Configure secrets

```bash
cp .env.test.example .env.test
```

Fill in `.env.test` (it is gitignored alongside `.env.prod`). Generate the
crypto material the same way as the pilot runbook §1.

`SENTRY_DSN` is optional; leave it empty for a quiet stack. `LOG_FORMAT=json`
is set by the compose file unconditionally so log aggregators get structured
output.

---

## 3. Boot

```bash
docker compose -f compose.test.yaml --env-file .env.test up -d --build
docker compose -f compose.test.yaml --env-file .env.test ps
docker compose -f compose.test.yaml --env-file .env.test logs -f backend
```

**Expected boot log lines** (in order):

1. ΗΔΥΚΑ version check from `pharmapi_check_version` — confirms credentials
   reach `testeps`. A 401 here is the canonical "creds wrong / Api-Key wrong"
   signal.
2. `Application startup complete` — uvicorn ready.

---

## 4. Migrate + seed

```bash
docker compose -f compose.test.yaml --env-file .env.test exec backend alembic upgrade head
docker compose -f compose.test.yaml --env-file .env.test exec backend python -m scripts.seed
```

`scripts/seed` authenticates against **live** Pharmapi `GET /user/me` to
materialise the pharmacy + pharmacist; the test stack does the same thing for
runtime calls, so seeding against `testeps` here is what makes the
click-through (§6) work without further setup.

> **ΕΟΠΥΥ vs. non-ΕΟΠΥΥ patient seeding.** Two demo AMKAs you'll see in the
> Test Book / pilot data behave differently against `testeps`:
>
> | AMKA / patient code | Status | What `/patient` and related calls return |
> |---|---|---|
> | `70014` | ΕΟΠΥΥ patient | full payload: intolerances, medicine history, conditions |
> | `70466` | non-ΕΟΠΥΥ patient | basic identity only — intolerances and medicine-history endpoints **expectedly return empty / 404** |
>
> A 404 on `/patient/70466/intolerances` is **not a bug**. The Counter / Review
> UI must degrade gracefully when those upstream endpoints are absent. Use
> `70014` for happy-path screenshots and `70466` to prove the empty-state
> rendering survives.

Record the `Local login:` email the seed prints.

---

## 5. ΗΔΥΚΑ smoke — click through the real upstream

Open `https://<your-host>/login` and sign in with the seeded credentials.

1. **Login** — proves `_start_pharmapi_session` opened the 24h session.
2. **Pending queue** — pulls live prescriptions for the pharmacy via Pharmapi.
3. **Open a real prescription** — pick the first barcode in the queue. The
   first real prescription is where you'll discover any `_normalize_pharmapi_detail`
   mapping gaps that the mock data hid (mock payloads were hand-crafted; real
   ΗΔΥΚΑ shape can drift). Expect at least one round of small mapping fixes
   here — write them up and ship a follow-up PR, do not patch on the box.
4. **Safety checks** — should evaluate against the patient context the queue
   carried in. ΕΟΠΥΥ vs. non-ΕΟΠΥΥ (see the §4 callout) drives which rules
   even have inputs to evaluate.
5. **Instructions** — generated client-side from the prescription detail.
6. **Documentation export** — write a documentation entry, export the PDF.

Anything that 502s here is a real upstream issue — capture the exact request
ID from the backend logs (now JSON-formatted under `LOG_FORMAT=json`) before
re-running.

---

## 6. Observability spot-checks

* **JSON logs** — `docker compose ... logs backend | tail -1 | jq .` parses.
* **Sentry** — with `SENTRY_DSN` set, force an error
  (`curl -k https://<host>/health/explode` if you've wired one — otherwise
  trigger a deliberate 500 some other way) and confirm the event appears in
  the Sentry project tagged `environment=test`.
* **Rate limiter** — slam `/auth/login` 11 times in a minute with the wrong
  password from the same IP; the 11th should return 429 with a
  slowapi-formatted body. The decorator is a no-op under pytest but live
  under uvicorn.

---

## 7. Day-2 ops

Identical to the pilot runbook §8–§10 — substitute `compose.test.yaml` /
`.env.test` everywhere `compose.prod.yaml` / `.env.prod` appears. The two
stacks co-exist on the same host because the compose project names
(`pharmassist-test` vs. `pharmassist-pilot`) and the pgdata volume names
(`pgdata_test` vs. `pgdata`) are distinct.

> ### ⚠️ Port collision when running side-by-side on one host
> Both stacks default to host ports **80 / 443** — Docker's port binding is
> exclusive, so the second `compose up` aborts with *"address already in
> use"* before any container starts. Two ways out:
> * Set `TEST_HTTP_PORT=8080` and `TEST_HTTPS_PORT=8443` in `.env.test`
>   (the compose file exposes both as overridable variables). Testers then
>   reach the stack at `https://<host>:8443/`. CORS / `PILOT_DOMAIN` follow
>   the same hostname; no other changes needed.
> * Or — the recommended deploy shape — give each stack its own host
>   so both can keep 443 and a real DNS name.

---

## 8. Tearing down

```bash
docker compose -f compose.test.yaml --env-file .env.test down       # keep data
docker compose -f compose.test.yaml --env-file .env.test down -v    # nuke pgdata_test + caddy_data
```

`down -v` deletes the local test rows but does NOT touch anything upstream.
