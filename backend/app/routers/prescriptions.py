"""Prescription queue + per-rx detail, approval, and partial update.

Order matters: ``/next`` is declared *before* ``/{rx_id}`` so FastAPI matches
the fixed path before the catch-all. Same reason ``/{rx_id}/approve`` comes
before the bare ``/{rx_id}``.
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException

from ..deps import get_current_user
from ..schemas.prescriptions import PrescriptionPatch
from ..services.prescriptions import MOCK_PRESCRIPTIONS, MOCK_QUEUE_BASE


router = APIRouter(prefix="/prescriptions", tags=["prescriptions"])


@router.get("/next")
async def next_pending_prescription(current: dict = Depends(get_current_user)):
    """Return the next PENDING prescription in the queue (for the keyboard shortcut)."""
    for base in MOCK_QUEUE_BASE:
        rx = MOCK_PRESCRIPTIONS.get(base["rxId"])
        status = rx["status"] if rx else base["status"]
        if status == "PENDING":
            return {**base, "status": status}
    raise HTTPException(status_code=404, detail="No pending prescriptions in the queue")


@router.get("")
async def list_prescriptions(current: dict = Depends(get_current_user)):
    """Return the prescription queue for the dashboard, with up-to-date statuses."""
    items = []
    for base in MOCK_QUEUE_BASE:
        rx = MOCK_PRESCRIPTIONS.get(base["rxId"])
        status = rx["status"] if rx else base["status"]
        items.append({**base, "status": status})
    return {"items": items}


@router.post("/{rx_id}/approve")
async def approve_prescription(rx_id: str, current: dict = Depends(get_current_user)):
    rx = MOCK_PRESCRIPTIONS.get(rx_id)
    if not rx:
        raise HTTPException(status_code=404, detail=f"Prescription {rx_id} not found")
    rx["status"] = "COMPLETED"
    rx["completedAt"] = datetime.now(timezone.utc).isoformat()
    return {"success": True, "rxId": rx_id, "status": rx["status"], "completedAt": rx["completedAt"]}


@router.get("/{rx_id}")
async def get_prescription_for_verification(rx_id: str, current: dict = Depends(get_current_user)):
    """Return prescription data (patient, medication, prescriber, safety checks) for the verification UI."""
    rx = MOCK_PRESCRIPTIONS.get(rx_id)
    if not rx:
        raise HTTPException(status_code=404, detail=f"Prescription {rx_id} not found")
    return rx


@router.patch("/{rx_id}")
async def patch_prescription(
    rx_id: str,
    patch: PrescriptionPatch,
    current: dict = Depends(get_current_user),
):
    """Partial update for a prescription — used by the Flag Discrepancy modal."""
    rx = MOCK_PRESCRIPTIONS.get(rx_id)
    if not rx:
        raise HTTPException(status_code=404, detail=f"Prescription {rx_id} not found")
    if patch.status is not None:
        rx["status"] = patch.status.upper()
    if patch.discrepancy_type is not None:
        rx["discrepancyType"] = patch.discrepancy_type
    if patch.notes is not None:
        rx["flagNotes"] = patch.notes
    if patch.notify_physician is not None:
        rx["notifyPhysician"] = bool(patch.notify_physician)
    return {
        "success": True,
        "rxId": rx_id,
        "status": rx["status"],
        "discrepancyType": rx.get("discrepancyType"),
        "notes": rx.get("flagNotes"),
        "notifyPhysician": rx.get("notifyPhysician"),
    }
