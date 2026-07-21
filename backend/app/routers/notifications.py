"""Contact-prescriber record.

ΗΔΥΚΑ exposes only the prescriber's NAME (no email/phone/message channel), so
there is NO automated delivery to a physician. This endpoint records the
pharmacist's contact intent + note as an auditable documentation_logs row
(action_type=CONTACT_PRESCRIBER) — the honest, durable form of "I contacted the
prescriber". It never claims delivery.
"""

import ipaddress

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.utils.environment import is_mock_pharmapi

from ..constants import ActionType
from ..db.session import get_session
from ..deps import get_current_user
from ..schemas.notifications import PhysicianNotification
from ..services.documentation import record_prescription_action
from ..services.live_rx import resolve_live_rx_with_checks, shape_live_response
from ..services.pharmacy import find_pharmacy_by_name
from ..services.prescriptions import MOCK_PRESCRIPTIONS

router = APIRouter(prefix="/notifications", tags=["notifications"])


def _client_ip(request: Request) -> str | None:
    raw = request.client.host if request.client else None
    if raw:
        try:
            ipaddress.ip_address(raw)
            return raw
        except ValueError:
            pass
    return None


@router.post("/physician")
async def notify_physician(
    payload: PhysicianNotification,
    request: Request,
    current: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Record that the pharmacist contacted the prescriber about a prescription.

    Writes a documentation_logs row (CONTACT_PRESCRIBER) — auditable, not a send.
    Returns ``recorded: true`` (never ``delivered``): ΗΔΥΚΑ provides no physician
    channel, so nothing is transmitted. Resolves the rx snapshot the same way the
    flag path does (mock store, or live barcode → ΗΔΥΚΑ → shaped).
    """
    if is_mock_pharmapi():
        rx = MOCK_PRESCRIPTIONS.get(payload.rxId)
        if not rx:
            raise HTTPException(status_code=404, detail=f"Prescription {payload.rxId} not found")
        safety = [dict(c) for c in rx.get("safetyChecks", [])]
    else:
        pharmacy = await find_pharmacy_by_name(session, current["pharmacy"])
        if pharmacy is None:
            raise HTTPException(status_code=400, detail="Pharmacy not found for current user")
        ip = _client_ip(request)
        live_rx, checks_payload = await resolve_live_rx_with_checks(
            session, payload.rxId, pharmacy, ip or "0.0.0.0"
        )
        if live_rx is None:
            raise HTTPException(status_code=404, detail=f"Prescription {payload.rxId} not found")
        # mode="json" → datetimes become ISO strings for the JSONB snapshot.
        safety = [c.model_dump(by_alias=True, mode="json") for c in checks_payload.checks]
        rx = await shape_live_response(live_rx, safety)

    log = await record_prescription_action(
        session,
        action_type=ActionType.CONTACT_PRESCRIBER,
        rx=rx,
        safety_checks=safety,
        pharmacist_email=current["email"],
        pharmapi_exec_ref=None,
        discrepancy_type=None,
        notes=payload.message,
        info_provided=None,
        delivery_method=None,
        ip_address=_client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    return {"success": True, "recorded": True, "documentationLogId": str(log.id)}
