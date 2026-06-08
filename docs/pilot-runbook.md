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

For TLS, pick a mode now (see §6) and set `PILOT_DOMAIN` / `CADDY_TLS`
accordingly.

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
HOST=https://<your-host>          # add -k to curl below if using `tls internal`

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

## 6. TLS — pick one mode

Both modes are driven by env vars consumed by `frontend/Caddyfile`.

### a) Public auto-HTTPS (real DNS)
For a box with a public DNS name and ports 80/443 reachable from the internet.
Caddy obtains and renews a real certificate over ACME automatically.

```dotenv
PILOT_DOMAIN=pilot.example.gr
# CADDY_TLS left unset
```

DNS `A`/`AAAA` for `pilot.example.gr` must point at the host before first boot,
or the ACME challenge fails.

### b) Tailscale-only / internal CA
For a box with **no** public DNS or open ports — reachable only over a tailnet.
Caddy issues a cert from its own internal CA.

```dotenv
PILOT_DOMAIN=pilot-box            # or the node's MagicDNS name
CADDY_TLS=tls internal
```

Testers reach `https://pilot-box` over the tailnet. Either install Caddy's root
CA on each client (`docker compose -f compose.prod.yaml exec frontend cat
/data/caddy/pki/authorities/local/root.crt`) or accept the warning for the
pilot. The `caddy_data` volume persists the CA + issued certs across restarts.

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

## 12. Deploy to AWS (single EC2 box, Tailscale-only)

For an internal pilot, run the whole `compose.prod.yaml` stack on **one EC2
instance** reachable **only over your tailnet** — no public DNS, no open ports,
no ACME. This matches the app's single-worker design (the in-process Pharmapi
session can't be load-balanced anyway) and keeps the attack surface at zero.

```
  testers ── tailnet ──▶  EC2 (eu-central-1)
                          ├─ Caddy  (tls internal)  :443
                          ├─ backend (uvicorn, 1 worker)
                          └─ Postgres (pgdata on EBS)
  Security group: DENY all inbound from the internet.
```

`deploy/aws/user-data.sh` automates the box: it installs Docker + Tailscale,
joins the tailnet, pulls secrets from SSM, and `compose up`s with
`CADDY_TLS="tls internal"`. The sections below are the one-time setup around it.

### 12.1 One-time prerequisites

**a) Tailscale auth key** — in the Tailscale admin console (Settings → Keys),
generate a key (reusable or single-use; tag it e.g. `tag:pilot`). You'll store
it in SSM below.

**b) Secrets in SSM Parameter Store** — store every secret (plus the auth key)
as a `SecureString` under one prefix. From a workstation with AWS creds:

```bash
PREFIX=/pharmassist/pilot
put() { aws ssm put-parameter --type SecureString --name "$PREFIX/$1" --value "$2" --overwrite; }

put SECRET_KEY                "$(openssl rand -hex 32)"
put CREDENTIAL_ENCRYPTION_KEY "$(python3 -c 'import secrets,base64;print(base64.b64encode(secrets.token_bytes(32)).decode())')"
put POSTGRES_PASSWORD         "$(openssl rand -base64 24)"
put PHARMAPI_USERNAME         'medcare1pharmapi'
put PHARMAPI_PASSWORD         '<real ΗΔΥΚΑ password>'
put PHARMAPI_API_KEY          '<real ΗΔΥΚΑ api key>'
put TS_AUTHKEY                'tskey-auth-xxxxxxxx'
```

> The `PHARMAPI_*` values must be **real** — the seed authenticates against live
> ΗΔΥΚΑ even though the app runs mocked (see §3).

**c) IAM instance role** — attach a role with **`AmazonSSMManagedInstanceCore`**
(for Session Manager shell access) plus this inline policy so the box can read
its secrets:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    { "Effect": "Allow", "Action": "ssm:GetParameter", "Resource": "arn:aws:ssm:*:*:parameter/pharmassist/pilot/*" },
    { "Effect": "Allow", "Action": "kms:Decrypt", "Resource": "*" }
  ]
}
```

### 12.2 Launch the instance

| Setting | Value |
|---|---|
| AMI | Amazon Linux 2023 |
| Type | `t3.medium` (4 GB — the on-box `npm run build` needs headroom). `t3.small` is fine if you build images in CI and pull instead. |
| Storage | 30 GB gp3 (holds the `pgdata` + `caddy_data` volumes) |
| IAM role | the one from 12.1c |
| Security group | **No inbound rules.** Egress: allow all. (Optional: allow inbound **UDP 41641** for direct Tailscale; without it traffic is DERP-relayed, which still works.) |
| User data | paste `deploy/aws/user-data.sh`, editing the `CONFIG` block at the top (repo ref, `TS_HOSTNAME`, `SSM_PREFIX`) |

Tailscale needs **no** inbound SG rule — it dials out and relays, so the box
stays invisible to the internet.

### 12.3 First boot → migrate + seed

The script brings the stack up but stops short of seeding (it needs a live ΗΔΥΚΑ
session). Shell in — either **SSM Session Manager** (console → Connect) or, since
the script enabled Tailscale SSH, `tailscale ssh ec2-user@pharmassist-pilot` —
then:

```bash
cd /opt/pharmassist
# Log into https://test.e-prescription.gr/epregen2/ with the ΗΔΥΚΑ account first
# so the 24h session is live, then:
docker compose -f compose.prod.yaml --env-file .env.prod exec backend alembic upgrade head
docker compose -f compose.prod.yaml --env-file .env.prod exec backend python -m scripts.seed
```

Record the `Local login:` email the seed prints; testers reach the pilot at
**`https://pharmassist-pilot`** (or the full MagicDNS name in `.env.prod`'s
`PILOT_DOMAIN`).

### 12.4 Certificates

`tls internal` means Caddy serves a cert from its **own CA**, so browsers show a
warning until that CA is trusted. Either:

- **Accept the warning** (fine for an internal pilot), or
- **Install Caddy's root CA** on tester machines:
  ```bash
  docker compose -f compose.prod.yaml --env-file .env.prod exec frontend \
    cat /data/caddy/pki/authorities/local/root.crt
  ```
- **No-warning upgrade:** enable HTTPS in the tailnet admin and use Tailscale's
  Let's Encrypt certs (`tailscale cert <magicdns>`), pointing Caddy at the issued
  files instead of `tls internal`. Browser-trusted, no CA install.

### 12.5 Backups to S3

Extend the §8 nightly cron to push each dump off-box (grant the role
`s3:PutObject` on the bucket):

```cron
0 2 * * * cd /opt/pharmassist && /usr/bin/docker compose -f compose.prod.yaml --env-file .env.prod exec -T db pg_dump -U pharmassist -d pharmassist | gzip | aws s3 cp - s3://YOUR-BUCKET/pharmassist/pharmassist-$(date +\%F).sql.gz
```

### 12.6 Update / redeploy

```bash
cd /opt/pharmassist && git pull
docker compose -f compose.prod.yaml --env-file .env.prod up -d --build
docker compose -f compose.prod.yaml --env-file .env.prod exec backend alembic upgrade head
```

Containers use `restart: unless-stopped` and Docker is enabled at boot, so the
stack survives instance reboots on its own.

### 12.7 Teardown

Terminate the instance (the EBS volume and its `pgdata`/`caddy_data` go with it —
take a final dump first if you want to keep the data). Then delete the SSM
parameters and revoke the Tailscale key in the admin console.
