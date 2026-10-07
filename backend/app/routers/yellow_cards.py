"""Local-only Yellow Card workspace: owner-scoped artifacts and atomic approval/outbox."""

import hashlib
import json
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, File, Header, HTTPException, Response, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from ..config import get_settings
from ..db.models.adr_report import AdrReport
from ..db.models.pharmacist import Pharmacist
from ..db.models.yellow_card import (
    YellowEvent,
    YellowPreview,
    YellowReport,
    YellowSignature,
    YellowSubmission,
)
from ..db.session import get_session
from ..deps import get_identity
from ..schemas.yellow_card import (
    ImportAdr,
    Medicine,
    PreviewRequest,
    Reaction,
    ReportData,
    SubmitRequest,
    UpdateReport,
)
from ..services.yellow_crypto import seal, unseal
from ..services.yellow_pdf import TEMPLATE_VERSION, normalize_signature, render_pdf


async def reporting(current: dict = Depends(get_identity)):
    if get_settings().yellow_cards_mode != "local_capture":
        raise HTTPException(403, "Η τοπική δοκιμή Κίτρινης Κάρτας δεν είναι ενεργή")
    return current


router = APIRouter(prefix="/yellow-cards", tags=["yellow-cards"], dependencies=[Depends(reporting)])


def owner(current):
    return {
        "pharmacist_id": uuid.UUID(current["pharmacist_id"]),
        "pharmacy_id": uuid.UUID(current["pharmacy_id"]),
    }


def owned(model, current):
    return select(model).where(*(getattr(model, k) == v for k, v in owner(current).items()))


async def get_owned(db, model, ident, current):
    row = await db.scalar(owned(model, current).where(model.id == ident))
    if row is None:
        raise HTTPException(404, "Η εγγραφή δεν βρέθηκε")
    return row


async def lock_owner(db, current):
    # Same lock for edits, signatures, preview and submission: no stale approval races.
    await db.scalar(
        select(Pharmacist)
        .where(Pharmacist.id == uuid.UUID(current["pharmacist_id"]))
        .with_for_update()
    )


def report_json(row):
    return {
        "id": str(row.id),
        "revision": row.revision,
        "data": json.loads(unseal(row.payload, f"report:{row.id}")),
    }


def submission_json(row):
    return {
        "id": str(row.id),
        "preview_id": str(row.preview_id),
        "status": row.status,
        "transport": row.transport,
        "approved_at": row.approved_at.isoformat(),
        "failure_code": row.failure_code,
    }


@router.get("")
async def listing(current: dict = Depends(reporting), db: AsyncSession = Depends(get_session)):
    rows = (
        await db.scalars(
            owned(YellowReport, current).order_by(YellowReport.updated_at.desc()).limit(100)
        )
    ).all()
    return [report_json(row) for row in rows]


@router.post("", status_code=201)
async def create(
    data: ReportData, current: dict = Depends(reporting), db: AsyncSession = Depends(get_session)
):
    row = YellowReport(id=uuid.uuid4(), **owner(current), revision=1)
    row.payload = seal(data.model_dump_json().encode(), f"report:{row.id}")
    db.add(row)
    await db.commit()
    return report_json(row)


@router.post("/from-adr", status_code=201)
async def from_adr(
    body: ImportAdr, current: dict = Depends(reporting), db: AsyncSession = Depends(get_session)
):
    adr = await get_owned(db, AdrReport, body.adr_id, current)
    data = ReportData(
        suspected=[Medicine(name=adr.medicine_name)],
        reactions=[Reaction(description=adr.symptom_description)],
        reporter_name=current["name"],
        reporter_email=current["email"],
    )
    # No patient name, AMKA or prescription number is imported.
    return await create(data, current, db)


@router.get("/signature")
async def current_signature(
    current: dict = Depends(reporting), db: AsyncSession = Depends(get_session)
):
    row = await db.scalar(
        owned(YellowSignature, current)
        .where(YellowSignature.active.is_(True))
        .order_by(YellowSignature.created_at.desc())
    )
    return {"id": str(row.id), "sha256": row.sha256} if row else None


