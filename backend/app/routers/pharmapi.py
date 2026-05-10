"""Pharmapi (ΗΔΥΚΑ) bridge — connect, status, pharmacy lookup, prescription fetch."""

import time
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Query

from ..deps import get_current_user
from ..schemas.auth import SessionStatus
from ..services.pharmapi import (
    SESSION_WINDOW_SECONDS,
    _start_pharmapi_session,
    pharmapi_get,
    pharmapi_search_prescriptions,
    pharmapi_session,
    session_is_valid,
)

router = APIRouter(prefix="/pharmapi", tags=["pharmapi"])


@router.post("/connect")
async def pharmapi_connect(current: dict = Depends(get_current_user)):
    """
    Step 2: Establish (or refresh) the 24h Pharmapi session.

    Calls GET /api/v1/user/me on Pharmapi with Basic Auth + Api-Key.
    Per ΗΔΥΚΑ docs: every pharmacist must call this at least once before
    using any other API endpoint. Must be refreshed within 24h.

    Error G12 = never connected → call this.
    Error G14 = 24h expired    → call this again.

    No-op refresh if /auth/login already opened the window.
    """
    data = await pharmapi_get("/api/v1/user/me", accept_xml=True)
    _start_pharmapi_session(data)
    return {
        "success": True,
        "message": "Pharmapi session established. Valid for 24h.",
        "session_valid_until": datetime.fromtimestamp(
            pharmapi_session["connected_at_ts"] + SESSION_WINDOW_SECONDS,
            tz=UTC,
        ).isoformat(),
        "pharmapi_user": data,
    }


@router.get("/status", response_model=SessionStatus)
async def pharmapi_status(current: dict = Depends(get_current_user)):
    """Show current Pharmapi session state."""
    if not pharmapi_session["connected"]:
        return SessionStatus(
            pharmapi_connected=False,
            connected_at=None,
            session_age_minutes=None,
            session_valid_for_minutes=None,
            pharmapi_user=None,
        )

    elapsed = time.time() - pharmapi_session["connected_at_ts"]
    remaining = max(0.0, SESSION_WINDOW_SECONDS - elapsed)

    return SessionStatus(
        pharmapi_connected=session_is_valid(),
        connected_at=pharmapi_session["connected_at"],
        session_age_minutes=round(elapsed / 60, 1),
        session_valid_for_minutes=round(remaining / 60, 1),
        pharmapi_user=pharmapi_session["user_data"],
    )


@router.get("/pharmacy")
async def get_my_pharmacy(current: dict = Depends(get_current_user)):
    """
    Fetch pharmacy details from Pharmapi.
    Requires active Pharmapi session (call /pharmapi/connect first).
    """
    return await pharmapi_get("/pharmacies/myPharmacy")


@router.get("/prescriptions/queue")
async def get_prescription_queue(
    current: dict = Depends(get_current_user),
    page: int = Query(0, ge=0, description="Page number (0-indexed)"),
    size: int = Query(50, ge=1, le=200, description="Results per page"),
    from_date: str | None = Query(None, alias="from", description="Start date YYYY-MM-DD"),
    to_date: str | None = Query(None, alias="to", description="End date YYYY-MM-DD"),
    amka: str | None = Query(None, description="Filter by patient AMKA"),
):
    """
    Fetch the pending prescription queue from ΗΔΥΚΑ.

    Returns prescriptions that have not yet been dispensed (prescribed=false).
    Each item contains: barcode, patient name, patient AMKA, issue/expiry date,
    status, insurance info.

    NOTE: Drug name and prescriber are NOT in the search response — those
    require a per-prescription detail call (GET /pharmapi/prescriptions/{barcode}).
    The frontend should populate those fields lazily when a pharmacist opens
    a prescription for verification.
    """
    items = await pharmapi_search_prescriptions(
        prescribed=False,
        page=page,
        size=size,
        from_date=from_date,
        to_date=to_date,
        amka=amka,
    )
    return {"items": items, "count": len(items)}


@router.get("/prescriptions/history")
async def get_prescription_history(
    current: dict = Depends(get_current_user),
    page: int = Query(0, ge=0),
    size: int = Query(50, ge=1, le=200),
    from_date: str | None = Query(None, alias="from"),
    to_date: str | None = Query(None, alias="to"),
    amka: str | None = Query(None),
    barcode: str | None = Query(None),
):
    """
    Fetch already-dispensed prescriptions from ΗΔΥΚΑ (prescribed=true).
    Useful for patient history lookup and dispensing audit.
    """
    items = await pharmapi_search_prescriptions(
        prescribed=True,
        page=page,
        size=size,
        from_date=from_date,
        to_date=to_date,
        amka=amka,
        barcode=barcode,
    )
    return {"items": items, "count": len(items)}


@router.get("/prescriptions/{barcode}")
async def get_prescription_detail(barcode: str, current: dict = Depends(get_current_user)):
    """
    Fetch full prescription detail by barcode from ΗΔΥΚΑ.

    This is the detail call — it returns drug name, dosage, prescriber, and
    all fields not present in the search/queue response. Call this when a
    pharmacist opens a prescription for verification.

    NOTE: Response shape is TBD — update the normaliser in services/prescriptions.py
    once the first real barcode is fetched and the JSON/XML shape is confirmed.
    """
    return await pharmapi_get(f"/prescriptions/{barcode}")
