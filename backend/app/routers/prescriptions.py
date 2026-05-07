"""Prescription queue + per-rx detail, approval, and partial update.

Bridge pattern
--------------
Set PHARMAPI_MOCK=false (env var) to switch from mock in-memory data to live
ΗΔΥΚΑ calls. Everything downstream (safety checks, patient lookup, dispensing
log) is identical in both modes.

  PHARMAPI_MOCK=true  (default)  → MOCK_PRESCRIPTIONS + MOCK_QUEUE_BASE
  PHARMAPI_MOCK=false            → pharmapi_search_prescriptions() + pharmapi_get()

Important: GET /prescriptions/{rx_id} in live mode calls GET /pharmapi/prescriptions/{barcode}.
That endpoint's response shape is TBD until the first real barcode is fetched.
Update _normalize_pharmapi_detail() once the shape is confirmed.

Order matters: ``/next`` is declared *before* ``/{rx_id}`` so FastAPI matches
the fixed path before the catch-all. Same reason ``/{rx_id}/approve`` comes
before the bare ``/{rx_id}``.
"""

import os
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException

from ..deps import get_current_user
from ..schemas.prescriptions import PrescriptionPatch
from ..services.pharmapi import pharmapi_get, pharmapi_search_prescriptions
from ..services.prescriptions import MOCK_PRESCRIPTIONS, MOCK_QUEUE_BASE


router = APIRouter(prefix="/prescriptions", tags=["prescriptions"])


def _is_mock() -> bool:
    """Re-read at request time so the flag can be toggled via env without restart."""
    return os.getenv("PHARMAPI_MOCK", "true").lower() not in ("false", "0", "no")


def _normalize_pharmapi_detail(raw: dict, barcode: str) -> dict:
    """
    Convert a live Pharmapi prescription detail response to our internal shape.

    ⚠️  The exact field names from Pharmapi are UNKNOWN until the first real
    barcode is fetched. This function contains best-guess mappings based on the
    search endpoint XML structure. Update immediately on first real call.
    """
    patient_info = raw.get("patientInfo") or {}
    return {
        "rxId": barcode,
        "code": barcode,
        "status": "PENDING",
        "source": "pharmapi",
        "_raw": raw,  # ← Remove once real shape is confirmed and mapped
        "patient": {
            "amka": patient_info.get("amka"),
            "name": " ".join(filter(None, [
                patient_info.get("firstName"),
                patient_info.get("lastName"),
            ])),
        },
        "medication": {
            # TBD — update when real detail endpoint response shape is confirmed
            "drugName": (raw.get("medication") or raw.get("drug") or {}).get("name"),
        },
        "prescriber": {
            # TBD — update when real detail endpoint response shape is confirmed
            "name": (raw.get("prescriber") or raw.get("doctor") or {}).get("name"),
        },
    }


# ── Queue + list ─────────────────────────────────────────────────────────────

@router.get("/next")
async def next_pending_prescription(current: dict = Depends(get_current_user)):
    """Return the next PENDING prescription in the queue (for the keyboard shortcut)."""
    if _is_mock():
        for base in MOCK_QUEUE_BASE:
            rx = MOCK_PRESCRIPTIONS.get(base["rxId"])
            status = rx["status"] if rx else base["status"]
            if status == "PENDING":
                return {**base, "status": status}
        raise HTTPException(status_code=404, detail="No pending prescriptions in the queue")

    # Live mode: fetch queue from ΗΔΥΚΑ, return first PENDING item
    items = await pharmapi_search_prescriptions(prescribed=False, size=10)
    pending = [i for i in items if i.get("status") == "PENDING"]
    if not pending:
        raise HTTPException(status_code=404, detail="No pending prescriptions in the queue")
    return pending[0]


@router.get("")
async def list_prescriptions(current: dict = Depends(get_current_user)):
    """
    Return the prescription queue for the dashboard, with up-to-date statuses.

    In live mode: medication and physician will be None — those fields are not
    in the ΗΔΥΚΑ search response. The frontend should populate them lazily from
    the detail call when a pharmacist opens a prescription for verification.
    """
    if _is_mock():
        items = []
        for base in MOCK_QUEUE_BASE:
            rx = MOCK_PRESCRIPTIONS.get(base["rxId"])
            status = rx["status"] if rx else base["status"]
            items.append({**base, "status": status})
        return {"items": items}

    # Live mode: fetch pending queue from ΗΔΥΚΑ
    items = await pharmapi_search_prescriptions(prescribed=False)
    return {"items": items}


# ── Per-prescription detail ───────────────────────────────────────────────────

@router.get("/{rx_id}")
async def get_prescription_for_verification(rx_id: str, current: dict = Depends(get_current_user)):
    """
    Return full prescription data for the verification UI.
    In live mode, rx_id is the ΗΔΥΚΑ barcode.
    """
    if _is_mock():
        rx = MOCK_PRESCRIPTIONS.get(rx_id)
        if not rx:
            raise HTTPException(status_code=404, detail=f"Prescription {rx_id} not found")
        return rx

    # Live mode: fetch detail by barcode from ΗΔΥΚΑ
    raw = await pharmapi_get(f"/prescriptions/{rx_id}")
    return _normalize_pharmapi_detail(raw, rx_id)


# ── Actions (approve / flag / patch) ────────────────────────────────────────
# Pharmapi has no "approve" or "flag" endpoint — dispense is tracked locally.
# In both modes these write to local state (mock dict or, later, dispensing_log DB).

@router.post("/{rx_id}/approve")
async def approve_prescription(rx_id: str, current: dict = Depends(get_current_user)):
    if _is_mock():
        rx = MOCK_PRESCRIPTIONS.get(rx_id)
        if not rx:
            raise HTTPException(status_code=404, detail=f"Prescription {rx_id} not found")
        rx["status"] = "COMPLETED"
        rx["completedAt"] = datetime.now(timezone.utc).isoformat()
        return {"success": True, "rxId": rx_id, "status": rx["status"], "completedAt": rx["completedAt"]}

    # Live mode: dispensing_log table not yet implemented (ADR-002). Fail closed
    # so a pharmacist never gets a green checkmark for a dispense that wasn't
    # persisted anywhere. Replace with a real write once ADR-002 lands.
    raise HTTPException(
        status_code=501,
        detail="Live dispense not yet wired to dispensing_log (ADR-002).",
    )


@router.patch("/{rx_id}")
async def patch_prescription(
    rx_id: str,
    patch: PrescriptionPatch,
    current: dict = Depends(get_current_user),
):
    """Partial update — used by the Flag Discrepancy modal."""
    if _is_mock():
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

    # Live mode: dispensing_log table not yet implemented (ADR-002). Same fail-
    # closed contract as approve — see comment there.
    raise HTTPException(
        status_code=501,
        detail="Live flag/patch not yet wired to dispensing_log (ADR-002).",
    )
