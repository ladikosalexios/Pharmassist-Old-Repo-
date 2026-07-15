"""Pharmapi (ΗΔΥΚΑ) bridge — connect, status, pharmacy lookup, error codes.

Prescription retrieval for the UI lives in ``routers/prescriptions.py`` (and
``/v1/prescriptions`` for B2B); the old ``/pharmapi/prescriptions/*`` read
endpoints duplicated it with no callers and were removed.
"""

from datetime import UTC, datetime

from fastapi import APIRouter, Depends

from ..deps import get_current_user
from ..schemas.auth import SessionStatus
from ..services.pharmapi import (
    SESSION_WINDOW_SECONDS,
    _start_pharmapi_session,
    pharmapi_get,
    pharmapi_get_error_codes,
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
