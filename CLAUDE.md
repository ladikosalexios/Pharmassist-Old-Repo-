# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

PharmAssist POC: pharmacist signs into our SPA → backend issues a session cookie → backend proxies calls to ΗΔΥΚΑ's Pharmapi (`pharmapiv2`). Around that bridge we layer a Postgres-backed safety engine, prescription review, ADR reporting, documentation log, and patient conditions.

**Retrieval-only.** PharmAssist retrieves and reviews prescriptions; it does not execute/dispense them — dispensing happens in the pharmacist's own pharmacy software (parasitic-first, `docs/agent-vs-spa-surface-split.md`). The eDispensation + HMVS/FMD execution path was removed; it is preserved in full at git tag `hmvs-certified`.

Stack: FastAPI (Python 3.13, async SQLAlchemy 2.0, asyncpg) + React 18 / Vite / TS / Tailwind + Postgres 16. Everything is orchestrated by `compose.yaml`.

## Verification and worktrees

Run `python3 scripts/verify.py` for the shared verification entry point. Read
[docs/VERIFY.md](docs/VERIFY.md) for dependencies, explicit exclusions, the isolated database
option and hook setup. Use `--with-db` for the seven database suites; never point verification
at the Compose or production database, and never run the live seed to prepare tests.
`AGENTS.md` is the tracked Codex entry point and links these same instructions.
Each worktree needs its own dependencies; local `.codex/config.toml` and agent presets are
not a prerequisite. Both providers' hooks delegate to shared scripts. Start the agent at the
worktree root: Claude Code loads none of this repository's hooks in a session started in a
subdirectory. In such a session, and in Codex unless you know the project and its hooks are
trusted, no hook verifies your work: run `python3 scripts/verify.py` from the worktree root
yourself before claiming completion.

## Running things

```bash
docker compose build            # first time only
docker compose up -d            # frontend :5173, backend :8000, db :5432
docker compose --profile tools up adminer   # opt-in DB UI at :8080
```

- Frontend dev URL: `http://localhost:5173` (login at `/login`). Swagger UI: `http://127.0.0.1:8000/docs`.
- Default seeded login lives in `README.md`.
- Vite dev server runs inside the `frontend` container and proxies API paths to `http://backend:8000` (see `frontend/vite.config.ts`). Frontend code uses relative paths and `credentials: "include"` so the session cookie rides along.

## Backend commands

Run inside the `backend` container (`docker compose exec backend …`) or with `cd backend` locally.

```bash
pip install -r requirements-dev.txt           # runtime + dev tools
python -m uvicorn main:app --reload           # local server (Dockerfile does this for you)

alembic upgrade head                          # apply migrations
alembic revision --autogenerate -m "msg"      # new migration (ALL models imported in alembic/env.py)

python -m scripts.seed                        # wipe & reseed core tables from a live Pharmapi /user/me

ruff check .                                  # lint
ruff format .                                 # format (CI runs `ruff format --check`)

pytest                                        # full suite
pytest tests/test_auth_db.py::test_login      # single test
```

Tests rely on env vars being set *before* `from main import app` because `get_settings()` is `@lru_cache`-d and several modules read settings at import time. See `tests/test_auth_db.py` for the pattern (it sets `PHARMAPI_MOCK=true`, `COOKIE_SECURE=false`, `CREDENTIAL_ENCRYPTION_KEY`, plus the four required secrets).

## Frontend commands

```bash
cd frontend
npm install
npm run dev           # vite (inside Docker this is the CMD)
npm run typecheck     # tsc -b --noEmit
npm run lint          # eslint .
npm run format        # prettier --write .
npm run build         # tsc -b && vite build
```

Frontend tests run with vitest: `npm run test` (`src/lib/api.test.ts`).

## Pre-commit / CI

`.pre-commit-config.yaml` runs ruff (backend + verification scripts), prettier (frontend),
and safety hooks. CI calls the same `scripts/verify.py` entry point separately for backend
and frontend. The default excludes the seven database suites explicitly; `--with-db` runs
those against a disposable local cluster. See [docs/VERIFY.md](docs/VERIFY.md) for exact coverage.
Keep the ruff pin in `backend/requirements-dev.txt` and `.pre-commit-config.yaml` aligned;
CI installs that requirements file.

## Configuration & secrets

`app/config.py` is the single source of truth. It uses a plain `Settings` model + `@lru_cache get_settings()`, no `pydantic-settings`. Four secrets **fail-fast at startup** (no in-code fallback): `SECRET_KEY`, `PHARMAPI_USERNAME`, `PHARMAPI_PASSWORD`, `PHARMAPI_API_KEY`. `CREDENTIAL_ENCRYPTION_KEY` (AES-256-GCM, base64-encoded) is checked the first time a credential is encrypted or decrypted, not at startup. `compose.yaml` supplies dev values; everything else copies `backend/.env.example` → `backend/.env`.

Toggles worth knowing:
- `PHARMAPI_MOCK=true` — skip live ΗΔΥΚΑ calls (used by tests and most local dev). Routers like `prescriptions.py` branch on `is_mock_pharmapi()` to use `MOCK_*` data instead of `pharmapi_*` services.
- `COOKIE_SECURE=false` — allow the session cookie over plain HTTP for local dev.

## Architecture — the big picture

