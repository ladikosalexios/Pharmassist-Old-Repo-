# PharmAssist — Internal Mock Pilot Runbook

Operational guide for standing up the **production-flavour** stack
(`compose.prod.yaml`) for an internal pilot. The app runs against **mock**
ΗΔΥΚΑ data (`PHARMAPI_MOCK=true`) but with real production hardening: baked
images (no source mounts), env-driven secrets, `COOKIE_SECURE=true` over HTTPS,
and Caddy fronting the SPA + API.

> **Audience:** whoever operates the pilot box. Assumes Docker + Docker Compose
> v2 and a clone of this repo on the host.

---

## 0. What you get

| Service    | Image                      | Exposed to host        | Role |
|------------|----------------------------|------------------------|------|
| `frontend` | Caddy + compiled SPA       | **80, 443**            | Serves the SPA, reverse-proxies the API, terminates TLS |
| `backend`  | uvicorn (1 worker, no reload) | — (network only)    | FastAPI app |
| `db`       | postgres:16-alpine         | — (network only)       | Postgres, data in the `pgdata` volume |

Only Caddy faces the host. The backend and database are reachable **only** on
the internal compose network.

---

## 1. Configure secrets

```bash
cp .env.prod.example .env.prod
```

Fill in `.env.prod` (it is gitignored). Generate the crypto material:

```bash
# SECRET_KEY
openssl rand -hex 32
# CREDENTIAL_ENCRYPTION_KEY
python -c "import secrets,base64; print(base64.b64encode(secrets.token_bytes(32)).decode())"
```

Set a strong `POSTGRES_PASSWORD`, and the three `PHARMAPI_*` values for the
ΗΔΥΚΑ account that will seed the demo data (see §3 for why these must be real
even in mock mode). `compose.prod.yaml` references every secret with
`${VAR:?...}`, so a missing value aborts the boot with a clear error.

Set `PILOT_DOMAIN` to your public hostname for automatic HTTPS (see §6).

---

## 2. Boot

```bash
docker compose -f compose.prod.yaml --env-file .env.prod up -d --build
```

First boot builds both images (frontend runs `npm ci && npm run build`; backend
installs `requirements.txt`). Watch them come up:

```bash
docker compose -f compose.prod.yaml --env-file .env.prod ps
docker compose -f compose.prod.yaml --env-file .env.prod logs -f backend
```

`db` must report **healthy** before `backend` starts (compose enforces this via
`depends_on`), and `backend` must be healthy before Caddy starts.

---

## 3. Migrate + seed the database

The image ships the migrations and the seed script. Run both **inside** the
backend container:

```bash
# Create the schema.
docker compose -f compose.prod.yaml --env-file .env.prod exec backend alembic upgrade head

# Populate the demo pharmacy, pharmacist, conditions and ADR reports.
docker compose -f compose.prod.yaml --env-file .env.prod exec backend python -m scripts.seed
```

> ### ⚠️ Seeding needs a live ΗΔΥΚΑ session
> Unlike `/auth/login` (which honours `PHARMAPI_MOCK=true` and returns a
> synthetic profile), **`scripts/seed` always authenticates against live
> Pharmapi** `GET /user/me` to materialise the pharmacy + pharmacist. So:
> - The `PHARMAPI_*` creds in `.env.prod` must be **real**.
> - ΗΔΥΚΑ sessions expire after 24h. If seeding fails with a `G14 / 24h session
>   expired` error, log into `https://test.e-prescription.gr/epregen2/` with
>   that account first, then re-run the seed.
>
> Everything **after** seeding runs on mock data — testers never touch ΗΔΥΚΑ.

The seed is idempotent (it TRUNCATEs its tables first) and prints the login it
created:

```
  Local login: <pharmacist-email>  /  test1234   (PharmAssist /auth/login)
  Pharmacy:    <pharmacy-uuid>  /  <name>  /  unit_id=…
```

**Record the pharmacist email and the pharmacy UUID** — you need them for login
and for inviting testers.

---

## 4. Log in

Open `https://<your-host>/login` and sign in with the credentials the seed
printed:

