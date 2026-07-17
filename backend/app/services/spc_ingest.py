"""SPC/ΦΟΧ document ingestion: PDF bytes → parsed SpcDetails row.

One pipeline for every source (admin upload, ΕΟΦ fetch, EMA fetch):
extract text → deterministic section split → map to SpcDetails →
LLM enrichment (live-only, additive — see services/spc_extract.py) → row.

The LLM call happens BEFORE the document row is staged: ``llm.complete``
commits its cache row internally, and that commit must never sweep a
half-staged document along with it.
"""

import asyncio
import hashlib
import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import get_settings
from ..db.models.drug_catalog import DrugCatalog
from ..db.models.spc_document import SpcDocument
from . import spc_extract, spc_parse
from .audit import _background_tasks

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


# ── Automated fetching: on-demand (scan-triggered) + batch ───────────────────
#
# fetch_for_product never raises; failures land in spc_fetch_state (per
# barcode+source, with exponential-ish backoff) and surface via
# GET /admin/spc/status. The scan hook (fire_spc_fetch_for_meds) is a tracked
# fire-and-forget task on the audit-task pattern, and no-ops instantly when
# both source flags are off.

_BACKOFF_HOURS = (1, 6, 24, 72)
_BACKOFF_CAP_HOURS = 7 * 24

# In-process guard so a burst of scans of the same barcode doesn't stack
# concurrent fetches before the first one records state.
_in_flight: set[str] = set()


def next_attempt_delay(attempts: int) -> timedelta:
    """Backoff schedule: 1→1h, 2→6h, 3→24h, 4→72h, ≥5→7d (pure function)."""
    if attempts <= 0:
        return timedelta(0)
    if attempts <= len(_BACKOFF_HOURS):
        return timedelta(hours=_BACKOFF_HOURS[attempts - 1])
    return timedelta(hours=_BACKOFF_CAP_HOURS)


def _enabled_sources() -> list[str]:
    settings = get_settings()
    out = []
    if settings.spc_fetch_eof_enabled:
        out.append("eof")
    if settings.spc_fetch_ema_enabled:
        out.append("ema")
    return out


async def _has_document(session: AsyncSession, barcode: str, atc_code: str | None) -> bool:
    doc = await session.scalar(
        select(SpcDocument.id).where(
            SpcDocument.parse_status != "failed",
            (SpcDocument.barcode == barcode)
            | (SpcDocument.atc_code == atc_code if atc_code else False),
        )
    )
    return doc is not None


async def _record_failure(session: AsyncSession, barcode: str, source: str, error: str) -> None:
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    from ..db.models.spc_fetch_state import SpcFetchState

    now = datetime.now(UTC)
    existing = await session.scalar(
        select(SpcFetchState).where(
            SpcFetchState.barcode == barcode, SpcFetchState.source == source
        )
    )
    attempts = (existing.attempts if existing else 0) + 1
    stmt = pg_insert(SpcFetchState).values(
        barcode=barcode,
        source=source,
        attempts=attempts,
        last_attempt_at=now,
        next_attempt_at=now + next_attempt_delay(attempts),
        last_error=error[:2000],
    )
    await session.execute(
        stmt.on_conflict_do_update(
            index_elements=["barcode", "source"],
            set_={
                "attempts": attempts,
                "last_attempt_at": now,
                "next_attempt_at": now + next_attempt_delay(attempts),
                "last_error": error[:2000],
            },
        )
    )
    await session.commit()


async def _clear_state(session: AsyncSession, barcode: str, source: str) -> None:
    from sqlalchemy import delete

    from ..db.models.spc_fetch_state import SpcFetchState

    await session.execute(
        delete(SpcFetchState).where(
            SpcFetchState.barcode == barcode, SpcFetchState.source == source
        )
    )
    await session.commit()


async def _source_blocked(session: AsyncSession, barcode: str, source: str) -> bool:
    from ..db.models.spc_fetch_state import SpcFetchState

    state = await session.scalar(
        select(SpcFetchState).where(
            SpcFetchState.barcode == barcode, SpcFetchState.source == source
        )
    )
    return bool(state and state.next_attempt_at and state.next_attempt_at > datetime.now(UTC))


