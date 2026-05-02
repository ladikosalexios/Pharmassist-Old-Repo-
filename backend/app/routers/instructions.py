"""Patient instructions: server-side render + delivery dispatch."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException

from ..deps import get_current_user
from ..schemas.instructions import InstructionsGenerate, InstructionsSend
from ..services.instructions import INSTRUCTION_DELIVERIES, render_instructions
from ..services.prescriptions import MOCK_PRESCRIPTIONS


router = APIRouter(prefix="/instructions", tags=["instructions"])


@router.post("/generate")
async def generate_instructions(
    payload: InstructionsGenerate,
    current: dict = Depends(get_current_user),
):
    rx = MOCK_PRESCRIPTIONS.get(payload.rxId)
    if rx is None:
        raise HTTPException(status_code=404, detail=f"Prescription {payload.rxId} not found")
    text = render_instructions(rx, payload.language, payload.options or {})
    return {"rxId": payload.rxId, "language": payload.language, "content": text}


@router.post("/send", status_code=201)
async def send_instructions(payload: InstructionsSend, current: dict = Depends(get_current_user)):
    rx = MOCK_PRESCRIPTIONS.get(payload.rxId)
    if rx is None:
        raise HTTPException(status_code=404, detail=f"Prescription {payload.rxId} not found")
    entry = {
        "rxId": payload.rxId,
        "patientId": payload.patientId or rx["patient"]["id"],
        "method": payload.method.upper(),
        "sentAt": datetime.now(timezone.utc).isoformat(),
        "by": current["email"],
        "size": len(payload.content or ""),
    }
    INSTRUCTION_DELIVERIES.append(entry)
    print(f"[Instructions] Sent {payload.method} to {entry['patientId']} for {payload.rxId} ({entry['size']} chars)")
    return {"success": True, **entry}