| Field    | Value                              |
|----------|------------------------------------|
| Email    | the `Local login:` email from §3   |
| Password | `test1234`                         |

This seeded account has `role=admin`, so it can invite other testers (§5).

---

## 5. Invite testers

Invitations are created by an admin via `POST /admin/invite`. There's no email
service yet — the invite URL is returned in the response (and logged to backend
stdout). Generate one with the admin session cookie:

```bash
HOST=https://<your-host>

# 1. Log in as the seeded admin → store the session cookie.
curl -sk -c cj.txt -X POST "$HOST/auth/login" \
  -H 'Content-Type: application/json' \
  -d '{"email":"<admin-email-from-seed>","password":"test1234"}'

# 2. Create an invite (pharmacy_id = the UUID the seed printed).
curl -sk -b cj.txt -X POST "$HOST/admin/invite" \
  -H 'Content-Type: application/json' \
  -d '{"email":"tester@example.gr","pharmacy_id":"<pharmacy-uuid-from-seed>"}'
```

The response contains `invite_url` like `/accept-invite?token=…`. Send the
tester `https://<your-host>/accept-invite?token=…`; the page lets them set a
local login password. Invites expire (see `INVITE_EXPIRE_DAYS`).

You can also drive this from the Swagger UI, but it isn't exposed through Caddy
by default — reach it via an SSH tunnel to the backend if needed.

---

## 6. TLS — automatic HTTPS

`frontend/Caddyfile` provisions and renews a real certificate over ACME
automatically. Set `PILOT_DOMAIN` to a public hostname with ports 80/443
reachable from the internet — two ways to get one:

```dotenv
# Your own domain (point an A/AAAA record here before first boot):
PILOT_DOMAIN=demo.example.gr

# — or, no domain at all — a free sslip.io name built from the public IP:
PILOT_DOMAIN=203.0.113.10.sslip.io
```

`sslip.io` resolves the embedded IP publicly, so ACME works with zero DNS setup —
ideal for a cheap demo box (see [`aws-public-deploy.md`](aws-public-deploy.md)).

> `PILOT_DOMAIN` defaults to `localhost`, which makes Caddy mint a local cert —
> useful for smoke-testing this exact config on a dev machine.

---

## 7. Demo data — IDs for testers

All seeded; available in the Counter queue immediately after §3. Drive the core
flow **Counter → Review → Dispense Wizard** with these.

**Happy path (clean dispense):**

| Rx ID         | Patient        | Drug          | Notes |
|---------------|----------------|---------------|-------|
| `RX2024-005`  | Maria Stavrou  | Warfarin 5 mg | PENDING, top of the queue — straightforward dispense |
| `RX2024-001`  | Sarah Johnson  | Amoxicillin   | PENDING |
| `RX2024-002`  | (queue)        | Warfarin      | PENDING |

**Safety-engine alerts (each trips a contraindication rule):**

| Rx ID            | Patient            | Trigger | Rule |
|------------------|--------------------|---------|------|
| `RX-ENGINE-001`  | Sarah Johnson      | Warfarin + pregnancy (AMKA 22071993789) | `WARFARIN_PREGNANCY_CONTRAINDICATION` |
| `RX-ENGINE-002`  | Nikos Papadopoulos | Aspirin + G6PD (AMKA 08111947033)       | `G6PD_ASPIRIN_HAEMOLYSIS` |
| `RX-ENGINE-003`  | Anna Kostas        | Metformin + severe renal (AMKA 12101948112) | `METFORMIN_RENAL_CONTRAINDICATION` |

There are also seeded ADR reports (`ADR-2026-0004…0009`) on the Side Effects
page and `RX-HIST-00x` rows in patient history.

---

## 8. Backups — nightly `pg_dump`

The DB port isn't published, so dump **through** the container. Create the
backup dir once (`mkdir -p /var/backups/pharmassist`), then add this to the
host's crontab (`crontab -e`). Adjust the repo path; note `%` must be escaped as
`\%` in cron:

