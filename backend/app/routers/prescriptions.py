"""Prescription queue + per-rx detail, approval, and partial update.

Bridge pattern
--------------
Set PHARMAPI_MOCK=false (env var) to switch from mock in-memory data to live
ΗΔΥΚΑ calls. Everything downstream (safety checks, patient lookup, dispensing
log) is identical in both modes.

  PHARMAPI_MOCK=true  (default)  → MOCK_PRESCRIPTIONS + MOCK_QUEUE_BASE
  PHARMAPI_MOCK=false            → pharmapi_search_prescriptions()

Order matters: ``/next`` is declared *before* ``/{rx_id}`` so FastAPI matches
the fixed path before the catch-all. Same reason ``/{rx_id}/approve`` comes
before the bare ``/{rx_id}``.
"""

import ipaddress
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.utils.environment import is_mock_pharmapi

from ..constants import ActionType, DeliveryMethod, PrescriptionStatus
from ..db.session import get_session
from ..deps import get_current_user
from ..schemas.prescriptions import ApproveResponse, PatchResponse, PrescriptionPatch
from ..services.documentation import record_prescription_action
from ..services.pharmacy import find_pharmacy_by_name
from ..services.pharmapi import (
    pharmapi_execute_prescription,
    pharmapi_search_prescriptions,
)
from ..services.prescriptions import MOCK_PRESCRIPTIONS, MOCK_QUEUE_BASE
from ..services.safety_engine import checks_for_prescription

router = APIRouter(prefix="/prescriptions", tags=["prescriptions"])


def _client_meta(request: Request) -> tuple:
    """(ip, user_agent) for documentation_logs columns. Both nullable upstream.

    documentation_logs.ip_address is a Postgres INET — non-IP strings
    (e.g. 'testclient' under TestClient, or a proxy-forwarded hostname)
    will fail validation. Coerce anything we can't parse to None.
    """
    raw = request.client.host if request.client else None
    ip = None
    if raw:
        try:
            ipaddress.ip_address(raw)
            ip = raw
        except ValueError:
            ip = None
    return ip, request.headers.get("user-agent")


# ── Queue + list ─────────────────────────────────────────────────────────────


