"""Out-of-band notifications (physician channel for now)."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends

from ..deps import get_current_user
from ..schemas.notifications import PhysicianNotification
from ..services.notifications import PHYSICIAN_NOTIFICATIONS


router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.post("/physician")
async def notify_physician(
    payload: PhysicianNotification,
    current: dict = Depends(get_current_user),
):
    entry = {
        "rxId": payload.rxId,
        "message": payload.message,
        "sentAt": datetime.now(timezone.utc).isoformat(),
        "by": current["email"],
    }
    PHYSICIAN_NOTIFICATIONS.append(entry)
    print(f"[Notification] Physician for {payload.rxId}: {payload.message}")
    return {"success": True, "delivered": True, **entry}
