"""Summary of Product Characteristics: lookup, provenance, verification.

Serving policy: auto-extracted content is shown immediately (the frontend
labels it "auto-extracted — verify against source"); the verify endpoint
lets any authenticated pharmacist upgrade the label — it never gates serving.

Route order matters: the fixed ``/documents/...`` paths are declared before
the ``/{atc_code}`` catch-all.
"""

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.models.spc_document import SpcDocument
from ..db.session import get_session
from ..deps import get_current_user
from ..services.spc import resolve_spc

router = APIRouter(prefix="/spc", tags=["spc"])


class VerifyRequest(BaseModel):
    verified: bool = True


@router.get("/documents/{document_id}/pdf")
async def get_document_pdf(
    document_id: uuid.UUID,
    current: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """The stored source document — the badge's "verify against source" link.

    Served from our own copy because ΕΟΦ portal URLs are session-bound and
    expire; EMA links stay stable and are preferred when present, but this
    endpoint always works.
    """
    doc = await session.get(SpcDocument, document_id)
    if doc is None or not doc.raw_pdf:
        raise HTTPException(status_code=404, detail="Document PDF not available")
    return Response(content=doc.raw_pdf, media_type="application/pdf")


@router.post("/documents/{document_id}/verify")
async def verify_document(
    document_id: uuid.UUID,
    body: VerifyRequest,
    current: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Mark a document's extracted content as pharmacist-reviewed (or revoke)."""
    doc = await session.get(SpcDocument, document_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")
    doc.verified = body.verified
    doc.verified_by = current.get("email") if body.verified else None
    doc.verified_at = datetime.now(UTC) if body.verified else None
    await session.commit()
    return {"documentId": str(doc.id), "verified": doc.verified}


@router.get("/{atc_code}")
async def get_spc(
    atc_code: str,
    barcode: str | None = None,
    current: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """SpcDetails for an ATC code, product-precise when a barcode is passed.

    Ingested documents win over the mock fixture; the response carries
    provenance fields (source/verified/extractionMethod/documentId) that
    drive the review page's badge.
    """
    payload = await resolve_spc(session, atc_code, barcode=barcode)
    if payload is None:
        raise HTTPException(status_code=404, detail=f"SPC not found for ATC {atc_code}")
    return payload