async def fetch_for_product(barcode: str) -> int:
    """Fetch + ingest SPC documents for one product. Returns docs ingested.

    Never raises. Skips when a usable document already exists, when the
    product isn't in the catalog, or when every enabled source is backing off.
    """
    from ..db.session import AsyncSessionLocal
    from .spc_sources import base as sources_base
    from .spc_sources import ema as ema_adapter
    from .spc_sources import eof as eof_adapter

    adapters = {"eof": eof_adapter, "ema": ema_adapter}
    ingested = 0
    try:
        async with AsyncSessionLocal() as session:
            product = await session.scalar(
                select(DrugCatalog).where(DrugCatalog.gns_code == barcode)
            )
            if product is None:
                return 0
            if await _has_document(session, barcode, product.atc_code):
                return 0

            for source in _enabled_sources():
                if await _source_blocked(session, barcode, source):
                    continue
                result = await adapters[source].resolve(product)
                if not result.docs:
                    await _record_failure(
                        session, barcode, source, result.error or "no documents found"
                    )
                    continue
                source_errors: list[str] = []
                for found in result.docs:
                    try:
                        pdf = await sources_base.download(found.url, source=source)
                        await ingest_pdf_bytes(
                            session,
                            pdf=pdf,
                            source=source,
                            doc_type=found.doc_type,
                            atc_code=product.atc_code,
                            barcode=barcode,
                            source_url=found.url,
                        )
                        ingested += 1
                    except Exception as exc:  # download/parse failure — contained
                        source_errors.append(f"{found.doc_type}: {type(exc).__name__}: {exc}")
                if ingested:
                    await _clear_state(session, barcode, source)
                    break  # first source that delivered wins
                await _record_failure(session, barcode, source, "; ".join(source_errors))
    except Exception:
        logger.warning("[spc] fetch_for_product failed for %s", barcode, exc_info=True)
    return ingested


async def _fetch_meds_task(barcodes: list[str]) -> None:
    for barcode in barcodes:
        try:
            await fetch_for_product(barcode)
        finally:
            _in_flight.discard(barcode)


def fire_spc_fetch_for_meds(medications: list[dict] | None) -> None:
    """Scan hook: background-fetch SPC docs for any scanned med lacking one.

    Instant no-op when no source adapter is enabled — the mock/dev stack
    never spawns tasks or touches the network.
    """
    if not medications or not _enabled_sources():
        return
    barcodes = []
    for med in medications:
        barcode = med.get("nhrn") if isinstance(med, dict) else None
        if barcode and barcode not in _in_flight:
            _in_flight.add(barcode)
            barcodes.append(barcode)
    if not barcodes:
        return
    task = asyncio.create_task(_fetch_meds_task(barcodes))
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)


async def run_batch(top_n: int = 50, triggered_by: str | None = None) -> None:
    """Batch-fetch SPC docs for the most-scanned uncovered products.

    Candidate ranking comes from prescription_scans frequency — counter
    reality decides what matters first. Never raises; bookkeeping lands in
    spc_sync_runs (same philosophy as drug_catalog.run_sync).
    """
    from ..db.models.prescription_scan import PrescriptionScan
    from ..db.models.spc_sync_run import SpcSyncRun
    from ..db.session import AsyncSessionLocal

    try:
        async with AsyncSessionLocal() as session:
            run = SpcSyncRun(mode="batch", status="running", triggered_by=triggered_by)
            session.add(run)
            await session.commit()
            await session.refresh(run)
            run_id = run.id
    except Exception:
        logger.exception("[spc] could not record batch run — aborting")
        return

    examined = fetched = failed = 0
    error: str | None = None
    try:
        async with AsyncSessionLocal() as session:
            # Most-scanned barcodes first; scans carry per-line meds in the
            # payload, but the scan barcode itself ranks the prescription.
            rows = await session.execute(
                select(
                    PrescriptionScan.rx_payload["medications"].label("meds"),
                )
                .order_by(PrescriptionScan.created_at.desc())
                .limit(500)
            )
            candidates: list[str] = []
            for (meds,) in rows:
                for med in meds or []:
                    barcode = med.get("nhrn") if isinstance(med, dict) else None
                    if barcode and barcode not in candidates:
                        candidates.append(barcode)
                if len(candidates) >= top_n:
                    break

        for barcode in candidates[:top_n]:
            examined += 1
            got = await fetch_for_product(barcode)
            if got:
                fetched += got
            else:
                failed += 1
    except Exception as exc:
        logger.exception("[spc] batch run %s failed", run_id)
        error = f"{type(exc).__name__}: {exc}"[:2000]

    try:
        async with AsyncSessionLocal() as session:
            run = await session.get(SpcSyncRun, run_id)
            if run is not None:
                run.status = "error" if error else "success"
                run.finished_at = datetime.now(UTC)
                run.examined = examined
                run.fetched_docs = fetched
                run.parsed_docs = fetched
                run.failed = failed
                run.error = error
                await session.commit()
    except Exception:
        logger.exception("[spc] could not finish batch run %s", run_id)