### Auth and the session cookie (ADR-003)
- `POST /auth/login` (`backend/app/routers/auth.py`) accepts JSON, looks up the pharmacist, runs bcrypt **even when the email is unknown** (against a module-level dummy hash) to neutralise the timing side-channel, then asks Pharmapi to validate the ΗΔΥΚΑ credentials and starts a 24h upstream session.
- The JWT (`services/security.create_jwt`) is set as an httpOnly, SameSite=Strict cookie named `pharmassist_session`. It is **never** returned in the body, and **never** read from an `Authorization` header. `deps.get_current_user` reads the cookie and resolves pharmacist + pharmacy.
- `COOKIE_MAX_AGE_SECONDS` is derived from `TOKEN_EXPIRE_MIN` so the browser and the server expire the session at the same moment — keep them aligned if either changes.

### Pharmapi (ΗΔΥΚΑ) integration
- All upstream HTTP lives in `app/services/pharmapi.py`. It maintains a per-process 24h session tracker (`pharmapi_session` dict) — fine for a single uvicorn process; production would move this to Redis. Every call uses Basic Auth + `Api-Key` header (`pharmapi_headers()`).
- Pharmapi credentials are **encrypted at rest** in `pharmacist_pharmacies` (`pharmapi_username`, `pharmapi_password`) under `CREDENTIAL_ENCRYPTION_KEY` via `app/crypto.py` (AES-256-GCM, 12-byte nonce prepended, base64). They are decrypted only in-memory in `auth.login` and handed straight to the upstream client — never logged, never persisted plaintext.
- Two distinct passwords flow through the system; do not confuse them: the **local login password** (bcrypt-hashed in `pharmacists.password_hash`) and the **Pharmapi password** (encrypted in the link row). `scripts/seed.py` and its docstring are the canonical reference.

### Mock vs live bridge pattern
Routers that touch upstream data (`prescriptions.py`, `safety_checks.py`, `documentation.py`, etc.) branch on `is_mock_pharmapi()`. Mock data lives in `app/services/*` as module-level constants (`MOCK_PRESCRIPTIONS`, `MOCK_QUEUE_BASE`, …). When wiring a new live endpoint, keep the mock branch in lockstep so frontend behaviour is identical in both modes — see the docstring at the top of `routers/prescriptions.py`.

### Database
- Async SQLAlchemy 2.0 with `asyncpg`. Session factory in `app/db/session.py`; FastAPI dependency `get_session()` yields one session per request.
- Models live under `app/db/models/`. `app/db/base.py` defines the `Base` class with a `MetaData(naming_convention=…)` so constraints get deterministic names — important for Alembic to detect them as identical. `TimestampMixin` adds `created_at`/`updated_at` columns; **a BEFORE UPDATE trigger** (added in migration `463cc54e7949`) is the source of truth for `updated_at`, with SQLAlchemy `onupdate=now()` as the ergonomic ORM path. Migrations that update rows via raw SQL still get fresh timestamps from the trigger.
- Alembic config is wired so models import once in `alembic/env.py`. **Add every new model module there** or autogenerate will silently miss it. `main.py` re-imports `app.db.models` at startup for the same reason.
- Migration files in `alembic/versions/` are excluded from ruff (`pyproject.toml`).

### Safety engine
`app/services/safety_engine.py` evaluates `safety_rules` (DB-backed) against the patient + prescription context. Seeded rules and the drug catalog are populated by `scripts/seed.py` calling `scripts/seed_data.py`. New rules go in `seed_data.py` and are re-applied with `python -m scripts.seed` (which TRUNCATEs the seeded tables and reinserts).

### Frontend layout
- `frontend/src/App.tsx` defines public `/login` and an `AppShell`-wrapped authenticated tree (Dashboard, Prescription Verification, Documentation, Side Effects, Patient Profile, Instructions).
- API access goes through `frontend/src/lib/api.ts`. Everything calls `fetch` with `credentials: "include"` so the session cookie is sent. Throws `ApiError(status, detail)` on non-OK responses.
- Vite's proxy in `vite.config.ts` forwards `/auth`, `/pharmapi`, `/prescriptions`, … to the backend. Paths that collide with SPA routes (`/documentation`, `/side-effects`, `/patients`, `/instructions`) use a `spaProxy` bypass that sends `text/html` navigations to `index.html` and JSON/`*` fetches to the backend — be careful adding new paths in this overlap zone.

## Conventions worth knowing

- Ruff line length is 100. `app/db/models/*.py` has `F821`/`E501` waived because SQLAlchemy uses forward-ref strings and medical-context docstrings read worse when wrapped. Several services with clinical strings (`alerts`, `instructions`, `messages`, `pharmapi`, `prescriptions`, `safety_checks`, `spc`) also have `E501` waived — keep clinical narrative and long upstream URLs on one line rather than wrapping.
- Quote style: ruff format enforces double quotes (Python); prettier defaults (TS).
- `app/utils/environment.py` is the single read point for `PHARMAPI_MOCK`; don't `os.getenv` it directly elsewhere.
- When changing `get_settings()` behaviour in a test, call `get_settings.cache_clear()` *and* re-import modules that snapshot settings at import time (`services/security.py`, `services/pharmapi.py`, `db/session.py`).

## Additional design docs

`docs/` has SVG diagrams (`architecture.svg`, `db-schema.svg`, `sequence-login.svg`, `ticket-dependencies.svg`) and two living planning docs (`going-real-audit.md`, `going-real-prompts-v2.md`, `sprint-split.md`). They reflect work-in-progress; cross-check against code before relying on details.