```cron
# 02:00 nightly — compressed logical dump of the pilot DB, kept 14 days.
0 2 * * * cd /opt/pharmassist && /usr/bin/docker compose -f compose.prod.yaml --env-file .env.prod exec -T db pg_dump -U pharmassist -d pharmassist | gzip > /var/backups/pharmassist/pharmassist-$(date +\%F).sql.gz && find /var/backups/pharmassist -name 'pharmassist-*.sql.gz' -mtime +14 -delete
```

`exec -T` disables the pseudo-TTY (required from cron). Verify a dump by hand
first:

```bash
docker compose -f compose.prod.yaml --env-file .env.prod exec -T db \
  pg_dump -U pharmassist -d pharmassist | gzip > /tmp/test-dump.sql.gz
ls -lh /tmp/test-dump.sql.gz
```

---

## 9. Restore

The dump is a full logical backup (schema **and** data), so a restore needs an
empty database. Drop and recreate it, which means dropping the backend's
connections first:

```bash
BACKUP=/var/backups/pharmassist/pharmassist-2026-06-07.sql.gz

# 1. Stop the app so nothing holds a connection to the DB.
docker compose -f compose.prod.yaml --env-file .env.prod stop backend

# 2. Drop & recreate an empty database.
docker compose -f compose.prod.yaml --env-file .env.prod exec -T db \
  psql -U pharmassist -d postgres \
  -c "DROP DATABASE pharmassist WITH (FORCE);" \
  -c "CREATE DATABASE pharmassist OWNER pharmassist;"

# 3. Load the dump.
gunzip -c "$BACKUP" | docker compose -f compose.prod.yaml --env-file .env.prod exec -T db \
  psql -U pharmassist -d pharmassist

# 4. Bring the app back.
docker compose -f compose.prod.yaml --env-file .env.prod start backend
```

No `alembic upgrade` is needed afterwards — the dump already carries the schema
at the version it was taken.

---

## 10. Day-2 operations

```bash
# Tail logs
docker compose -f compose.prod.yaml --env-file .env.prod logs -f backend frontend

# Health (from the host, through Caddy)
curl -sk https://<your-host>/health          # {"status":"ok", ...}

# Update to a new build
git pull
docker compose -f compose.prod.yaml --env-file .env.prod up -d --build
docker compose -f compose.prod.yaml --env-file .env.prod exec backend alembic upgrade head

# Stop (data is preserved in the pgdata / caddy_data volumes)
docker compose -f compose.prod.yaml --env-file .env.prod down

# Nuke everything INCLUDING data + certs
docker compose -f compose.prod.yaml --env-file .env.prod down -v
```

---

## 11. Post-deploy smoke checklist

- [ ] `docker compose -f compose.prod.yaml --env-file .env.prod ps` — all healthy
- [ ] `curl -sk https://<host>/health` returns `{"status":"ok", …}`
- [ ] Login with the seeded admin succeeds; the session cookie is `Secure`
- [ ] Counter → click `RX2024-005` → Review → Dispense Wizard completes (mock)
- [ ] An engine Rx (`RX-ENGINE-001`) shows the contraindication alert
- [ ] Hard-refresh on `https://<host>/documentation` renders the page (no 404)
- [ ] An invited tester can open their `/accept-invite?token=…` link

---

## 12. Deploy to AWS

Deployment moved to a single **public-HTTPS** path — one small EC2 box, real cert
via your domain or a free `<ip>.sslip.io` name, reachable over the normal
internet. The Tailscale-only variant was removed.

See **[`aws-public-deploy.md`](aws-public-deploy.md)** for the full walkthrough:
launch a `t3.small`, open ports 80/443, paste `deploy/aws/user-data.sh` (it
installs Docker, builds the stack, migrates + seeds), and point clients at
`https://<host>`.

### Update / redeploy

```bash
cd /opt/pharmassist && git pull
docker compose -f compose.prod.yaml --env-file .env.prod up -d --build
docker compose -f compose.prod.yaml --env-file .env.prod exec backend alembic upgrade head
```

Containers use `restart: unless-stopped` and Docker is enabled at boot, so the
stack survives instance reboots on its own.

### Teardown

Terminate the instance (the EBS volume and its `pgdata`/`caddy_data` go with it —
take a final `pg_dump` first if you want to keep the data).