@router.get("/next")
async def next_pending_prescription(current: dict = Depends(get_current_user)):
    """Return the next PENDING prescription in the queue (for the keyboard shortcut)."""
    if is_mock_pharmapi():
        for base in MOCK_QUEUE_BASE:
            rx = MOCK_PRESCRIPTIONS.get(base["rxId"])
            status = rx["status"] if rx else base["status"]
            if status == PrescriptionStatus.PENDING:
                return {**base, "status": status}
        raise HTTPException(status_code=404, detail="No pending prescriptions in the queue")

    # Live mode: fetch queue from ΗΔΥΚΑ, return first PENDING item
    items = await pharmapi_search_prescriptions(prescribed=False, size=10)
    pending = [i for i in items if i.get("status") == PrescriptionStatus.PENDING]
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
    if is_mock_pharmapi():
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
async def get_prescription_for_verification(
    rx_id: str,
    current: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """
    Return full prescription data for the verification UI.
    In live mode, rx_id is the ΗΔΥΚΑ barcode.

    `safetyChecks` is populated from checks_for_prescription — the same source
    the dashboard's /alerts/active uses — so the verification view can never
    show a different set of checks than the dashboard flagged.
    """
    if is_mock_pharmapi():
        rx = MOCK_PRESCRIPTIONS.get(rx_id)
        if not rx:
            raise HTTPException(status_code=404, detail=f"Prescription {rx_id} not found")
        pharmacy = await find_pharmacy_by_name(session, current["pharmacy"])
        if pharmacy is None:
            raise HTTPException(status_code=400, detail="Pharmacy not found for current user")
        payload = await checks_for_prescription(session, rx_id, rx, pharmacy.id)
        return {**rx, "safetyChecks": [c.model_dump(by_alias=True) for c in payload.checks]}

    # Live mode: Pharmapi has no per-prescription detail endpoint.
    # Use the search endpoint filtered by barcode — returns the same shape
    # as the list view, already normalised by _parse_prescription_search_json.
    results = await pharmapi_search_prescriptions(barcode=rx_id)
    if not results:
        raise HTTPException(status_code=404, detail=f"Prescription {rx_id} not found")
    return results[0]


# ── Actions (approve / flag / patch) ────────────────────────────────────────
# Approve: POSTs (fake) to ΗΔΥΚΑ for an exec_ref, then writes a documentation_logs
# row (action_type=APPROVE) with the safety-check snapshot. Mock-only.
# Flag: PATCH with status=FLAGGED writes a documentation_logs row (action_type=FLAG)
# with the snapshot + discrepancy fields. No ΗΔΥΚΑ call (not a dispense).
# Both fail closed in live mode until real ΗΔΥΚΑ dispense wiring lands.


@router.post("/{rx_id}/approve", response_model=ApproveResponse)
async def approve_prescription(
    rx_id: str,
    request: Request,
    current: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    if not is_mock_pharmapi():
        # Real ΗΔΥΚΑ dispense POST not yet wired.
        raise HTTPException(
            status_code=501,
            detail="Live dispense not yet wired to ΗΔΥΚΑ POST.",
        )

    rx = MOCK_PRESCRIPTIONS.get(rx_id)
    if not rx:
        raise HTTPException(status_code=404, detail=f"Prescription {rx_id} not found")

    # 1) Snapshot safety checks at action time (cast to plain list of dicts so
    #    JSONB serialisation doesn't surprise us if the source ever shifts to
    #    something pydantic-ish).
    snapshot = [dict(c) for c in rx.get("safetyChecks", [])]

    # 2) Pretend-POST to ΗΔΥΚΑ. Returns a synthetic exec_ref in mock mode.
    exec_resp = await pharmapi_execute_prescription(
        barcode=rx_id,
        eof_licence_no=rx.get("prescriber", {}).get("licenceId", ""),
    )

    # 3) Persist documentation_logs row.
    ip, ua = _client_meta(request)
    log = await record_prescription_action(
        session,
        action_type=ActionType.APPROVE,
        rx=rx,
        safety_checks=snapshot,
        pharmacist_email=current["email"],
        pharmapi_exec_ref=exec_resp["exec_ref"],
        discrepancy_type=None,
        notes=None,
        info_provided="Counselling delivered per SPC",
        delivery_method=DeliveryMethod.DIGITAL,
        ip_address=ip,
        user_agent=ua,
    )

    # 4) Mutate in-memory mock so subsequent GETs reflect COMPLETED status.
    rx["status"] = PrescriptionStatus.COMPLETED
    rx["completedAt"] = datetime.now(UTC).isoformat()

    return ApproveResponse(
        success=True,
        rxId=rx_id,
        status=rx["status"],
        completedAt=rx["completedAt"],
        execId=exec_resp["exec_ref"],
        documentationLogId=str(log.id),
    )


@router.patch("/{rx_id}", response_model=PatchResponse)
async def patch_prescription(
    rx_id: str,
    patch: PrescriptionPatch,
    request: Request,
    current: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Partial update — used by the Flag Discrepancy modal.

    A FLAGGED status flip writes a documentation_logs row (action_type=FLAG).
    Other partial edits (e.g. notify_physician=true with no status change)
    update the in-memory mock only — they aren't audit-worthy by themselves.
    """
    if not is_mock_pharmapi():
        raise HTTPException(
            status_code=501,
            detail="Live flag/patch not yet wired to ΗΔΥΚΑ.",
        )

    rx = MOCK_PRESCRIPTIONS.get(rx_id)
    if not rx:
        raise HTTPException(status_code=404, detail=f"Prescription {rx_id} not found")

    flagging = (patch.status or "").upper() == PrescriptionStatus.FLAGGED
    log_id = None

    if flagging:
        snapshot = [dict(c) for c in rx.get("safetyChecks", [])]
        ip, ua = _client_meta(request)
        log = await record_prescription_action(
            session,
            action_type=ActionType.FLAG,
            rx=rx,
            safety_checks=snapshot,
            pharmacist_email=current["email"],
            pharmapi_exec_ref=None,
            discrepancy_type=patch.discrepancy_type,
            notes=patch.notes,
            info_provided=None,
            delivery_method=None,
            ip_address=ip,
            user_agent=ua,
        )
        log_id = str(log.id)

    if patch.status is not None:
        rx["status"] = patch.status.upper()
    if patch.discrepancy_type is not None:
        rx["discrepancyType"] = patch.discrepancy_type
    if patch.notes is not None:
        rx["flagNotes"] = patch.notes
    if patch.notify_physician is not None:
        rx["notifyPhysician"] = bool(patch.notify_physician)

    return PatchResponse(
        success=True,
        rxId=rx_id,
        status=rx["status"],
        discrepancyType=rx.get("discrepancyType"),
        notes=rx.get("flagNotes"),
        notifyPhysician=rx.get("notifyPhysician"),
        documentationLogId=log_id,
    )
