"""Prescription queue + per-rx detail, approval, and partial update.

Bridge pattern
--------------
Set PHARMAPI_MOCK=false (env var) to switch from mock in-memory data to live
ΗΔΥΚΑ calls. Everything downstream (safety checks, patient lookup, dispensing
log) is identical in both modes.

  PHARMAPI_MOCK=true  (default)  → MOCK_PRESCRIPTIONS + MOCK_QUEUE_BASE
  PHARMAPI_MOCK=false            → pharmapi_get_prescription() by barcode,
                                   falling back to pharmapi_search_prescriptions()

Resolve path: a single prescription is resolved by barcode via
``pharmapi_get_prescription`` (GET /prescriptions/get/{barcode}), which returns
the source CDA and — unlike /search — surfaces PAPERLESS (άυλη) prescriptions.
``/search`` remains the fallback (and still backs the /next + list queues).

Order matters: ``/next`` is declared *before* ``/{rx_id}`` so FastAPI matches
the fixed path before the catch-all. Same reason ``/{rx_id}/approve`` comes
before the bare ``/{rx_id}``.
"""

import ipaddress
import logging
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.utils.environment import is_mock_pharmapi

from ..constants import ActionType, DeliveryMethod, PrescriptionStatus
from ..db.models.dispense_log import DispenseLog
from ..db.session import get_session
from ..deps import get_current_user
from ..schemas.prescriptions import (
    ApproveRequest,
    ApproveResponse,
    DispensePack,
    PatchResponse,
    PrescriptionPatch,
)
from ..services.cda import DispenseItem, build_dispense_cda
from ..services.documentation import record_prescription_action
from ..services.drug_catalog import atc_codes_for_barcodes
from ..services.pharmacy import find_pharmacy_by_name
from ..services.pharmapi import (
    pharmapi_dispense,
    pharmapi_get_prescription,
    pharmapi_search_prescriptions,
)
from ..services.prescriptions import MOCK_PRESCRIPTIONS, MOCK_QUEUE_BASE
from ..services.safety_engine import checks_for_prescription, live_rx_to_engine_shape

