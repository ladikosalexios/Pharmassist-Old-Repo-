"""Health probes.

Two distinct probes, deliberately not merged:

- ``GET /health`` — the legacy pilot-box probe. Reports the in-process **B2C**
  ΗΔΥΚΑ session + whether the vendor Api-Key is configured. Left untouched (the
  pilot runbook and its uptime check depend on this exact shape).
- ``GET /health/v1`` — the B2B liveness probe (FT-8). Unauthenticated and cheap,
  so an external uptime monitor (FT-10/FT-8 wiring, deferred) can hit it without
  a key. Reports the three signals an integrator's operator cares about: the DB
  is reachable, how stale the formulary (FT-4 masterdata sync) is, and the app
  version. Carries NO tenant data — it is keyless by design.
"""

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Response
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import get_settings
from ..db.models.catalog_sync_run import CatalogSyncRun
from ..db.session import get_session
from ..services.pharmapi import PHARMAPI_API_KEY, session_is_valid

router = APIRouter(tags=["health"])

# Mirror FT-4's stale-sync warn threshold (OPERATIONS.md nightly cron): a
# formulary whose last successful sync is older than this is decaying silently.
# Surfaced as a flag here; it does NOT flip the probe to unhealthy — a stale
# catalogue is an alert, not an outage (the endpoint still serves).
SYNC_STALE_AFTER_SECONDS = 48 * 3600


@router.get("/health")
async def health():
    return {
        "status": "ok",
        "pharmapi_session_valid": session_is_valid(),
        "pharmapi_api_key_set": bool(PHARMAPI_API_KEY),
        "timestamp": datetime.now(UTC).isoformat(),
    }


@router.get("/health/v1")
async def health_v1(response: Response, db: AsyncSession = Depends(get_session)):
    """Unauthenticated B2B liveness probe (FT-8): DB reachable, last FT-4 sync
    age, app version. 200 when the DB is reachable, 503 when it is not (so an
    external uptime monitor pages on a real outage). A stale catalogue is
    reported but does NOT downgrade the status."""
    settings = get_settings()
    now = datetime.now(UTC)

    db_ok = True
    last_sync: CatalogSyncRun | None = None
    try:
        await db.execute(text("SELECT 1"))
        last_sync = await db.scalar(
            select(CatalogSyncRun)
            .where(CatalogSyncRun.status == "success")
            .order_by(CatalogSyncRun.started_at.desc())
            .limit(1)
        )
    except Exception:
        db_ok = False

    sync_at = last_sync.finished_at if last_sync else None
    sync_age = int((now - sync_at).total_seconds()) if sync_at else None
    sync_stale = sync_age is None or sync_age > SYNC_STALE_AFTER_SECONDS

    response.status_code = 200 if db_ok else 503
    return {
        "status": "ok" if db_ok else "degraded",
        "version": settings.app_version,
        "db": {"reachable": db_ok},
        "lastCatalogSync": {
            "at": sync_at.isoformat() if sync_at else None,
            "ageSeconds": sync_age,
            "stale": sync_stale,
        },
        "timestamp": now.isoformat(),
    }
