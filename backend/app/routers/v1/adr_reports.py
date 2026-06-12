"""B2B /v1 ADR reports — POST create, GET list (with filters), GET by id, POST transition.

Mock/live parity: PHARMAPI_MOCK=true serves fixtures from services/v1_mock.py
with the same shape as DB rows.  Every endpoint is gated behind require_tier("clinical").

EOF_REPORTED is a tracked status label — this endpoint does NOT transmit to ΕΟΦ.
"""

import copy
import uuid
from datetime import date

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import AdrCausality, AdrSeverity, AdrStatus
from app.db.session import get_session
from app.services import b2b_adr
from app.services.v1_mock import MOCK_V1_ADR_REPORTS
from app.utils.environment import is_mock_pharmapi

from .deps import ApiContext, require_tier
from .errors import V1Error

router = APIRouter(prefix="/adr-reports", tags=["b2b-v1"])

_VALID_SEVERITIES = {AdrSeverity.MILD, AdrSeverity.MODERATE, AdrSeverity.SEVERE}
_VALID_CAUSALITIES = {
    AdrCausality.CERTAIN,
    AdrCausality.PROBABLE,
    AdrCausality.POSSIBLE,
    AdrCausality.UNLIKELY,
}
_VALID_STATUSES = {
    AdrStatus.PENDING_REVIEW,
    AdrStatus.ESCALATED,
    AdrStatus.EOF_REPORTED,
    AdrStatus.CLOSED,
}

# In-memory mock store — a mutable copy so POST/transition tests don't mutate the
# canonical fixture list; reset between test sessions by re-importing the module.
_MOCK_STORE: list[dict] = copy.deepcopy(MOCK_V1_ADR_REPORTS)


# ── request schemas ───────────────────────────────────────────────────────────


class AdrReportCreate(BaseModel):
    patientAmka: str | None = None
    patientName: str | None = None
    rxId: str | None = None
    medicineBarcode: str | None = None
    medicineName: str | None = None
    atcCode: str | None = None
    symptomDescription: str
    onsetTiming: str | None = None
    severity: str | None = None
    causality: str | None = None
    eofReportRef: str | None = None


class AdrTransitionRequest(BaseModel):
    notes: str | None = None


# ── helpers ───────────────────────────────────────────────────────────────────


def _validate_severity(v: str | None) -> None:
    if v is not None and v not in _VALID_SEVERITIES:
        raise V1Error(
            "validation_failed", 422, f"severity must be one of {sorted(_VALID_SEVERITIES)}"
        )


def _validate_causality(v: str | None) -> None:
    if v is not None and v not in _VALID_CAUSALITIES:
        raise V1Error(
            "validation_failed", 422, f"causality must be one of {sorted(_VALID_CAUSALITIES)}"
        )


def _validate_status_filter(v: str | None) -> None:
    if v is not None and v not in _VALID_STATUSES:
        raise V1Error("validation_failed", 422, f"status must be one of {sorted(_VALID_STATUSES)}")


