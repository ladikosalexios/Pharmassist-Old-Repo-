"""B2B /v1 ADR report service — DB-backed, location-scoped.

State machine (mirrors B2C next_status):
  PENDING_REVIEW → ESCALATED → EOF_REPORTED → CLOSED
EOF_REPORTED is a tracked label only; PharmAssist does NOT transmit to ΕΟΦ.
All transitions record a B2bAdrEvent row in the same DB transaction.

Mock fixtures live in services/v1_mock.py (MOCK_V1_ADR_REPORTS) and share
the exact same response shape as the live path.
"""

from datetime import UTC, date, datetime
from uuid import UUID

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import AdrStatus
from app.db.models.b2b_adr_event import B2bAdrEvent
from app.db.models.b2b_adr_report import B2bAdrReport
from app.routers.v1.errors import V1Error

# ── vocabulary ────────────────────────────────────────────────────────────────

_TRANSITIONS: dict[str, str] = {
    AdrStatus.PENDING_REVIEW: AdrStatus.ESCALATED,
    AdrStatus.ESCALATED: AdrStatus.EOF_REPORTED,
    AdrStatus.EOF_REPORTED: AdrStatus.CLOSED,
}


def next_status(current: str) -> str | None:
    """Return the valid next status, or None if CLOSED (terminal)."""
    return _TRANSITIONS.get(current)


# ── response shaping ──────────────────────────────────────────────────────────


def _report_to_dict(r: B2bAdrReport) -> dict:
    return {
        "id": str(r.id),
        "locationId": str(r.location_id),
        "patientAmka": r.patient_amka,
        "patientName": r.patient_name,
        "rxId": r.rx_id,
        "medicineBarcode": r.medicine_barcode,
        "medicineName": r.medicine_name,
        "atcCode": r.atc_code,
        "symptomDescription": r.symptom_description,
        "onsetTiming": r.onset_timing,
        "severity": r.severity,
        "causality": r.causality,
        "status": r.status,
        "eofReportRef": r.eof_report_ref,
        "reportedAt": r.reported_at.isoformat(),
        "createdAt": r.created_at.isoformat(),
    }


def _event_to_dict(e: B2bAdrEvent) -> dict:
    return {
        "id": str(e.id),
        "eventType": e.event_type,
        "fromStatus": e.from_status,
        "toStatus": e.to_status,
        "notes": e.notes,
        "occurredAt": e.occurred_at.isoformat(),
    }


# ── write operations ──────────────────────────────────────────────────────────


async def create_report(
    session: AsyncSession,
    *,
    location_id: UUID,
    api_key_id: UUID | None,
    patient_amka: str | None,
    patient_name: str | None,
    rx_id: str | None,
    medicine_barcode: str | None,
    medicine_name: str | None,
    atc_code: str | None,
    symptom_description: str,
    onset_timing: str | None,
    severity: str | None,
    causality: str | None,
    eof_report_ref: str | None,
) -> dict:
    report = B2bAdrReport(
        location_id=location_id,
        created_via_api_key_id=api_key_id,
        patient_amka=patient_amka,
        patient_name=patient_name,
        rx_id=rx_id,
        medicine_barcode=medicine_barcode,
        medicine_name=medicine_name,
        atc_code=atc_code,
        symptom_description=symptom_description,
        onset_timing=onset_timing,
        severity=severity,
        causality=causality,
        status=AdrStatus.PENDING_REVIEW,
        eof_report_ref=eof_report_ref,
    )
    session.add(report)
    await session.flush()

    session.add(
        B2bAdrEvent(
            adr_id=report.id,
            actor_api_key_id=api_key_id,
            event_type="REPORT_CREATED",
            from_status=None,
            to_status=AdrStatus.PENDING_REVIEW,
        )
    )
    await session.commit()
    await session.refresh(report)
    return _report_to_dict(report)


async def transition_report(
    session: AsyncSession,
    *,
    location_id: UUID,
    report_id: UUID,
    api_key_id: UUID | None,
    notes: str | None,
) -> dict:
    report = await _get_owned(session, location_id, report_id)
    target = next_status(report.status)
    if target is None:
        raise V1Error(
            "illegal_transition",
            409,
            f"ADR report is in terminal status '{report.status}' — no further transitions",
        )
    old_status = report.status
    report.status = target
    session.add(
        B2bAdrEvent(
            adr_id=report.id,
            actor_api_key_id=api_key_id,
            event_type="STATUS_CHANGED",
            from_status=old_status,
            to_status=target,
            notes=notes,
        )
    )
    await session.commit()
    await session.refresh(report)
    return _report_to_dict(report)


# ── read operations ───────────────────────────────────────────────────────────


async def get_report(
    session: AsyncSession,
    location_id: UUID,
    report_id: UUID,
) -> dict:
    report = await _get_owned(session, location_id, report_id)
    await session.refresh(report, ["events"])
    d = _report_to_dict(report)
    d["events"] = [_event_to_dict(e) for e in report.events]
    return d


async def list_reports(
    session: AsyncSession,
    *,
    location_id: UUID,
    amka: str | None,
    atc_code: str | None,
    medicine_barcode: str | None,
    status: str | None,
    from_date: date | None,
    to_date: date | None,
    page: int,
    size: int,
) -> dict:
    filters = [B2bAdrReport.location_id == location_id]
    if amka:
        filters.append(B2bAdrReport.patient_amka == amka)
    if atc_code:
        filters.append(B2bAdrReport.atc_code == atc_code)
    if medicine_barcode:
        filters.append(B2bAdrReport.medicine_barcode == medicine_barcode)
    if status:
        filters.append(B2bAdrReport.status == status)
    if from_date:
        filters.append(B2bAdrReport.reported_at >= from_date)
    if to_date:
        # inclusive: treat to_date as end-of-day
        to_dt = datetime(to_date.year, to_date.month, to_date.day, 23, 59, 59, tzinfo=UTC)
        filters.append(B2bAdrReport.reported_at <= to_dt)

    from sqlalchemy import func

    total_q = await session.scalar(
        select(func.count()).select_from(B2bAdrReport).where(and_(*filters))
    )
    total = total_q or 0

    rows_q = (
        select(B2bAdrReport)
        .where(and_(*filters))
        .order_by(B2bAdrReport.reported_at.desc())
        .offset(page * size)
        .limit(size)
    )
    result = await session.execute(rows_q)
    reports = result.scalars().all()

    total_pages = max(1, (total + size - 1) // size)
    return {
        "items": [_report_to_dict(r) for r in reports],
        "page": page,
        "size": size,
        "total": total,
        "totalPages": total_pages,
        "lastPage": page >= total_pages - 1,
    }


# ── internal helpers ──────────────────────────────────────────────────────────


async def _get_owned(session: AsyncSession, location_id: UUID, report_id: UUID) -> B2bAdrReport:
    """Fetch a report that belongs to this location — 404 if absent or not owned."""
    result = await session.execute(
        select(B2bAdrReport).where(
            B2bAdrReport.id == report_id,
            B2bAdrReport.location_id == location_id,
        )
    )
    report = result.scalar_one_or_none()
    if report is None:
        raise V1Error("not_found", 404, "ADR report not found")
    return report
