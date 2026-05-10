"""Documentation & Legal Log: list, create, fetch, full + per-record export.

Order matters: ``/export`` and ``/{doc_id}/export`` must be declared *before*
the catch-all ``/{doc_id}`` so FastAPI matches them first. Keeping all five
routes in this single file makes the ordering self-evident.
"""

import time
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query

from ..deps import get_current_user
from ..schemas.documentation import DocumentationCreate
from ..services.documentation import (
    MOCK_DOCUMENTATION,
    csv_response,
    filter_records,
    mark_exported,
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
):
    rows = filter_records(q, method)
    mark_exported(rows)
    today = datetime.now(UTC).date().isoformat()
    fmt = (format or "pdf").lower()
    if fmt == "pdf" and REPORTLAB_AVAILABLE:
        return pdf_response(full_report(rows, current), f"PharmAssist_DocumentationLog_{today}.pdf")
    return csv_response(rows, f"PharmAssist_DocumentationLog_{today}.csv")


@router.get("/{doc_id}/export")
async def export_documentation_record(
    doc_id: str,
    format: str = Query("pdf", description="pdf | csv (default pdf)"),
    current: dict = Depends(get_current_user),
):
    rec = next((d for d in MOCK_DOCUMENTATION if d["id"] == doc_id), None)
    if rec is None:
        raise HTTPException(status_code=404, detail=f"Documentation record {doc_id} not found")
    mark_exported([rec])
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
):
    items = filter_records(q, method)
    total = len(items)
    page = items[offset : offset + limit]
    return {"items": page, "total": total, "stats": stats()}


@router.get("/{doc_id}")
async def get_documentation_record(doc_id: str, current: dict = Depends(get_current_user)):
    rec = next((d for d in MOCK_DOCUMENTATION if d["id"] == doc_id), None)
    if rec is None:
        raise HTTPException(status_code=404, detail=f"Documentation record {doc_id} not found")
    return rec


@router.post("", status_code=201)
async def create_documentation_record(
    payload: DocumentationCreate,
    current: dict = Depends(get_current_user),
):
    """Create a new documentation log entry, e.g. when patient instructions are saved."""
    rx = MOCK_PRESCRIPTIONS.get(payload.rxId)
    if rx is None:
        raise HTTPException(status_code=404, detail=f"Prescription {payload.rxId} not found")
    new_id = f"DOC-{int(time.time() * 1000)}"
    record = {
        "id": new_id,
        "rxId": payload.rxId,
        "patientName": rx["patient"]["name"],
        "drugName": f"{rx['medication']['drugName']} {rx['medication']['dose']}",
        "setting": payload.setting or "Private",
        "deliveryMethod": payload.method.upper(),
        "language": payload.language,
        "informationProvided": payload.instructions,
        "pharmacistName": current.get("name", "Pharmacist"),
        "pharmacistLicense": "PH-12345",
        "signatureConfirmed": True,
        "dispensedAt": datetime.now(UTC).isoformat(),
    }
    MOCK_DOCUMENTATION.insert(0, record)
    return record