logger = logging.getLogger(__name__)
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

    In live mode: drug name (medication) and prescriber are mapped from the
    Pharmapi search response (medicines[0].name and doctorName respectively).
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
    request: Request,
    current: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """
    Return full prescription data for the verification UI.
    In live mode, rx_id is the ΗΔΥΚΑ barcode.

    Both modes run checks_for_prescription and attach safetyChecks. In live
    mode the incoming drug's ATC is resolved from drug_catalog; interaction
    checks (section 1) don't fire because Pharmapi history lacks medicine
    barcodes — see safety_engine.py for the full gap description.
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

    # Live mode: resolve by barcode via GET /prescriptions/get/{barcode} (the
    # source CDA — surfaces paperless άυλη prescriptions), falling back to
    # /search. Then enrich with safety checks.
    pharmacy = await find_pharmacy_by_name(session, current["pharmacy"])
    if pharmacy is None:
        raise HTTPException(status_code=400, detail="Pharmacy not found for current user")
    rx = await _fetch_live_rx(rx_id, pharmacy, request)
    if rx is None:
        raise HTTPException(status_code=404, detail=f"Prescription {rx_id} not found")

    medicine_barcode = rx.get("medicineBarcode")
    atc_map = await atc_codes_for_barcodes(session, [medicine_barcode] if medicine_barcode else [])
    atc = atc_map.get(medicine_barcode) if medicine_barcode else None

    shaped_rx = live_rx_to_engine_shape(rx, atc)
    payload = await checks_for_prescription(session, shaped_rx["rxId"], shaped_rx, pharmacy.id)
    return {**rx, "safetyChecks": [c.model_dump(by_alias=True) for c in payload.checks]}


# ── Actions (approve / flag / patch) ────────────────────────────────────────
# Approve flow (mock + live; identical control flow, branch only at the
# pharmapi_dispense call):
#   1. resolve the rx (mock map or pharmapi search)
#   2. build the eDispensation request CDA via services.cda.build_dispense_cda
#   3. POST it via services.pharmapi.pharmapi_dispense (mock parity envelope)
#   4. on success → write dispense_log (upstream receipt audit) + a
#      documentation_logs row (counselling / legal record). Never persist
#      either row when pharmapi_dispense raises — we only audit real dispenses.
#   5. return ApproveResponse with execRef + the two log ids.
# Flag: PATCH with status=FLAGGED writes a documentation_logs row only — no
# ΗΔΥΚΑ call because flagging is internal triage, not a dispense.


def _pack_dispense_item(
    *, therapy_line_id: str, medicine_barcode: str, pack: DispensePack
) -> DispenseItem:
    """A supply line carrying real HMVS-QR data (dispense_mode=1) from a scanned
    + supplied pack — the ΕΟΦ/QR serial ΗΔΥΚΑ validates instead of a placeholder."""
    return DispenseItem(
        therapy_line_id=therapy_line_id,
        medicine_barcode=medicine_barcode,
        lot_number=pack.serial,  # HMVS QR serial is the lot when dispense_mode=1
        consent=1,
        dispense_mode=1,
        qr_product_code=pack.gtin,
        qr_batch_no=pack.batch,
        qr_expiry=pack.expiry,
        qr_code_type="GS1",
    )


def _rx_to_dispense_items(rx: dict, packs: list[DispensePack] | None = None) -> list[DispenseItem]:
    """Map a prescription dict (+ scanned packs) to DispenseItems for the CDA.

    ``therapyLines`` (from ``pharmapi_get_prescription``'s parsed source CDA)
    carries the REAL per-line therapy id (``id[@root='1.21.1']``) + medicine
    barcode, so the eDispensation echoes ΗΔΥΚΑ's own line ids.

    Pack pairing: when ``packs`` (verified+supplied HMVS packs) are supplied they
    are paired to therapy lines by index — each yields a ``dispense_mode=1`` line
    with the real GS1 GTIN/serial/batch/expiry. A line with no matching pack (or
    no packs at all, e.g. mock / pre-scan) falls back to the synthetic
    ``dispense_mode=0`` ΕΟΦ-strip placeholder so the CDA stays schema-valid.
    """
    packs = packs or []
    lines = rx.get("therapyLines") or []
    if lines:
        items: list[DispenseItem] = []
        for i, ln in enumerate(lines, start=1):
            line_id = ln.get("lineId") or f"{rx['rxId']}-L{i}"
            med_barcode = ln.get("medicineBarcode") or ""
            pack = packs[i - 1] if i - 1 < len(packs) else None
            if pack is not None:
                items.append(
                    _pack_dispense_item(
                        therapy_line_id=line_id, medicine_barcode=med_barcode, pack=pack
                    )
                )
            else:
                items.append(
                    DispenseItem(
                        therapy_line_id=line_id,
                        medicine_barcode=med_barcode,
                        lot_number="000000000000",
                        consent=1,
                        dispense_mode=0,
                    )
                )
        return items

    # Fallback (mock / no per-line list): one line from the flat dict shape.
    medication = rx.get("medication") if isinstance(rx.get("medication"), dict) else {}
    medicine_barcode = rx.get("medicineBarcode") or (medication or {}).get("nhrn") or ""
    if packs:
        return [
            _pack_dispense_item(
                therapy_line_id=f"{rx['rxId']}-L1",
                medicine_barcode=medicine_barcode,
                pack=packs[0],
            )
        ]
    return [
        DispenseItem(
            therapy_line_id=f"{rx['rxId']}-L1",
            medicine_barcode=medicine_barcode,
            lot_number="000000000000",
            consent=1,
            dispense_mode=0,
        )
    ]


async def _fetch_live_rx(rx_id: str, pharmacy, request: Request) -> dict | None:
    """Resolve ONE live prescription by barcode (shared by detail + dispense).

    Primary: ``pharmapi_get_prescription`` (GET /prescriptions/get/{barcode}) —
    the source CDA, which surfaces PAPERLESS (άυλη) prescriptions and carries the
    real per-line therapy ids. On 404 fall back to ``/search`` (legacy printed /
    already-associated rows). Returns the search-shaped rx dict, or None.
    """
    ip, _ = _client_meta(request)
    # X-DOCTOR-IP per spec (pharmacist external IP). Under TestClient there is no
    # real client; fall back so pharmapi_get_prescription's header guard passes.
    doctor_ip = ip or "0.0.0.0"
    try:
        return await pharmapi_get_prescription(
            barcode=rx_id, pharmacy_id=pharmacy.pharmapi_unit_id, doctor_ip=doctor_ip
        )
    except HTTPException as exc:
        if exc.status_code != 404:
            raise
    results = await pharmapi_search_prescriptions(barcode=rx_id)
    return results[0] if results else None


async def _resolve_rx_for_dispense(
    session: AsyncSession, rx_id: str, current: dict, pharmacy, request: Request
) -> dict:
    """Return the rx dict the dispense flow operates on.

    Mock branch: look up MOCK_PRESCRIPTIONS by rxId. Live branch: barcode-direct
    via ``_fetch_live_rx`` (GET /prescriptions/get/{barcode} → /search fallback).
    """
    if is_mock_pharmapi():
        rx = MOCK_PRESCRIPTIONS.get(rx_id)
        if not rx:
            raise HTTPException(status_code=404, detail=f"Prescription {rx_id} not found")
        return rx

    rx = await _fetch_live_rx(rx_id, pharmacy, request)
    if rx is None:
        raise HTTPException(status_code=404, detail=f"Prescription {rx_id} not found")
    return rx


async def _get_existing_dispense_log(
    session: AsyncSession, pharmacy_id, barcode: str
) -> DispenseLog | None:
    """Idempotency cache lookup: at most one row per (pharmacy_id, barcode)
    by the UNIQUE constraint, so .scalar() is correct."""
    return await session.scalar(
        select(DispenseLog).where(
            DispenseLog.pharmacy_id == pharmacy_id,
            DispenseLog.barcode == barcode,
        )
    )


def _cached_approve_response(log: DispenseLog) -> ApproveResponse:
    """Reply built from an existing dispense_logs row — no new doc-log,
    no second ΗΔΥΚΑ call. ``completedAt`` reports the *original* dispense
    time so the receipt is the truthful one, not "now"."""
    return ApproveResponse(
        success=True,
        rxId=log.barcode,
        status=PrescriptionStatus.COMPLETED,
        completedAt=log.created_at.isoformat() if log.created_at else "",
        execId=log.exec_ref,
        executionNo=log.exec_ref,
        documentationLogId=None,
        dispenseLogId=str(log.id),
        idempotent=True,
    )


@router.post("/{rx_id}/approve", response_model=ApproveResponse)
async def approve_prescription(
    rx_id: str,
    request: Request,
    body: ApproveRequest | None = None,
    current: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    x_request_id: str | None = Header(default=None, alias="X-Request-Id", max_length=128),
):
    # Resolve the pharmacy first — barcode-direct resolution needs its
    # pharmapi_unit_id for the /get/{barcode} pharmacyId query.
    pharmacy = await find_pharmacy_by_name(session, current["pharmacy"])
    if pharmacy is None:
        raise HTTPException(status_code=400, detail="Pharmacy not found for current user")

    rx = await _resolve_rx_for_dispense(session, rx_id, current, pharmacy, request)

    # ── Idempotency pre-check ─────────────────────────────────────────────────
    # A successful dispense already exists for (pharmacy, barcode) → return
    # the cached receipt verbatim. No second ΗΔΥΚΑ call, no error. The DB
    # UNIQUE on (pharmacy_id, barcode) is the real guard; this pre-check
    # avoids burning a doomed POST + Roundtrip every time the client retries.
    cached = await _get_existing_dispense_log(session, pharmacy.id, rx_id)
    if cached is not None:
        return _cached_approve_response(cached)

    # Scanned + supplied HMVS packs (if the wizard sent them) supply the real
    # ΕΟΦ/QR serial per line; absent → synthetic ΕΟΦ-strip fallback.
    packs = body.packs if body else []
    items = _rx_to_dispense_items(rx, packs)
    cda_request = build_dispense_cda(
        barcode=rx_id,
        pharmacy_unit_id=pharmacy.pharmapi_unit_id,
        items=items,
    )

    ip, ua = _client_meta(request)
    # X-DOCTOR-IP per IDIKA spec — the pharmacist's external IP. Under
    # TestClient (no real client) we fall back to a placeholder so the
    # required-header guard in pharmapi_dispense never refuses a mock call.
    doctor_ip = ip or "0.0.0.0"

    # Single seam to ΗΔΥΚΑ — mock + live return the same envelope shape.
    # If this raises, we MUST NOT persist any success log. Both writes below
    # are unreachable on failure (the exception propagates).
    envelope = await pharmapi_dispense(
        barcode=rx_id,
        cda_xml=cda_request,
        doctor_ip=doctor_ip,
    )

    # Snapshot the safety checks at action time — cast to plain dicts so
    # JSONB serialisation doesn't surprise us if upstream ever switches to
    # pydantic-ish objects.
    snapshot = [dict(c) for c in rx.get("safetyChecks", [])]

    dispense_log = DispenseLog(
        pharmacy_id=pharmacy.id,
        pharmacist_id=uuid.UUID(current["pharmacist_id"]),
        barcode=rx_id,
        exec_ref=envelope["exec_ref"],
        request_cda=cda_request.decode("utf-8"),
        response_cda=envelope.get("response_cda") or "",
        request_id=x_request_id,
    )
    session.add(dispense_log)
    try:
        await session.flush()
    except IntegrityError as exc:
        # At this point ΗΔΥΚΑ already dispensed (we have envelope["exec_ref"]).
        # Distinguish the two IntegrityError flavours so we don't mis-handle:
        #   (a) UNIQUE(pharmacy_id, barcode)  → a concurrent winner wrote the
        #       row; roll back, fetch theirs, return cached. No double dispense.
        #   (b) Anything else (FK gone, NOT NULL, check)  → bug in our caller
        #       state or schema drift; surface 502 + the upstream exec_ref so
        #       an operator can reconcile manually. Logged at error level.
        await session.rollback()
        constraint = getattr(exc.orig, "constraint_name", None) or str(exc.orig)
        is_unique_race = "uq_dispense_logs_pharmacy_id" in constraint
        if not is_unique_race:
            logger.error(
                "[dispense] non-UNIQUE IntegrityError on flush after ΗΔΥΚΑ "
                "succeeded — barcode=%s pharmacy=%s exec_ref=%s constraint=%s",
                rx_id,
                pharmacy.id,
                envelope["exec_ref"],
                constraint,
            )
            raise HTTPException(
                502,
                f"Dispense recorded upstream (execRef={envelope['exec_ref']}) "
                "but local persistence failed — manual reconciliation required",
            ) from exc
        winner = await _get_existing_dispense_log(session, pharmacy.id, rx_id)
        if winner is None:
            # UNIQUE violation reported but the winning row vanished between
            # the flush failure and our re-SELECT (DELETE between?). Log and
            # 500 so the operator notices, never silently swallow.
            logger.error(
                "[dispense] UNIQUE race winner not found — barcode=%s pharmacy=%s",
                rx_id,
                pharmacy.id,
            )
            raise HTTPException(
                500,
                "dispense_logs UNIQUE violation but no winning row found",
            ) from None
        return _cached_approve_response(winner)
    except Exception as exc:
        # ΗΔΥΚΑ already dispensed but we couldn't write the audit row. This
        # leaves an upstream side-effect with no local trail; the operator
        # needs the exec_ref to reconcile. Logged at error level (no PHI —
        # only the exec_ref and the exception class).
        await session.rollback()
        logger.error(
            "[dispense] flush failed after ΗΔΥΚΑ success — barcode=%s pharmacy=%s "
            "exec_ref=%s exc=%s",
            rx_id,
            pharmacy.id,
            envelope["exec_ref"],
            type(exc).__name__,
        )
        raise HTTPException(
            502,
            f"Dispense recorded upstream (execRef={envelope['exec_ref']}) "
            "but local persistence failed — manual reconciliation required",
        ) from exc

    doc_log = await record_prescription_action(
        session,
        action_type=ActionType.APPROVE,
        rx=rx,
        safety_checks=snapshot,
        pharmacist_email=current["email"],
        pharmapi_exec_ref=envelope["exec_ref"],
        discrepancy_type=None,
        notes=None,
        info_provided="Counselling delivered per SPC",
        delivery_method=DeliveryMethod.DIGITAL,
        ip_address=ip,
        user_agent=ua,
    )

    # completedAt comes from the upstream envelope (ΗΔΥΚΑ's effectiveTime)
    # so the fresh-response timestamp matches the cached-response timestamp
    # for the same dispense — both report the moment ΗΔΥΚΑ recorded the
    # execution, not the moment we returned the HTTP reply.
    completed_at = envelope.get("executed_at") or datetime.now(UTC).isoformat()
    if is_mock_pharmapi():
        # Reflect COMPLETED in the in-memory mock so subsequent GETs match
        # what the dispense_logs row now says.
        rx["status"] = PrescriptionStatus.COMPLETED
        rx["completedAt"] = completed_at

    return ApproveResponse(
        success=True,
        rxId=rx_id,
        status=PrescriptionStatus.COMPLETED,
        completedAt=completed_at,
        execId=envelope["exec_ref"],
        executionNo=envelope["exec_ref"],
        documentationLogId=str(doc_log.id),
        dispenseLogId=str(dispense_log.id),
        idempotent=False,
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