def _mock_list(
    *,
    location_id: str,
    amka: str | None,
    atc_code: str | None,
    medicine_barcode: str | None,
    status: str | None,
    from_date: date | None,
    to_date: date | None,
    page: int,
    size: int,
) -> dict:
    items = [r for r in _MOCK_STORE if r["locationId"] == location_id]
    if amka:
        items = [r for r in items if r.get("patientAmka") == amka]
    if atc_code:
        items = [r for r in items if r.get("atcCode") == atc_code]
    if medicine_barcode:
        items = [r for r in items if r.get("medicineBarcode") == medicine_barcode]
    if status:
        items = [r for r in items if r.get("status") == status]
    if from_date:
        items = [r for r in items if r["reportedAt"] >= from_date.isoformat()]
    if to_date:
        items = [r for r in items if r["reportedAt"][:10] <= to_date.isoformat()]
    items.sort(key=lambda r: r["reportedAt"], reverse=True)
    total = len(items)
    total_pages = max(1, (total + size - 1) // size)
    return {
        "items": items[page * size : (page + 1) * size],
        "page": page,
        "size": size,
        "total": total,
        "totalPages": total_pages,
        "lastPage": page >= total_pages - 1,
    }


def _mock_get(location_id: str, report_id: str) -> dict:
    for r in _MOCK_STORE:
        if r["id"] == report_id and r["locationId"] == location_id:
            return dict(r, events=[])
    raise V1Error("not_found", 404, "ADR report not found")


# ── endpoints ─────────────────────────────────────────────────────────────────


@router.post("", status_code=201)
async def create_adr_report(
    body: AdrReportCreate,
    ctx: ApiContext = Depends(require_tier("clinical")),  # noqa: B008
    session: AsyncSession = Depends(get_session),
):
    """Create a new ADR report for this location.  Status starts at PENDING_REVIEW.

    EOF_REPORTED is reachable via /transition; PharmAssist does NOT submit to ΕΟΦ.
    """
    _validate_severity(body.severity)
    _validate_causality(body.causality)

    if is_mock_pharmapi():
        record = {
            "id": str(uuid.uuid4()),
            "locationId": str(ctx.location_id),
            "patientAmka": body.patientAmka,
            "patientName": body.patientName,
            "rxId": body.rxId,
            "medicineBarcode": body.medicineBarcode,
            "medicineName": body.medicineName,
            "atcCode": body.atcCode,
            "symptomDescription": body.symptomDescription,
            "onsetTiming": body.onsetTiming,
            "severity": body.severity,
            "causality": body.causality,
            "status": AdrStatus.PENDING_REVIEW,
            "eofReportRef": body.eofReportRef,
            "reportedAt": "2026-06-11T12:00:00+00:00",
            "createdAt": "2026-06-11T12:00:00+00:00",
        }
        _MOCK_STORE.append(record)
        return record

    return await b2b_adr.create_report(
        session,
        location_id=ctx.location_id,
        api_key_id=ctx.api_key_id,
        patient_amka=body.patientAmka,
        patient_name=body.patientName,
        rx_id=body.rxId,
        medicine_barcode=body.medicineBarcode,
        medicine_name=body.medicineName,
        atc_code=body.atcCode,
        symptom_description=body.symptomDescription,
        onset_timing=body.onsetTiming,
        severity=body.severity,
        causality=body.causality,
        eof_report_ref=body.eofReportRef,
    )


@router.get("")
async def list_adr_reports(
    amka: str | None = Query(None),
    atc: str | None = Query(None, description="Filter by ATC code"),
    barcode: str | None = Query(None, description="Filter by medicine barcode"),
    status: str | None = Query(None),
    from_: date | None = Query(None, alias="from"),
    to: date | None = Query(None),
    page: int = Query(0, ge=0),
    size: int = Query(20, ge=1, le=100),
    ctx: ApiContext = Depends(require_tier("clinical")),  # noqa: B008
    session: AsyncSession = Depends(get_session),
):
    """List ADR reports for this location with optional filters.

    Filters: amka, atc (ATC code), barcode (medicine barcode), status, from (date), to (date).
    Sorted by reportedAt descending. Paginated.
    """
    _validate_status_filter(status)

    if is_mock_pharmapi():
        return _mock_list(
            location_id=str(ctx.location_id),
            amka=amka,
            atc_code=atc,
            medicine_barcode=barcode,
            status=status,
            from_date=from_,
            to_date=to,
            page=page,
            size=size,
        )

    return await b2b_adr.list_reports(
        session,
        location_id=ctx.location_id,
        amka=amka,
        atc_code=atc,
        medicine_barcode=barcode,
        status=status,
        from_date=from_,
        to_date=to,
        page=page,
        size=size,
    )


@router.get("/{report_id}")
async def get_adr_report(
    report_id: uuid.UUID,
    ctx: ApiContext = Depends(require_tier("clinical")),  # noqa: B008
    session: AsyncSession = Depends(get_session),
):
    """Fetch a single ADR report (with event history).  404 if not owned by this location."""
    if is_mock_pharmapi():
        return _mock_get(str(ctx.location_id), str(report_id))
    return await b2b_adr.get_report(session, ctx.location_id, report_id)


@router.post("/{report_id}/transition")
async def transition_adr_report(
    report_id: uuid.UUID,
    body: AdrTransitionRequest,
    ctx: ApiContext = Depends(require_tier("clinical")),  # noqa: B008
    session: AsyncSession = Depends(get_session),
):
    """Advance the ADR report to the next status.

    Transitions: PENDING_REVIEW → ESCALATED → EOF_REPORTED → CLOSED.
    CLOSED is terminal — transitioning from it returns 409 illegal_transition.
    EOF_REPORTED means the report is marked; PharmAssist does NOT submit to ΕΟΦ.
    """
    if is_mock_pharmapi():
        report = _mock_get(str(ctx.location_id), str(report_id))
        target = b2b_adr.next_status(report["status"])
        if target is None:
            raise V1Error(
                "illegal_transition",
                409,
                f"ADR report is in terminal status '{report['status']}' — no further transitions",
            )
        report["status"] = target
        # Update in-place in the mock store
        for r in _MOCK_STORE:
            if r["id"] == report["id"]:
                r["status"] = target
        return report

    return await b2b_adr.transition_report(
        session,
        location_id=ctx.location_id,
        report_id=report_id,
        api_key_id=ctx.api_key_id,
        notes=body.notes,
    )
