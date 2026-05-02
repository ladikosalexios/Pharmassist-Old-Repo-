"""Pharmacist ↔ prescriber message thread per prescription."""

import time
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException

from ..deps import get_current_user
from ..schemas.messages import MessagePayload
from ..services.messages import MOCK_MESSAGES


router = APIRouter(prefix="/messages", tags=["messages"])


@router.get("")
async def list_messages(rxId: str, current: dict = Depends(get_current_user)):
    """Return the message thread between this pharmacist and the prescriber for a given rxId."""
    return {"items": MOCK_MESSAGES.get(rxId, [])}


@router.post("")
async def post_message(payload: MessagePayload, current: dict = Depends(get_current_user)):
    if not payload.body.strip():
        raise HTTPException(status_code=400, detail="Message body cannot be empty.")
    msg = {
        "id": f"m-{int(time.time() * 1000)}",
        "rxId": payload.rxId,
        "to": payload.to,
        "from": "pharmacist",
        "fromName": current["name"],
        "body": payload.body.strip(),
        "sentAt": datetime.now(timezone.utc).isoformat(),
    }
    MOCK_MESSAGES.setdefault(payload.rxId, []).append(msg)
    return msg
