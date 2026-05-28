"""Active safety alerts for the dashboard."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.drug_catalog import DrugCatalog
from app.db.session import get_session
from app.schemas.safety import SafetyAlertPayload
from app.services.pharmacy import find_pharmacy_by_name
from app.services.pharmapi import pharmapi_search_prescriptions
from app.utils.environment import is_mock_pharmapi

from ..constants import AlertStatus, PrescriptionStatus
from ..deps import get_current_user
from ..services.prescriptions import MOCK_PRESCRIPTIONS, MOCK_QUEUE_BASE
from ..services.safety_engine import evaluate_safety, load_active_safety_rules

router = APIRouter(prefix="/alerts", tags=["alerts"])


async def _resolve_atc_by_barcode(session: AsyncSession, barcodes: list[str]) -> dict[str, str]:
    """One query that maps medicine barcode → ATC via the local drug_catalog.

    v2 search doesn't carry ATC and there's no per-rx detail endpoint in the
    spec; the catalogue we already sync from /masterdata/medicines is the
    canonical source. Returns an empty dict if no barcodes resolve.
    """
    barcodes = [b for b in barcodes if b]
    if not barcodes:
        return {}
    rows = await session.scalars(select(DrugCatalog).where(DrugCatalog.gns_code.in_(barcodes)))
    return {row.gns_code: row.atc_code for row in rows}


def _live_rx_to_engine_shape(rx: dict, atc: str | None) -> dict:
    """Reshape a v2 search item into what evaluate_safety expects.

    `patient.id` collapses to AMKA — rx_history's live path takes an AMKA
    or EKAA, so a single identifier suffices.
    """
    amka = rx.get("patientAmka")
    return {
        "rxId": rx["rxId"],
        "patient": {"id": amka, "amka": amka},
        "medication": {"atcCode": atc},
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

    # Live path. Search pending (prescribed=False) → resolve each medicine's
    # ATC from drug_catalog in one query → batch-evaluate against pre-loaded
    # rules. There is no /prescriptions/{barcode} detail endpoint in v2, so
    # the catalogue we already sync from /masterdata/medicines is the only
    # path to ATC. Drugs missing from the catalogue resolve to None and
    # evaluate_safety silently skips their ATC-keyed checks.
    prescriptions = await pharmapi_search_prescriptions(prescribed=False, size=100)
    pending = [p for p in prescriptions if p["status"] == PrescriptionStatus.PENDING]

    barcode_to_atc = await _resolve_atc_by_barcode(
        session, [p.get("medicineBarcode") for p in pending]
    )
    rules = await load_active_safety_rules(session)

    alerts = []
    for rx in pending:
        atc = barcode_to_atc.get(rx.get("medicineBarcode") or "")
        shaped = _live_rx_to_engine_shape(rx, atc)
        payload = await evaluate_safety(session, shaped, pharmacy.id, rules=rules)
        alerts.extend(c for c in payload.checks if c.status != AlertStatus.OK)
    return alerts
