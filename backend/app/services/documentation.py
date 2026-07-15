"""Documentation & Legal Log: filter / stats / CSV response helpers.

PDF rendering lives in ``services.pdf`` (separate so the optional reportlab
dependency stays isolated).
"""

import asyncio
import csv
import hashlib
import io
from datetime import UTC, datetime, timedelta
from typing import Literal

from fastapi import HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from ..constants import DeliveryMethod
from ..db.models.documentation_log import DocumentationLog
from ..db.models.pharmacist import Pharmacist
from ..db.models.pharmacist_pharmacy import PharmacistPharmacy
from .audit import _background_tasks, log_documentation_action
from .security import SECRET_KEY


def _build_filters(query: str | None, method: str | None) -> list:
    clauses = []
    if query:
        q = f"%{query.lower().strip()}%"
        clauses.append(
            or_(
                func.lower(DocumentationLog.patient_name).like(q),
                func.lower(DocumentationLog.prescription_barcode).like(q),
                func.lower(DocumentationLog.medicine_name).like(q),
            )
        )
    if method and method.upper() != "ALL":
        clauses.append(DocumentationLog.delivery_method == method.upper())
    return clauses


async def filter_records(
    session: AsyncSession,
    query: str | None,
    method: str | None,
    limit: int | None = None,
    offset: int | None = None,
) -> list:
    stmt = (
        select(DocumentationLog)
        .options(joinedload(DocumentationLog.pharmacist))
        .where(*_build_filters(query, method))
        .order_by(DocumentationLog.dispensed_at.desc())
    )
    if offset is not None:
        stmt = stmt.offset(offset)
    if limit is not None:
        stmt = stmt.limit(limit)
    return list((await session.execute(stmt)).scalars().all())


async def count_records(session: AsyncSession, query: str | None, method: str | None) -> int:
    stmt = select(func.count()).select_from(DocumentationLog).where(*_build_filters(query, method))
    return (await session.execute(stmt)).scalar_one()


def get_documentation_log_dict(doc_log: DocumentationLog) -> dict:
    return {
        "id": doc_log.id,
        "rxId": doc_log.prescription_barcode,
        "patientName": doc_log.patient_name,
        "drugName": doc_log.medicine_name,
        "setting": None,
        "deliveryMethod": doc_log.delivery_method,
        "language": doc_log.language,
        "informationProvided": doc_log.info_provided,
        "pharmacistName": doc_log.pharmacist.full_name,
        "pharmacistLicense": doc_log.pharmacist.eof_licence_no,
        "signatureConfirmed": bool(doc_log.pharmacist_signature),
        "dispensedAt": doc_log.dispensed_at.isoformat(),
        "exportedAt": doc_log.exported_at.isoformat() if doc_log.exported_at else None,
    }


async def stats(session: AsyncSession) -> dict:
    # Method breakdown (drives the legend) + date-windowed counts for the
    # History stats strip. Frontend keys: history.statToday / statWeek /
    # statMonth / statTotal.
    rows = (
        await session.execute(
            select(DocumentationLog.delivery_method, func.count().label("n")).group_by(
                DocumentationLog.delivery_method
            )
        )
    ).all()
    total = sum(r.n for r in rows)
    s = {"total": total, "print": 0, "digital": 0, "both": 0}
    for r in rows:
        m = (r.delivery_method or "").upper()
        if m == DeliveryMethod.PRINT:
            s["print"] = r.n
        elif m == DeliveryMethod.DIGITAL:
            s["digital"] = r.n
        elif m == DeliveryMethod.BOTH:
            s["both"] = r.n

    # Date-windowed counts (UTC): today = since 00:00, this week = since
    # Monday 00:00, this month = since the 1st 00:00.
    now = datetime.now(UTC)
    start_today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    start_week = start_today - timedelta(days=now.weekday())
    start_month = start_today.replace(day=1)

    async def _count_since(start: datetime) -> int:
        return (
            await session.execute(
                select(func.count())
                .select_from(DocumentationLog)
                .where(DocumentationLog.dispensed_at >= start)
            )
        ).scalar_one()

    s["today"] = await _count_since(start_today)
    s["thisWeek"] = await _count_since(start_week)
    s["thisMonth"] = await _count_since(start_month)
    return s


