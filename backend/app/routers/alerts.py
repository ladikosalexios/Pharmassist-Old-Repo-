"""Active safety alerts for the dashboard."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.schemas.safety import SafetyAlertPayload
from app.services.pharmacy import find_pharmacy_by_name
from app.services.pharmapi import (
    pharmapi_get_prescription_detail,
    pharmapi_search_prescriptions,
)
from app.utils.environment import is_mock_pharmapi

from ..constants import AlertStatus, PrescriptionStatus
from ..deps import get_current_user
from ..services.prescriptions import MOCK_PRESCRIPTIONS, MOCK_QUEUE_BASE
from ..services.safety_engine import evaluate_safety, load_active_safety_rules

router = APIRouter(prefix="/alerts", tags=["alerts"])


def _extract_atc(detail: dict) -> str | None:
    """Best-effort ATC extraction from the /prescriptions/{barcode} response.

    The v2 detail shape is not fully documented in-repo, so we probe the
    handful of likely paths and return None if none match — evaluate_safety
    is now tolerant of missing ATC.
    """
    if not isinstance(detail, dict):
        return None
    medicines = detail.get("medicines") or []
    if medicines and isinstance(medicines[0], dict):
        first = medicines[0]
        for key in ("atcCode", "atc", "atcCode4", "atcL3"):
            if first.get(key):
                return first[key]
    for key in ("atcCode", "atc"):
        if detail.get(key):
            return detail[key]
    return None


def _live_rx_to_engine_shape(rx: dict, detail: dict) -> dict:
    """Reshape a v2 search item + detail into what evaluate_safety expects.

    `patient.id` is set to the AMKA — rx_history's live path takes an
    AMKA-or-EKAA so the two collapse to one identifier for live mode.
    """
    amka = rx.get("patientAmka")
    return {
        "rxId": rx["rxId"],
        "patient": {"id": amka, "amka": amka},
        "medication": {"atcCode": _extract_atc(detail)},
    }


@router.get("/active", response_model=list[SafetyAlertPayload])
async def get_active_alerts(
    current: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Return active safety alerts for the dashboard."""
    pharmacy = await find_pharmacy_by_name(session, current["pharmacy"])
    if pharmacy is None:
        raise HTTPException(status_code=400, detail="Pharmacy not found for current user")

    if is_mock_pharmapi():
        # Mock path — unchanged. Per-rx DB rule queries are fine at mock-fixture scale.
        alerts: list[SafetyAlertPayload] = []
        for base in MOCK_QUEUE_BASE:
            rx = MOCK_PRESCRIPTIONS.get(base["rxId"])
            if rx is None or rx.get("status") != PrescriptionStatus.PENDING:
                continue
            payload = await evaluate_safety(session, rx, pharmacy.id)
            alerts.extend(c for c in payload.checks if c.status != AlertStatus.OK)
        return alerts

    # Live path. Search → enrich each pending with a detail call (no ATC in the
    # search response) → batch-evaluate against pre-loaded rules.
    prescriptions = await pharmapi_search_prescriptions(prescription_status="ACTIVE", size=100)
    pending = [p for p in prescriptions if p["status"] == PrescriptionStatus.PENDING]

    rules = await load_active_safety_rules(session)

    alerts = []
    for rx in pending:
        detail = await pharmapi_get_prescription_detail(rx["rxId"])
        shaped = _live_rx_to_engine_shape(rx, detail)
        payload = await evaluate_safety(session, shaped, pharmacy.id, rules=rules)
        alerts.extend(c for c in payload.checks if c.status != AlertStatus.OK)
    return alerts
