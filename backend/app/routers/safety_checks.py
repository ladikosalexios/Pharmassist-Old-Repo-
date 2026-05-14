"""Automated safety checks per prescription."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.session import get_session
from ..deps import get_current_user
from ..schemas.safety import SafetyChecksPayload
from ..services.pharmacy import find_pharmacy_by_name
from ..services.prescriptions import MOCK_PRESCRIPTIONS
from ..services.safety_checks import MOCK_SAFETY_CHECKS
from ..services.safety_engine import evaluate_safety

router = APIRouter(prefix="/safety-checks", tags=["safety-checks"])


@router.get("/{rx_id}", response_model=SafetyChecksPayload)
async def get_safety_checks(
    rx_id: str,
    current: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Return automated safety checks for a prescription.

    Two exclusive paths:
    - MOCK_SAFETY_CHECKS owns a fixed set of demo rx_ids (RX2024-*) with
      hand-crafted, clinically complete results. Those rx_ids are served
      directly from the mock so the engine cannot silently replace them with
      sparser output while the rule data is still being built out.
    - All other rx_ids are evaluated by the rule engine against the live
      safety_rules table, patient conditions, and medicine history.

    Once the rule data and patient history are complete enough to cover the
    demo prescriptions, delete the MOCK_SAFETY_CHECKS branch and let the
    engine own everything.
    """
    mock_checks = MOCK_SAFETY_CHECKS.get(rx_id)
    if mock_checks is not None:
        return SafetyChecksPayload(rx_id=rx_id, checks=[], source="mock", legacy_checks=mock_checks)

    rx = MOCK_PRESCRIPTIONS.get(rx_id)
    if rx is None:
        raise HTTPException(status_code=404, detail=f"Prescription {rx_id} not found")

    pharmacy = await find_pharmacy_by_name(session, current["pharmacy"])
    if pharmacy is None:
        raise HTTPException(status_code=400, detail="Pharmacy not found for current user")

    return await evaluate_safety(session, rx, pharmacy.id)
