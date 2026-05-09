"""Automated safety checks per prescription."""

from fastapi import APIRouter, Depends, HTTPException

from ..deps import get_current_user
from ..services.safety_checks import MOCK_SAFETY_CHECKS

router = APIRouter(prefix="/safety-checks", tags=["safety-checks"])


@router.get("/{rx_id}")
async def get_safety_checks(rx_id: str, current: dict = Depends(get_current_user)):
    """Return the automated safety checks for a prescription."""
    checks = MOCK_SAFETY_CHECKS.get(rx_id)
    if checks is None:
        raise HTTPException(status_code=404, detail=f"Prescription {rx_id} not found")
    return {"rxId": rx_id, "checks": checks}
