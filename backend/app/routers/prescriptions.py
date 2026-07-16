"""Prescription queue + per-rx detail and partial update (flag triage).

Retrieval-only: dispensing happens in the pharmacist's own software
(parasitic-first — docs/agent-vs-spa-surface-split.md). The eDispensation /
HMVS execution path was removed at tag ``hmvs-certified``.

Bridge pattern
--------------
Set PHARMAPI_MOCK=false (env var) to switch from mock in-memory data to live
ΗΔΥΚΑ calls. Everything downstream (safety checks, patient lookup) is
identical in both modes.

  PHARMAPI_MOCK=true  (default)  → MOCK_PRESCRIPTIONS + MOCK_QUEUE_BASE
  PHARMAPI_MOCK=false            → pharmapi_get_prescription() by barcode,
                                   falling back to pharmapi_search_prescriptions()

Resolve path: a single prescription is resolved by barcode via
``pharmapi_get_prescription`` (GET /prescriptions/get/{barcode}), which returns
the source CDA and — unlike /search — surfaces PAPERLESS (άυλη) prescriptions.
``/search`` remains the fallback (and still backs the /next + list queues).

Order matters: ``/next`` is declared *before* ``/{rx_id}`` so FastAPI matches
the fixed path before the catch-all.
"""

import ipaddress
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.utils.environment import is_mock_pharmapi

from ..constants import ActionType, PrescriptionStatus
from ..db.session import get_session
from ..deps import get_current_user
from ..schemas.prescriptions import PatchResponse, PrescriptionPatch
from ..services.documentation import record_prescription_action
from ..services.drug_catalog import atc_codes_for_barcodes
from ..services.pharmacy import find_pharmacy_by_name
from ..services.pharmapi import pharmapi_get_prescription, pharmapi_search_prescriptions
from ..services.prescriptions import MOCK_PRESCRIPTIONS, MOCK_QUEUE_BASE
from ..services.safety_engine import checks_for_prescription, live_rx_to_engine_shape
from ..services.scan_log import fire_scan_record

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
    mode the incoming drug's ATC is resolved from drug_catalog; co-medication
    interactions (section 1) and intolerance contraindications (section 2) are
    revived via services/substance_resolver, which maps the commercialName /
    activeSubstance that Pharmapi returns (no barcode) to an ATC — see
    safety_engine.py.
    """
    if is_mock_pharmapi():
        rx = MOCK_PRESCRIPTIONS.get(rx_id)
        if not rx:
            raise HTTPException(status_code=404, detail=f"Prescription {rx_id} not found")
        pharmacy = await find_pharmacy_by_name(session, current["pharmacy"])
        if pharmacy is None:
            raise HTTPException(status_code=400, detail="Pharmacy not found for current user")
        payload = await checks_for_prescription(session, rx_id, rx, pharmacy.id)
        result = {**rx, "safetyChecks": [c.model_dump(by_alias=True) for c in payload.checks]}
        fire_scan_record(
            pharmacy_id=pharmacy.id,
            pharmacist_id=uuid.UUID(current["pharmacist_id"]),
            barcode=rx_id,
            rx=result,
            source="mock",
        )
        return result

    # Live mode: resolve by barcode via GET /prescriptions/get/{barcode} (the
    # source CDA — surfaces paperless άυλη prescriptions), falling back to
    # /search. Then enrich with safety checks.
    pharmacy = await find_pharmacy_by_name(session, current["pharmacy"])
    if pharmacy is None:
        raise HTTPException(status_code=400, detail="Pharmacy not found for current user")
    rx = await _fetch_live_rx(rx_id, pharmacy, request)
    if rx is None:
        raise HTTPException(status_code=404, detail=f"Prescription {rx_id} not found")

    # Resolve ATCs for EVERY therapy line in one query so multi-medicine
    # prescriptions get per-line safety evaluation (sibling-line interactions
    # fire in the engine) and the UI can render one card per medicine. Falls
    # back to the single medicineBarcode when the source had no line list.
    lines = rx.get("therapyLines") or []
    line_barcodes = [ln.get("medicineBarcode") for ln in lines if ln.get("medicineBarcode")]
    medicine_barcode = rx.get("medicineBarcode")
    barcodes = line_barcodes or ([medicine_barcode] if medicine_barcode else [])
    atc_map = await atc_codes_for_barcodes(session, barcodes)
    atc = atc_map.get(medicine_barcode) if medicine_barcode else None

    shaped_rx = live_rx_to_engine_shape(rx, atc)
    if lines:
        rx["medications"] = [
            {
                "drugName": ln.get("name"),
                "atcCode": atc_map.get(ln.get("medicineBarcode")),
                "nhrn": ln.get("medicineBarcode"),
            }
            for ln in lines
        ]
        shaped_rx["medications"] = [
            {"atcCode": m["atcCode"]} for m in rx["medications"] if m["atcCode"]
        ]
    payload = await checks_for_prescription(session, shaped_rx["rxId"], shaped_rx, pharmacy.id)
    result = {**rx, "safetyChecks": [c.model_dump(by_alias=True) for c in payload.checks]}
    fire_scan_record(
        pharmacy_id=pharmacy.id,
        pharmacist_id=uuid.UUID(current["pharmacist_id"]),
        barcode=rx_id,
        rx=result,
        source="live",
    )
    return result


async def _fetch_live_rx(rx_id: str, pharmacy, request: Request) -> dict | None:
    """Resolve ONE live prescription by barcode (for the detail view).

    Primary: ``pharmapi_get_prescription`` (GET /prescriptions/get/{barcode}) —
    the source CDA, which surfaces PAPERLESS (άυλη) prescriptions and carries the
    real per-line therapy ids. On 404 fall back to ``/search`` (legacy printed /
    already-associated rows). Returns the search-shaped rx dict, or None.
    """
    ip, _ = _client_meta(request)
    # X-DOCTOR-IP per spec (pharmacist external IP). Under TestClient there is no
    # real client; fall back so pharmapi_get_prescription's header guard passes.
    # PROD P1: behind a reverse proxy ``request.client.host`` is the proxy IP, not
    # the pharmacist's. Wire X-Forwarded-For (Caddy/Nginx) before prod — sending
    # the proxy IP to ΗΔΥΚΑ misattributes the call on the regulator-facing log.
    # See docs/OPEN-ISSUES.md (X-DOCTOR-IP).
    doctor_ip = ip or "0.0.0.0"
    primary_exc: HTTPException | None = None
    try:
        return await pharmapi_get_prescription(
            barcode=rx_id, pharmacy_id=pharmacy.pharmapi_unit_id, doctor_ip=doctor_ip
        )
    except HTTPException as exc:
        # 404 → plain not-found; 422 → a domain refusal from ΗΔΥΚΑ with a
        # display-ready Greek description (non-ΕΟΠΥΥ patient, already executed,
        # …). Both get a /search fallback shot; anything else is a real fault.
        if exc.status_code not in (404, 422):
            raise
        primary_exc = exc
    results = await pharmapi_search_prescriptions(barcode=rx_id)
    if results:
        return results[0]
    if primary_exc is not None and primary_exc.status_code == 422:
        # Nothing found via search either — surface the upstream refusal
        # verbatim rather than a misleading "not found".
        raise primary_exc
    return None


# ── Actions (flag / patch) ───────────────────────────────────────────────────
# Flag: PATCH with status=FLAGGED writes a documentation_logs row only — no
# ΗΔΥΚΑ call because flagging is internal triage, not a dispense.


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
