"""Automated safety checks per prescription."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.session import get_session
from ..deps import get_current_user
from ..schemas.safety import SafetyChecksPayload
from ..services.pharmacy import find_pharmacy_by_name
from ..services.prescriptions import MOCK_PRESCRIPTIONS
from ..services.safety_engine import checks_for_prescription

router = APIRouter(prefix="/safety-checks", tags=["safety-checks"])


@router.get("/{rx_id}", response_model=SafetyChecksPayload)
async def get_safety_checks(
    rx_id: str,
    current: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Return automated safety checks for a prescription.

    Delegates to checks_for_prescription — the single source shared with the
    dashboard's /alerts/active — so the two views can never disagree. Demo
    rx_ids resolve from the curated MOCK_SAFETY_CHECKS; everything else is
    evaluated by the rule engine.
    """
    pharmacy = await find_pharmacy_by_name(session, current["pharmacy"])
    if pharmacy is None:
        raise HTTPException(status_code=400, detail="Pharmacy not found for current user")

    return await checks_for_prescription(session, rx_id, MOCK_PRESCRIPTIONS.get(rx_id), pharmacy.id)