def csv_response(rows: list, filename: str) -> StreamingResponse:
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(
        [
            "ID",
            "Dispensed At",
            "Rx Code",
            "Patient",
            "Drug",
            "Setting",
            "Delivery Method",
            "Language",
            "Information Provided",
            "Pharmacist",
            "Licence",
            "Signature Confirmed",
        ]
    )
    for d in rows:
        writer.writerow(
            [
                d["id"],
                d["dispensedAt"],
                d["rxId"],
                d["patientName"],
                d["drugName"],
                d["setting"],
                d["deliveryMethod"],
                d["language"],
                d["informationProvided"],
                d["pharmacistName"],
                d["pharmacistLicense"],
                "yes" if d["signatureConfirmed"] else "no",
            ]
        )
    out.seek(0)
    return StreamingResponse(
        iter([out.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


async def mark_exported(session: AsyncSession, rows: list) -> str:
    """Stamp exported_at on each record (immutability marker) and commit."""
    ts = datetime.now(UTC)
    for row in rows:
        if row.exported_at is None:
            row.exported_at = ts
    await session.commit()
    return ts.isoformat()


# ── Prescription action audit (DB-backed) ─────────────────────────────────────


async def _resolve_pharmacist_default_pharmacy(session: AsyncSession, email: str) -> tuple:
    """Look up (pharmacist_id, pharmacy_id, eof_licence_no) for a JWT-authenticated user.

    Joins pharmacists → pharmacist_pharmacies on the default link. The seed
    script always creates exactly one default link per pharmacist; if a
    pharmacist somehow has none, that's a data-integrity bug — fail loud.
    """
    stmt = (
        select(
            Pharmacist.id,
            Pharmacist.eof_licence_no,
            PharmacistPharmacy.pharmacy_id,
        )
        .join(PharmacistPharmacy, PharmacistPharmacy.pharmacist_id == Pharmacist.id)
        .where(func.lower(Pharmacist.email) == email.lower())
        .where(PharmacistPharmacy.is_default.is_(True))
    )
    row = (await session.execute(stmt)).first()
    if not row:
        raise HTTPException(
            status_code=401,
            detail=f"No default-pharmacy link for {email}. Run scripts/seed.py.",
        )
    return row[0], row[2], row[1]


def _signature(pharmacist_id, barcode: str, dispensed_at: datetime) -> str:
    payload = f"{pharmacist_id}{barcode}{dispensed_at.isoformat()}{SECRET_KEY}"
    return hashlib.sha256(payload.encode()).hexdigest()


async def record_prescription_action(
    session: AsyncSession,
    *,
    action_type: Literal["APPROVE", "FLAG"],
    rx: dict,
    safety_checks: list,
    pharmacist_email: str,
    pharmapi_exec_ref: str | None,
    discrepancy_type: str | None,
    notes: str | None,
    info_provided: str | None,
    delivery_method: str | None,
    ip_address: str | None,
    user_agent: str | None,
) -> DocumentationLog:
    """Persist a documentation_logs row for a prescription action.

    Single write path, called by PATCH /prescriptions/{id} when status flips
    to FLAGGED. Computes the pharmacist_signature documented on the model and
    commits.
    """
    pharmacist_id, pharmacy_id, _ = await _resolve_pharmacist_default_pharmacy(
        session, pharmacist_email
    )

    dispensed_at = datetime.now(UTC)
    log = DocumentationLog(
        pharmacist_id=pharmacist_id,
        pharmacy_id=pharmacy_id,
        action_type=action_type,
        prescription_barcode=rx["rxId"],
        patient_amka=rx["patient"]["amka"],
        patient_name=rx["patient"]["name"],
        medicine_name=rx["medication"]["drugName"],
        info_provided=info_provided,
        delivery_method=delivery_method,
        discrepancy_type=discrepancy_type,
        notes=notes,
        safety_check_snapshot=safety_checks,
        dispensed_at=dispensed_at,
        pharmapi_exec_ref=pharmapi_exec_ref,
        pharmacist_signature=_signature(pharmacist_id, rx["rxId"], dispensed_at),
        ip_address=ip_address,
        user_agent=user_agent,
    )
    session.add(log)
    await session.commit()
    await session.refresh(log)
    task = asyncio.create_task(
        log_documentation_action(
            pharmacist_id=pharmacist_id,
            pharmacy_id=pharmacy_id,
            action=f"PRESCRIPTION_{action_type}D",
            resource_id=rx["rxId"],
        )
    )
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
    return log
