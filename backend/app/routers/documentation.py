"""Documentation & Legal Log: list, create, fetch, full + per-record export.

Order matters: ``/export`` and ``/{doc_id}/export`` must be declared *before*
the catch-all ``/{doc_id}`` so FastAPI matches them first. Keeping all five
routes in this single file makes the ordering self-evident.
"""

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.documentation_log import DocumentationLog
from app.db.session import get_session

from ..deps import get_current_user
from ..schemas.documentation import DocumentationCreate
from ..services.documentation import (
    csv_response,
    filter_records,
    get_documentation_log_dict,
    mark_exported,
    record_prescription_action,
    stats,
)
from ..services.pdf import (
    REPORTLAB_AVAILABLE,
    full_report,
    pdf_response,
    safe_filename_part,
    single_record,
)
from ..services.prescriptions import MOCK_PRESCRIPTIONS

router = APIRouter(prefix="/documentation", tags=["documentation"])


@router.get("/export")
async def export_documentation(
    q: str | None = Query(None, description="Free-text search across patient, rxId, drug."),
    method: str | None = Query(None, description="PRINT | DIGITAL | BOTH | ALL"),
    format: str = Query("pdf", description="pdf | csv (default pdf)"),
    current: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    rows = await filter_records(session, q, method)
    await mark_exported(session, rows)
    dicts = [get_documentation_log_dict(r) for r in rows]
    today = datetime.now(UTC).date().isoformat()
    fmt = (format or "pdf").lower()
    if fmt == "pdf" and REPORTLAB_AVAILABLE:
        return pdf_response(
            full_report(dicts, current), f"PharmAssist_DocumentationLog_{today}.pdf"
        )
    return csv_response(dicts, f"PharmAssist_DocumentationLog_{today}.csv")


@router.get("/{doc_id}/export")
async def export_documentation_record(
    doc_id: uuid.UUID,
    format: str = Query("pdf", description="pdf | csv (default pdf)"),
    current: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    row = await DocumentationLog.get_by_id(session, doc_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"Documentation record {doc_id} not found")
    await mark_exported(session, [row])
    rec = get_documentation_log_dict(row)
    fname_base = f"PharmAssist_Record_{safe_filename_part(rec['rxId'])}_{safe_filename_part(rec['patientName'])}"
    fmt = (format or "pdf").lower()
    if fmt == "pdf" and REPORTLAB_AVAILABLE:
        return pdf_response(single_record(rec, current), f"{fname_base}.pdf")
    return csv_response([rec], f"{fname_base}.csv")


@router.get("")
async def list_documentation(
    q: str | None = Query(None, description="Free-text search across patient, rxId, drug."),
    method: str | None = Query(None, description="PRINT | DIGITAL | BOTH | ALL"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    rows = await filter_records(session, q, method)
    total = len(rows)
    page = [get_documentation_log_dict(r) for r in rows[offset : offset + limit]]
    return {"items": page, "total": total, "stats": await stats(session)}


@router.get("/{doc_id}")
async def get_documentation_record(
    doc_id: uuid.UUID,
    current: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    row = await DocumentationLog.get_by_id(session, doc_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"Documentation record {doc_id} not found")
    return get_documentation_log_dict(row)


@router.post("", status_code=201)
async def create_documentation_record(
    payload: DocumentationCreate,
    current: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Create a new documentation log entry, e.g. when patient instructions are saved."""
    rx = MOCK_PRESCRIPTIONS.get(payload.rxId)
    if rx is None:
        raise HTTPException(status_code=404, detail=f"Prescription {payload.rxId} not found")
    log = await record_prescription_action(
        session,
        action_type="APPROVE",
        rx=rx,
        safety_checks=[],
        pharmacist_email=current["email"],
        pharmapi_exec_ref=None,
        discrepancy_type=None,
        notes=None,
        info_provided=payload.instructions,
        delivery_method=payload.method.upper(),
        ip_address=None,
        user_agent=None,
    )
    record = await DocumentationLog.get_by_id(session, log.id)
    return get_documentation_log_dict(record)
