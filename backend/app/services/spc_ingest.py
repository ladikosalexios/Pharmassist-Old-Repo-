"""SPC/ΦΟΧ document ingestion: PDF bytes → parsed SpcDetails row.

One pipeline for every source (admin upload, ΕΟΦ fetch, EMA fetch):
extract text → deterministic section split → map to SpcDetails →
LLM enrichment (live-only, additive — see services/spc_extract.py) → row.

The LLM call happens BEFORE the document row is staged: ``llm.complete``
commits its cache row internally, and that commit must never sweep a
half-staged document along with it.
"""

import hashlib
import logging

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import get_settings
from ..db.models.drug_catalog import DrugCatalog
from ..db.models.spc_document import SpcDocument
from . import spc_extract, spc_parse

logger = logging.getLogger(__name__)


def _merge_enrichment(deterministic: dict, llm_payload: dict) -> dict:
    """Overlay LLM-normalised fields onto the deterministic payload.

    The LLM wins per-field only where it produced content; deterministic
    values survive everywhere else (enrichment can add, never lose)."""
    merged = dict(deterministic)
    for key in ("recommendedDosage", "foodInstructions"):
        if llm_payload.get(key):
            merged[key] = llm_payload[key]
    for key in ("contraindications", "precautions", "majorInteractions"):
        if llm_payload.get(key):
            merged[key] = llm_payload[key]
    llm_storage = llm_payload.get("storage") or {}
    if any(llm_storage.get(k) for k in ("conditions", "afterOpening", "disposal")):
        base = dict(deterministic.get("storage") or {})
        for k in ("conditions", "afterOpening", "disposal"):
            if llm_storage.get(k):
                base[k] = llm_storage[k]
        merged["storage"] = base
    return merged


async def ingest_pdf_bytes(
    session: AsyncSession,
    *,
    pdf: bytes,
    source: str,
    doc_type: str,
    atc_code: str,
    barcode: str | None = None,
    source_url: str | None = None,
    language: str = "el",
) -> SpcDocument:
    """Parse + persist one document. Commits. Raises ValueError on inputs the
    pipeline cannot accept (oversize file, unknown doc_type); a PDF that
    parses to nothing is NOT an error — it lands as ``parse_status="failed"``
    with the raw bytes retained for a future re-parse.
    """
    settings = get_settings()
    if len(pdf) > settings.spc_max_pdf_bytes:
        raise ValueError(f"PDF exceeds spc_max_pdf_bytes ({settings.spc_max_pdf_bytes})")
    if doc_type not in ("spc", "pil", "combined"):
        raise ValueError(f"Unknown doc_type {doc_type!r}")

    sha = hashlib.sha256(pdf).hexdigest()
    existing = await session.scalar(
        select(SpcDocument).where(
            SpcDocument.barcode == barcode,
            SpcDocument.doc_type == doc_type,
            SpcDocument.sha256 == sha,
        )
    )
    if existing is not None:
        return existing

    text = spc_parse.extract_text(pdf)
    spc_sections = spc_parse.split_spc_sections(text) if doc_type in ("spc", "combined") else {}
    pil_sections = spc_parse.split_pil_sections(text) if doc_type in ("pil", "combined") else {}
    parsed, parse_status = spc_parse.map_to_details(spc_sections, pil_sections)
    extraction_method = "deterministic"

    if parse_status != "failed":
        # Target sections in the prompt-contract order (spc_extract._SECTION_LABELS).
        storage_text = "\n".join(
            filter(
                None,
                (
                    spc_sections.get("6.3"),
                    spc_sections.get("6.4"),
                    spc_sections.get("6.6"),
                    pil_sections.get("5"),
                ),
            )
        )
        target_sections = [
            spc_sections.get("4.2") or pil_sections.get("3") or "",
            spc_sections.get("4.3") or "",
            spc_sections.get("4.4") or "",
            spc_sections.get("4.5") or "",
            storage_text,
        ]
        enriched = await spc_extract.enrich(session, target_sections)
        if enriched is not None:
            parsed = _merge_enrichment(parsed, enriched)
            extraction_method = "llm"

    doc = SpcDocument(
        barcode=barcode,
        atc_code=atc_code,
        doc_type=doc_type,
        source=source,
        source_url=source_url,
        sha256=sha,
        language=language,
        raw_pdf=pdf,
        full_text=text or None,
        sections={**spc_sections, **{f"pil-{k}": v for k, v in pil_sections.items()}} or None,
        parsed=parsed,
        extraction_method=extraction_method,
        parse_status=parse_status,
    )
    session.add(doc)
    await session.commit()
    await session.refresh(doc)
    logger.info(
        "[spc] ingested %s doc for atc=%s barcode=%s status=%s method=%s",
        source,
        atc_code,
        barcode,
        parse_status,
        extraction_method,
    )
    return doc


async def spc_coverage(session: AsyncSession) -> dict:
    """Coverage counts for GET /admin/spc/status."""
    total_docs = await session.scalar(select(func.count(SpcDocument.id))) or 0
    parsed_docs = (
        await session.scalar(
            select(func.count(SpcDocument.id)).where(SpcDocument.parse_status != "failed")
        )
        or 0
    )
    verified_docs = (
        await session.scalar(
            select(func.count(SpcDocument.id)).where(SpcDocument.verified.is_(True))
        )
        or 0
    )
    atcs_covered = (
        await session.scalar(
            select(func.count(func.distinct(SpcDocument.atc_code))).where(
                SpcDocument.parse_status != "failed"
            )
        )
        or 0
    )
    catalog_atcs = (
        await session.scalar(
            select(func.count(func.distinct(DrugCatalog.atc_code))).where(
                DrugCatalog.atc_code != ""
            )
        )
        or 0
    )
    return {
        "total_docs": total_docs,
        "parsed_docs": parsed_docs,
        "verified_docs": verified_docs,
        "atcs_covered": atcs_covered,
        "catalog_atcs": catalog_atcs,
    }
