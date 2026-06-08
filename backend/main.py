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

import asyncio
import contextlib
import os
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import app.db.models  # noqa — registers all SQLAlchemy models at startup
from app.config import Settings, get_settings
from app.routers import (
    admin,
    alerts,
    auth,
    documentation,
    health,
    hmvs,
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
from app.services.audit import _background_tasks
from app.services.pharmapi import keepalive_loop, pharmapi_check_version
from app.utils.environment import is_mock_pharmapi


@asynccontextmanager
async def lifespan(_app: FastAPI):
    if not is_mock_pharmapi():
        await pharmapi_check_version()

    # Proactive ΗΔΥΚΑ session keep-alive (opt-in via PHARMAPI_KEEPALIVE_ENABLED).
    # Guarantees a /user/me call well within the 24h window so the upstream
    # session never lapses while idle.
    settings = get_settings()
    keepalive_task: asyncio.Task | None = None
    # Never start the keep-alive under pytest — tests must not make unattended
    # live ΗΔΥΚΑ calls, even when the container env enables it.
    if settings.pharmapi_keepalive_enabled and "pytest" not in sys.modules:
        keepalive_task = asyncio.create_task(
            keepalive_loop(settings.pharmapi_keepalive_interval_seconds)
        )

    try:
        yield
    finally:
        if keepalive_task is not None:
            keepalive_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await keepalive_task
        # Drain in-flight fire-and-forget audit tasks so a graceful restart
        # doesn't drop a pharmacist's last logged action (e.g. an HMVS supply).
        if _background_tasks:
            await asyncio.gather(*_background_tasks, return_exceptions=True)


# Order doesn't affect routing (each router has its own prefix), but include
# order is what /docs and /openapi.json render in. Group public → auth → core
# domains.
_ROUTER_MODULES = (
    health,
    auth,
    admin,
    pharmapi,
    hmvs,
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

    # Treat a missing ENV as production (secure-by-default).
    if os.getenv("ENV", "production") == "production":
        if not settings.cookie_secure:
            raise RuntimeError(
                "COOKIE_SECURE must be True in production. "
                "Set COOKIE_SECURE=false only in local dev .env."
            )

    app = FastAPI(
        title=settings.app_title,
        description=settings.app_description,
        version=settings.app_version,
        lifespan=lifespan,
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
