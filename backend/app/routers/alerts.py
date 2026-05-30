"""Active safety alerts for the dashboard."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.schemas.safety import SafetyAlertPayload
from app.services.drug_catalog import atc_codes_for_barcodes
from app.services.pharmacy import find_pharmacy_by_name
from app.services.pharmapi import pharmapi_search_prescriptions
from app.utils.environment import is_mock_pharmapi

from ..constants import AlertStatus, PrescriptionStatus
from ..deps import get_current_user
from ..services.prescriptions import MOCK_PRESCRIPTIONS, MOCK_QUEUE_BASE
from ..services.safety_engine import (
    checks_for_prescription,
    live_rx_to_engine_shape,
    load_active_safety_rules,
)

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

    rules = await load_active_safety_rules(session)

    if is_mock_pharmapi():
        alerts: list[SafetyAlertPayload] = []
        for base in MOCK_QUEUE_BASE:
            rx = MOCK_PRESCRIPTIONS.get(base["rxId"])
            if rx is None or rx.get("status") != PrescriptionStatus.PENDING:
                continue
            # Shared with /safety-checks/{rx} — demo rx_ids resolve from the
            # curated checklist, others from the engine, so the dashboard and
            # the detail view always agree about a given prescription.
            payload = await checks_for_prescription(
                session, base["rxId"], rx, pharmacy.id, rules=rules
            )
            alerts.extend(c for c in payload.checks if c.status != AlertStatus.OK)
        return alerts

    # Live path. Search pending (prescribed=False) → resolve each medicine's
    # ATC from drug_catalog in one query → batch-evaluate against pre-loaded
    # rules. There is no /prescriptions/{barcode} detail endpoint in v2, so
    # the catalogue we already sync from /masterdata/medicines is the only
    # path to ATC. Drugs missing from the catalogue resolve to None and
    # evaluate_safety silently skips their ATC-keyed checks.
    prescriptions = await pharmapi_search_prescriptions(prescribed=False, size=100)
    pending = [p for p in prescriptions if p["status"] == PrescriptionStatus.PENDING]

    barcode_to_atc = await atc_codes_for_barcodes(
        session, [p.get("medicineBarcode") for p in pending]
    )

    alerts = []
    for rx in pending:
        atc = barcode_to_atc.get(rx.get("medicineBarcode") or "")
        shaped = live_rx_to_engine_shape(rx, atc)
        payload = await checks_for_prescription(
            session, shaped["rxId"], shaped, pharmacy.id, rules=rules
        )
        alerts.extend(c for c in payload.checks if c.status != AlertStatus.OK)
    return alerts