@router.post("/signature", status_code=201)
async def save_signature(
    file: UploadFile = File(...),
    current: dict = Depends(reporting),
    db: AsyncSession = Depends(get_session),
):
    raw = await file.read(1_000_001)
    try:
        image = await run_in_threadpool(normalize_signature, raw)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    await lock_owner(db, current)
    for old in (
        await db.scalars(owned(YellowSignature, current).where(YellowSignature.active.is_(True)))
    ).all():
        old.active = False
    row = YellowSignature(
        id=uuid.uuid4(), **owner(current), active=True, sha256=hashlib.sha256(image).hexdigest()
    )
    row.image = seal(image, f"signature:{row.id}")
    db.add(row)
    await db.commit()
    return {"id": str(row.id), "sha256": row.sha256}


@router.get("/signature/{signature_id}/image")
async def signature_image(
    signature_id: uuid.UUID,
    current: dict = Depends(reporting),
    db: AsyncSession = Depends(get_session),
):
    row = await get_owned(db, YellowSignature, signature_id, current)
    if not row.active:
        raise HTTPException(404, "Η υπογραφή έχει αποσυρθεί")
    return Response(
        unseal(row.image, f"signature:{row.id}"),
        media_type="image/png",
        headers={"Cache-Control": "no-store"},
    )


@router.delete("/signature", status_code=204)
async def revoke_signature(
    current: dict = Depends(reporting), db: AsyncSession = Depends(get_session)
):
    await lock_owner(db, current)
    for row in (
        await db.scalars(owned(YellowSignature, current).where(YellowSignature.active.is_(True)))
    ).all():
        row.active = False
    await db.commit()


@router.get("/submissions")
async def submissions(current: dict = Depends(reporting), db: AsyncSession = Depends(get_session)):
    rows = (
        await db.scalars(
            owned(YellowSubmission, current).order_by(YellowSubmission.created_at.desc()).limit(100)
        )
    ).all()
    return [submission_json(row) for row in rows]


@router.post("/submissions", status_code=202)
async def submit(
    body: SubmitRequest,
    idempotency_key: str = Header(min_length=1, max_length=100),
    current: dict = Depends(reporting),
    db: AsyncSession = Depends(get_session),
):
    await lock_owner(db, current)
    existing = await db.scalar(
        owned(YellowSubmission, current).where(YellowSubmission.idempotency_key == idempotency_key)
    )
    if existing:
        if existing.preview_id != body.preview_id:
            raise HTTPException(409, "Το κλειδί αποστολής χρησιμοποιήθηκε ήδη")
        return submission_json(existing)
    preview = await get_owned(db, YellowPreview, body.preview_id, current)
    report = await get_owned(db, YellowReport, preview.report_id, current)
    signature = await get_owned(db, YellowSignature, preview.signature_id, current)
    if report.revision != preview.revision or not signature.active:
        raise HTTPException(409, "Η αναφορά ή η υπογραφή άλλαξε. Δημιουργήστε νέα προεπισκόπηση")
    existing = await db.scalar(
        owned(YellowSubmission, current).where(YellowSubmission.preview_id == preview.id)
    )
    if existing:
        return submission_json(existing)
    row = YellowSubmission(
        id=uuid.uuid4(),
        **owner(current),
        preview_id=preview.id,
        idempotency_key=idempotency_key,
        status="QUEUED",
        approved_at=datetime.now(UTC),
        transport="local_capture",
        approval_version="local-v1",
    )
    db.add(row)
    await db.flush()
    db.add(YellowEvent(submission_id=row.id, kind="APPROVED_AND_QUEUED"))
    await db.commit()
    return submission_json(row)


@router.post("/submissions/{submission_id}/cancel")
async def cancel(
    submission_id: uuid.UUID,
    current: dict = Depends(reporting),
    db: AsyncSession = Depends(get_session),
):
    row = await db.scalar(
        owned(YellowSubmission, current)
        .where(YellowSubmission.id == submission_id)
        .with_for_update()
    )
    if row is None:
        raise HTTPException(404, "Η αποστολή δεν βρέθηκε")
    if row.status != "QUEUED":
        raise HTTPException(409, "Η αποστολή έχει ήδη ξεκινήσει")
    row.status = "CANCELLED"
    db.add(YellowEvent(submission_id=row.id, kind="CANCELLED"))
    await db.commit()
    return submission_json(row)


