"""Active safety alerts for the dashboard."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.schemas.safety import SafetyAlertPayload
from app.services.pharmacy import find_pharmacy_by_name
from app.utils.environment import is_mock_pharmapi

from ..constants import PrescriptionStatus
from ..deps import get_current_user
from ..services.prescriptions import MOCK_PRESCRIPTIONS, MOCK_QUEUE_BASE
from ..services.safety_engine import evaluate_safety

router = APIRouter(prefix="/alerts", tags=["alerts"])


@router.get("/active", response_model=list[SafetyAlertPayload])
async def get_active_alerts(
    current: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Return active safety alerts for the dashboard."""
    pharmacy = await find_pharmacy_by_name(session, current["pharmacy"])
    if pharmacy is None:
        raise HTTPException(status_code=400, detail="Pharmacy not found for current user")

    if not is_mock_pharmapi():
        raise HTTPException(status_code=501, detail="Live alerts not yet wired.")

    alerts: list[SafetyAlertPayload] = []
    for base in MOCK_QUEUE_BASE:
        rx = MOCK_PRESCRIPTIONS.get(base["rxId"])
        if rx is None or rx.get("status") != PrescriptionStatus.PENDING:
            continue
        payload = await evaluate_safety(session, rx, pharmacy.id)
        alerts.extend(c for c in payload.checks if c.status != "ok")
    return alerts
