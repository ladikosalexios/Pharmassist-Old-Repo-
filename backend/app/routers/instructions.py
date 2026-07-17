"""Patient instructions: server-side render + delivery dispatch.

Mock mode resolves the prescription from MOCK_PRESCRIPTIONS; live mode from
the LATEST prescription_scans row for the barcode — the scan log is the local
record of what crossed the counter, so anything the pharmacist scanned can get
an instruction sheet without another ΗΔΥΚΑ round-trip.
"""

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.utils.environment import is_mock_pharmapi

from ..db.models.prescription_scan import PrescriptionScan
from ..db.session import get_session
from ..deps import get_current_user
from ..schemas.instructions import InstructionsGenerate, InstructionsSend
from ..services.instructions import INSTRUCTION_DELIVERIES, render_instructions
from ..services.prescriptions import MOCK_PRESCRIPTIONS
from ..services.spc import resolve_spc


async def _spc_for_meds(session: AsyncSession, rx: dict) -> dict[str, dict]:
    """Resolved SpcDetails per ATC for every medicine on the prescription —
    ingested documents win over the mock fixture (services/spc.resolve_spc)."""
    meds = rx.get("medications")
    if not (isinstance(meds, list) and meds):
        m = rx.get("medication")
        meds = [m] if isinstance(m, dict) else []
    out: dict[str, dict] = {}
    for med in meds:
        atc = med.get("atcCode") if isinstance(med, dict) else None
        if atc and atc not in out:
            payload = await resolve_spc(session, atc, barcode=med.get("nhrn"))
            if payload:
                out[atc] = payload
    return out


router = APIRouter(prefix="/instructions", tags=["instructions"])


async def _resolve_rx(session: AsyncSession, rx_id: str) -> dict | None:
    if is_mock_pharmapi():
        return MOCK_PRESCRIPTIONS.get(rx_id)
    scan = await session.scalar(
        select(PrescriptionScan)
        .where(PrescriptionScan.barcode == rx_id)
        .order_by(PrescriptionScan.created_at.desc())
        .limit(1)
    )
    return scan.rx_payload if scan else None


@router.post("/generate")
async def generate_instructions(
    payload: InstructionsGenerate,
    current: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    rx = await _resolve_rx(session, payload.rxId)
    if rx is None:
        raise HTTPException(status_code=404, detail=f"Prescription {payload.rxId} not found")
    spc_by_atc = await _spc_for_meds(session, rx)
    text = render_instructions(rx, payload.language, payload.options or {}, spc_by_atc)
    return {"rxId": payload.rxId, "language": payload.language, "content": text}


@router.post("/send", status_code=201)
async def send_instructions(
    payload: InstructionsSend,
    current: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    rx = await _resolve_rx(session, payload.rxId)
    if rx is None:
        raise HTTPException(status_code=404, detail=f"Prescription {payload.rxId} not found")
    patient = rx.get("patient") if isinstance(rx.get("patient"), dict) else {}
    entry = {
        "rxId": payload.rxId,
        "patientId": payload.patientId or patient.get("id") or rx.get("patientAmka"),
        "method": payload.method.upper(),
        "sentAt": datetime.now(UTC).isoformat(),
        "by": current["email"],
        "size": len(payload.content or ""),
    }
    INSTRUCTION_DELIVERIES.append(entry)
    print(
        f"[Instructions] Sent {payload.method} to {entry['patientId']} for {payload.rxId} ({entry['size']} chars)"
    )
    return {"success": True, **entry}
