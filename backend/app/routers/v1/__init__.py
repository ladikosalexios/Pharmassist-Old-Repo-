"""B2B /v1 API surface — Tier-1 Core (docs/b2b-core/TICKETS.md).

Every endpoint sits behind the X-API-Key dependency (deps.get_api_context)
and is scoped to the resolved location. Errors render in the BC-5 envelope.
The B2C cookie-auth surface is a separate tree and is never touched here.
"""

from fastapi import APIRouter, Depends

from app.services.pharmapi import session_is_valid
from app.utils.environment import is_mock_pharmapi

from . import adr_reports, drugs, patients, prescriptions, safety
from .deps import ApiContext, get_api_context

router = APIRouter(prefix="/v1", tags=["b2b-v1"])
router.include_router(patients.router)
router.include_router(prescriptions.router)
router.include_router(drugs.router)
router.include_router(safety.router)
router.include_router(adr_reports.router)


@router.get("/status")
async def v1_status(ctx: ApiContext = Depends(get_api_context)):
    """Auth smoke endpoint: who am I, and is my location's ΗΔΥΚΑ session warm.

    `pharmapiConnected: false` is normal before the first upstream call —
    sessions are established lazily per location.
    """
    return {
        "customer": {"id": str(ctx.customer_id), "name": ctx.customer_name, "tier": ctx.tier},
        "location": {
            "id": str(ctx.location_id),
            "name": ctx.location_name,
            "isEopyy": ctx.is_eopyy,
        },
        "mockMode": is_mock_pharmapi(),
        "pharmapiConnected": session_is_valid(ctx.pharmapi.session_key),
    }
