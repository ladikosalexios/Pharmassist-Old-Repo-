"""
PharmAssist POC — FastAPI Backend
----------------------------------
Auth flow (per ΗΔΥΚΑ docs):
  1. Pharmacist logs into PharmAssist  → gets our JWT
  2. Our backend calls Pharmapi GET /api/v1user/me (Basic Auth + Api-Key header)
       → "creates active connection" in ΗΔΥΚΑ, valid for 24h
  3. All other Pharmapi calls work for 24h using same Basic Auth + Api-Key
  4. After 24h, must call /api/v1user/me again to refresh

Required env vars (all have safe dev defaults — see app/config.py):
  PHARMAPI_USERNAME   e.g. medcare1pharmapi
  PHARMAPI_PASSWORD   e.g. Aa900919081908!!
  PHARMAPI_API_KEY    static key from your ΗΔΥΚΑ registration email
                      (per-app, shared across all pharmacists using your software)
  SECRET_KEY                JWT signing key (override in prod!)
  TOKEN_EXPIRE_MINUTES      default 480 (8h)
  CORS_ALLOW_ORIGINS        comma-separated; default '*'

Project layout:
  app/config.py  — typed Settings + get_settings() (cached)
  app/schemas/   — Pydantic API contracts (one module per domain)
  app/services/  — in-memory stores + business helpers (mock data, JWT,
                   Pharmapi client, PDF rendering, etc.)
  app/deps.py    — shared FastAPI dependencies (get_current_user via session cookie)
  app/routers/   — one APIRouter per domain
  main.py        — create_app() factory; uvicorn entrypoint (this file)
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import app.db.models  # noqa — registers all SQLAlchemy models at startup
from app.config import Settings, get_settings
from app.routers import (
    alerts,
    auth,
    documentation,
    health,
    instructions,
    messages,
    notifications,
    patients,
    pharmapi,
    prescriptions,
    safety_checks,
    side_effects,
    spc,
)

# Order doesn't affect routing (each router has its own prefix), but include
# order is what /docs and /openapi.json render in. Group public → auth → core
# domains.
_ROUTER_MODULES = (
    health,
    auth,
    pharmapi,
    prescriptions,
    safety_checks,
    spc,
    alerts,
    messages,
    documentation,
    instructions,
    side_effects,
    patients,
    notifications,
)


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build a fully-wired FastAPI app.

    Tests can construct an isolated instance with custom settings by passing
    one in directly; in production we just call ``create_app()`` which reads
    the cached settings.
    """
    if settings is None:
        settings = get_settings()

    app = FastAPI(
        title=settings.app_title,
        description=settings.app_description,
        version=settings.app_version,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allow_origins,
        allow_credentials=settings.cors_allow_credentials,
        allow_methods=settings.cors_allow_methods,
        allow_headers=settings.cors_allow_headers,
    )

    for module in _ROUTER_MODULES:
        app.include_router(module.router)

    return app


# Production / dev entrypoint: `uvicorn backend.main:app`.
app = create_app()
