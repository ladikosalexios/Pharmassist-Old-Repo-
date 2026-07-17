"""Automated safety checks per prescription."""

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.session import get_session
from ..deps import get_current_user
from ..schemas.safety import SafetyChecksPayload
from ..services.live_rx import resolve_live_rx_with_checks
from ..services.pharmacy import find_pharmacy_by_name
from ..services.prescriptions import MOCK_PRESCRIPTIONS
from ..services.safety_engine import checks_for_prescription
from ..utils.environment import is_mock_pharmapi

router = APIRouter(prefix="/safety-checks", tags=["safety-checks"])


def _client_ip(request: Request) -> str:
    import ipaddress

    raw = request.client.host if request.client else None
    if raw:
        try:
            ipaddress.ip_address(raw)
            return raw
        except ValueError:
            pass
    return "0.0.0.0"


@router.get("/{rx_id}", response_model=SafetyChecksPayload)
async def get_safety_checks(
    rx_id: str,
    request: Request,
    current: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Return automated safety checks for a prescription.

    Uses the SAME resolution as GET /prescriptions/{barcode} so the review
    page's safety panel can never disagree with (or 404 while) the detail card
    loads. Mock demo rx_ids resolve from MOCK_PRESCRIPTIONS + the curated
    checklist; live mode resolves the barcode upstream and evaluates per line.
    """
    pharmacy = await find_pharmacy_by_name(session, current["pharmacy"])
    if pharmacy is None:
        raise HTTPException(status_code=400, detail="Pharmacy not found for current user")

    if is_mock_pharmapi():
        return await checks_for_prescription(
            session, rx_id, MOCK_PRESCRIPTIONS.get(rx_id), pharmacy.id, verbose_spc=True
        )

    rx, payload = await resolve_live_rx_with_checks(session, rx_id, pharmacy, _client_ip(request))
    if payload is None:
        raise HTTPException(status_code=404, detail=f"Prescription {rx_id} not found")
    return payload
