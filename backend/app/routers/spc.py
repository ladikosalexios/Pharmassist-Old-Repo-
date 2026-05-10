"""Summary of Product Characteristics lookup by ATC code."""

from fastapi import APIRouter, Depends, HTTPException

from ..deps import get_current_user
from ..services.spc import MOCK_SPC

router = APIRouter(prefix="/spc", tags=["spc"])


@router.get("/{atc_code}")
async def get_spc(atc_code: str, current: dict = Depends(get_current_user)):
    """Return the Summary of Product Characteristics for a given ATC code."""
    spc = MOCK_SPC.get(atc_code)
    if spc is None:
        raise HTTPException(status_code=404, detail=f"SPC not found for ATC {atc_code}")
    return spc
