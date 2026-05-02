"""Pharmapi (ΗΔΥΚΑ) bridge — connect, status, pharmacy lookup, prescription fetch."""

import time
from datetime import datetime, timezone

from fastapi import APIRouter, Depends

from ..deps import get_current_user
from ..schemas.auth import SessionStatus
from ..services.pharmapi import (
    SESSION_WINDOW_SECONDS,
    pharmapi_get,
    pharmapi_session,
    session_is_valid,
)


router = APIRouter(prefix="/pharmapi", tags=["pharmapi"])


@router.post("/connect")
async def pharmapi_connect(current: dict = Depends(get_current_user)):
    """
    Step 2: Establish (or refresh) the 24h Pharmapi session.

    Calls GET /api/v1user/me on Pharmapi with Basic Auth + Api-Key.
    Per ΗΔΥΚΑ docs: every pharmacist must call this at least once before
    using any other API endpoint. Must be refreshed within 24h.

    Error G12 = never connected → call this.
    Error G14 = 24h expired    → call this again.
    """
    # Correct path per docs: /api/v1/user/me (returns XML)
    data = await pharmapi_get("/api/v1/user/me", accept_xml=True)

    now = time.time()
    pharmapi_session.update({
        "connected": True,
        "connected_at": datetime.now(timezone.utc).isoformat(),
        "connected_at_ts": now,
        "user_data": data,
    })

    return {
        "success": True,
        "message": "Pharmapi session established. Valid for 24h.",
        "session_valid_until": datetime.fromtimestamp(
            now + SESSION_WINDOW_SECONDS, tz=timezone.utc
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


@router.get("/prescriptions/{barcode}")
async def get_prescription(barcode: str, current: dict = Depends(get_current_user)):
    """
    Load a prescription by barcode from Pharmapi.
    Requires active Pharmapi session.
    """
    return await pharmapi_get(f"/prescriptions/{barcode}")
