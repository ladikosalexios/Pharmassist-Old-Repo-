# PharmAssist POC

Proof-of-concept: pharmacist login → JWT → proxy calls to Pharmapi.

## Stack
- **Backend**: FastAPI (Python) + httpx
- **Frontend**: Single HTML file, no build step

## Setup (5 minutes)

### 1. Docker

The project runs in Docker. Containers are managed by Docker Compose.

1. Download [Docker](https://www.docker.com/products/docker-desktop/)
2. Run Docker
3. Navigate to project root
4. Run `docker compose build` (first time only)
5. Run `docker compose up -d`

### 2. Demo login

Navigate to http://localhost:5173/login

| Field    | Value                   |
|----------|-------------------------|
| Email    | ladikosalexios@gmail.com |
| Password | test1234 |

## Required secrets

The backend **fails to start** if any of these four is unset — there is no
insecure in-code fallback. The Docker stack supplies them in `compose.yaml`;
for any other setup, copy `backend/.env.example` to `backend/.env` and fill
them in.

| Variable | Purpose |
|----------|---------|
| `SECRET_KEY` | JWT / session-cookie signing key |
| `PHARMAPI_USERNAME` / `PHARMAPI_PASSWORD` | ΗΔΥΚΑ Pharmapi login |
| `PHARMAPI_API_KEY` | per-app ΗΔΥΚΑ key from your registration email |

`CREDENTIAL_ENCRYPTION_KEY` (AES key for encrypting stored credentials) is
also required — it is checked the first time a credential is encrypted or
decrypted, not at startup.

## What works

| Feature | Endpoint |
|---------|----------|
| Pharmacist login | POST /auth/login |
| Session check | GET /auth/me |
| Pharmapi ping | GET /pharmapi/ping |
| Pharmacy details | GET /pharmapi/pharmacy |
| Load prescription | GET /pharmapi/prescriptions/{barcode} |

## Optional tools

### Adminer — browse the database in your browser

Adminer is a lightweight web UI for inspecting the Postgres database. It's
defined as an opt-in service in `compose.yaml` under the `tools` profile,
so it does **not** start with `docker compose up` by default — you only run
it when you actually want it.

**Start Adminer:**

```bash
docker compose --profile tools up adminer
```

**Open it:**

http://localhost:8080

**Login:**

| Field    | Value             |
|----------|-------------------|
| System   | `PostgreSQL`      |
| Server   | `db` (prefilled)  |
| Username | `pharmassist`     |
| Password | `pharmassist_dev` |
| Database | `pharmassist`     |

Once logged in you get a sidebar of every table, can click rows to view/edit,
run ad-hoc SQL, and see a foreign-key schema diagram via the **schema** link
at the top.

**Stop it:** `docker compose --profile tools stop adminer` (or just `Ctrl+C`
if you ran it in the foreground).

> Adminer needs the `db` service to be running. The `db` service is added
> by the database-foundation PR — once that's merged, Adminer connects to
> it automatically over the compose network.

## What's NOT in this POC (next steps)

- PostgreSQL database (users, patients, audit log)
- Encrypted Pharmapi credential storage per pharmacy
- Safety engine (drug-drug interactions)
- Patient history / conditions
- Dispense flow
- React frontend with TanStack Query + Zustand

## Auto-generated API docs

FastAPI generates interactive Swagger UI automatically:
http://127.0.0.1:8000/docs

You can test all endpoints directly from the browser there.
