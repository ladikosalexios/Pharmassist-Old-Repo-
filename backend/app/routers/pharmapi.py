"""Pharmapi (ΗΔΥΚΑ) bridge — connect, status, pharmacy lookup, prescription fetch."""

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query

from ..deps import get_current_user
from ..schemas.auth import SessionStatus
from ..services.pharmapi import (
    SESSION_WINDOW_SECONDS,
    _start_pharmapi_session,
    pharmapi_get,
    pharmapi_get_error_codes,
    pharmapi_search_prescriptions,
    pharmapi_session,
    session_status,
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
    data = await pharmapi_get("/api/v1/user/me")
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
    return SessionStatus(**session_status())


@router.get("/pharmacy")
async def get_my_pharmacy(current: dict = Depends(get_current_user)):
    """
    Fetch pharmacy unit details from Pharmapi.
    Requires active Pharmapi session (call /pharmapi/connect first).
    """
    return await pharmapi_get("/api/v1/user/me/units")


@router.get("/errors")
async def get_error_codes(current: dict = Depends(get_current_user)):
    """Fetch the full Pharmapi error code list from ΗΔΥΚΑ."""
    return await pharmapi_get_error_codes()


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
    status, insurance info, drug name (from medicines[0]) and prescriber name.

    GET /pharmapi/prescriptions/{barcode} returns the same search-filtered
    data — it is not a richer detail endpoint.
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
    # ΗΔΥΚΑ rejects `prescribed=true` without an `amka` (error code 606).
    # When the caller doesn't pass one, fall back to the unfiltered search —
    # the response then mixes dispensed + pending, which is at least non-empty.
    items = await pharmapi_search_prescriptions(
        prescribed=True if amka else None,
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
    Fetch prescription detail by barcode from ΗΔΥΚΑ.

    Pharmapi v2 has no dedicated per-prescription detail endpoint — the search
    endpoint filtered by barcode is the correct approach per the OpenAPI spec.
    Returns the first (and only) matching result, or 404 if not found.
    """
    results = await pharmapi_search_prescriptions(barcode=barcode)
    if not results:
        raise HTTPException(status_code=404, detail=f"Prescription {barcode} not found")
    return results[0]