@router.get("/artifacts/{preview_id}")
async def artifact(
    preview_id: uuid.UUID,
    current: dict = Depends(reporting),
    db: AsyncSession = Depends(get_session),
):
    row = await get_owned(db, YellowPreview, preview_id, current)
    return Response(
        unseal(row.pdf, f"pdf:{row.id}"),
        media_type="application/pdf",
        headers={
            "Cache-Control": "no-store",
            "Content-Disposition": 'inline; filename="yellow-card.pdf"',
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.patch("/{report_id}")
async def update(
    report_id: uuid.UUID,
    body: UpdateReport,
    current: dict = Depends(reporting),
    db: AsyncSession = Depends(get_session),
):
    await lock_owner(db, current)
    row = await get_owned(db, YellowReport, report_id, current)
    if row.revision != body.revision:
        raise HTTPException(409, "Η αναφορά άλλαξε σε άλλο παράθυρο. Φορτώστε την ξανά")
    row.revision += 1
    row.payload = seal(body.data.model_dump_json().encode(), f"report:{row.id}")
    await db.commit()
    return report_json(row)


@router.post("/{report_id}/previews", status_code=201)
async def preview(
    report_id: uuid.UUID,
    body: PreviewRequest,
    current: dict = Depends(reporting),
    db: AsyncSession = Depends(get_session),
):
    await lock_owner(db, current)
    report = await get_owned(db, YellowReport, report_id, current)
    if report.revision != body.revision:
        raise HTTPException(409, "Η αναφορά άλλαξε. Φορτώστε την ξανά")
    sig = await get_owned(db, YellowSignature, body.signature_id, current)
    if not sig.active:
        raise HTTPException(409, "Αποθηκεύστε ή επιλέξτε την τρέχουσα υπογραφή")
    data = ReportData.model_validate_json(unseal(report.payload, f"report:{report.id}"))
    missing = data.missing()
    if missing:
        raise HTTPException(422, {"missing": missing})
    row = YellowPreview(
        id=uuid.uuid4(),
        **owner(current),
        report_id=report.id,
        revision=report.revision,
        signature_id=sig.id,
        template_version=TEMPLATE_VERSION,
    )
    pdf = await run_in_threadpool(
        render_pdf, data, unseal(sig.image, f"signature:{sig.id}"), str(report.id)
    )
    row.pdf = seal(pdf, f"pdf:{row.id}")
    row.sha256 = hashlib.sha256(pdf).hexdigest()
    row.payload = seal(data.model_dump_json().encode(), f"preview:{row.id}")
    envelope = {
        "from": "yellow-cards@pharmassist.test",
        "to": "yellowcard@eof.test",
        "reply_to": "pharmacist@pharmassist.test",
        "subject": f"ΤΟΠΙΚΗ ΔΟΚΙΜΗ — Κίτρινη Κάρτα {report.id}",
        "body": (
            "Δοκιμαστική αναφορά με συνθετικά δεδομένα. "
            "Μόνο τοπική καταγραφή στο Mailpit. Δεν υποβλήθηκε στον ΕΟΦ."
        ),
    }
    raw = json.dumps(envelope, ensure_ascii=False, sort_keys=True).encode()
    row.envelope = seal(raw, f"envelope:{row.id}")
    row.envelope_sha256 = hashlib.sha256(raw).hexdigest()
    db.add(row)
    await db.commit()
    return {
        "id": str(row.id),
        "revision": row.revision,
        "signature_id": str(sig.id),
        "sha256": row.sha256,
        "envelope": envelope,
        "envelope_sha256": row.envelope_sha256,
    }


@router.get("/{report_id}")
async def detail(
    report_id: uuid.UUID,
    current: dict = Depends(reporting),
    db: AsyncSession = Depends(get_session),
):
    return report_json(await get_owned(db, YellowReport, report_id, current))
