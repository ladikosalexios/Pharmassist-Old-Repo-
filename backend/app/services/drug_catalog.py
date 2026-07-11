"""Sync the drug_catalog table from Pharmapi masterdata + the /v1 search read path."""

import logging
from datetime import UTC, datetime

from sqlalchemy import func, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.catalog_sync_run import CatalogSyncRun
from app.db.models.drug_catalog import DrugCatalog
from app.services.formulary import parse_strength
from app.services.pharmapi import pharmapi_get_masterdata_medicines

from ..db.session import AsyncSessionLocal

logger = logging.getLogger(__name__)

# Columns refreshed on every sync upsert. interaction_group and atc_class are
# intentionally excluded so manually assigned values are preserved.
_SYNC_UPDATE_COLUMNS = (
    "atc_code",
    "name_gr",
    "name_en",
    "active",
    "form_code",
    "strength_raw",
    "strength_value",
    "strength_unit",
    "retail_price",
    "reference_price",
    "eopyy_coverage",
    "participation_pct",
    "substance_code",
    "package_size",
)


def _inn_name(item: dict) -> str | None:
    """Extract the main active substance INN (International Nonproprietary Name) description."""
    for entry in item.get("activeSubstances") or []:
        if entry.get("mainActiveSubstance"):
            return (entry.get("activeSubstance") or {}).get("description")
    return None


def _substance_code(item: dict) -> str | None:
    for entry in item.get("activeSubstances") or []:
        if entry.get("mainActiveSubstance"):
            code = (entry.get("activeSubstance") or {}).get("code")
            return str(code) if code is not None else None
    return None


def _to_row(item: dict) -> dict | None:
    """Map one Pharmapi medicine dict to a DrugCatalog insert dict.
    Returns None if barcode is missing (row is skipped).

    Formulary fields (BC-13) follow the live-probe mapping in
    docs/b2b-core/masterdata-probe.md: positiveList → eopyy_coverage,
    retailPrice/referencePrice, participationPercentage, formCode, content
    (raw + parsed strength), main activeSubstance.code, piecesPerPackage.
    """
    barcode = item.get("barcode")
    if not barcode:
        return None
    brand = item.get("commercialNameOnly") or ""
    strength = item.get("content") or ""
    name_gr = f"{brand} {strength}".strip() if strength else brand
    strength_value, strength_unit = parse_strength(strength)
    pieces = item.get("piecesPerPackage")
    return {
        "gns_code": str(barcode),
        "atc_code": item.get("atcCode") or "",
        "atc_class": "",  # not supplied by Pharmapi masterdata
        "name_gr": name_gr,
        "name_en": _inn_name(item),
        "interaction_group": None,  # not supplied by Pharmapi
        "active": item["inCirculation"] if item.get("inCirculation") is not None else True,
        "form_code": item.get("formCode") or None,
        "strength_raw": strength or None,
        "strength_value": strength_value,
        "strength_unit": strength_unit,
        "retail_price": item.get("retailPrice"),
        "reference_price": item.get("referencePrice"),
        "eopyy_coverage": item.get("positiveList"),
        "participation_pct": item.get("participationPercentage"),
        "substance_code": _substance_code(item),
        "package_size": str(pieces) if pieces is not None else None,
    }


async def search_catalog(
    session: AsyncSession,
    *,
    q: str | None = None,
    atc: str | None = None,
    barcode: str | None = None,
    page: int = 0,
    size: int = 50,
) -> dict:
    """Paginated catalogue search for the /v1 drugs endpoint (BC-11).

    `q` matches name_gr OR name_en (case-insensitive substring), `atc` is a
    prefix match (index-backed), `barcode` is exact. Filters combine with AND.
    DB-backed, so mock/live parity is free — the seeded 20 rows serve mock
    environments, a masterdata sync serves live ones.
    """
    conds = []
    if q:
        pattern = f"%{q.strip()}%"
        conds.append(or_(DrugCatalog.name_gr.ilike(pattern), DrugCatalog.name_en.ilike(pattern)))
    if atc:
        conds.append(DrugCatalog.atc_code.like(f"{atc.strip().upper()}%"))
    if barcode:
        conds.append(DrugCatalog.gns_code == barcode.strip())

    total = (await session.scalars(select(func.count(DrugCatalog.id)).where(*conds))).one()
    rows = (
        await session.scalars(
            select(DrugCatalog)
            .where(*conds)
            .order_by(DrugCatalog.name_gr)
            .offset(page * size)
            .limit(size)
        )
    ).all()
    return {
        "items": list(rows),
        "total": total,
        "page": page,
        "size": size,
        "last_page": (page + 1) * size >= total,
    }


async def atc_codes_for_barcodes(
    session: AsyncSession,
    barcodes: list[str | None],
) -> dict[str, str]:
    """Return {gns_code: atc_code} for every barcode that exists in drug_catalog.

    Rows where atc_code is blank (stored as "" by _to_row when Pharmapi omits
    it) are excluded — callers get None from .get() for those, which is the
    same signal as "not in catalog" and correctly causes ATC-keyed checks to
    skip rather than match against an empty string.
    """
    barcodes = [b for b in barcodes if b]
    if not barcodes:
        return {}
    rows = await session.scalars(select(DrugCatalog).where(DrugCatalog.gns_code.in_(barcodes)))
    return {row.gns_code: row.atc_code for row in rows if row.atc_code}


async def run_sync(since: str | None, triggered_by: str | None = None) -> None:
    """Run one catalogue sync, recording a catalog_sync_runs row (FT-4).

    Built for BackgroundTasks / cron callers: never raises. Failures land in
    the status row (visible via GET /admin/sync-drug-catalog/status) AND the
    log — the previous behaviour printed-and-swallowed, so a dead sync was
    invisible anywhere but live container output.
    """
    try:
        async with AsyncSessionLocal() as db:
            run = CatalogSyncRun(
                mode="incremental" if since else "full",
                since=since,
                status="running",
                triggered_by=triggered_by,
            )
            db.add(run)
            await db.commit()
            await db.refresh(run)
            run_id = run.id
    except Exception:
        logger.exception("[sync-drug-catalog] could not record sync run — aborting")
        return

    try:
        async with AsyncSessionLocal() as db:
            result = await _sync_drug_catalog(db, since=since)
    except Exception as exc:
        logger.exception("[sync-drug-catalog] failed (run %s)", run_id)
        await _finish_run(run_id, status="error", error=f"{type(exc).__name__}: {exc}"[:2000])
        return

    logger.info(
        "[sync-drug-catalog] complete (run %s) — fetched=%d upserted=%d skipped=%d",
        run_id,
        result["fetched"],
        result["upserted"],
        result["skipped"],
    )
    await _finish_run(run_id, status="success", **result)


async def _finish_run(
    run_id,
    *,
    status: str,
    error: str | None = None,
    fetched: int = 0,
    upserted: int = 0,
    skipped: int = 0,
) -> None:
    try:
        async with AsyncSessionLocal() as db:
            run = await db.get(CatalogSyncRun, run_id)
            if run is None:  # pragma: no cover — row deleted mid-run
                return
            run.status = status
            run.error = error
            run.fetched = fetched
            run.upserted = upserted
            run.skipped = skipped
            run.finished_at = datetime.now(UTC)
            await db.commit()
    except Exception:  # pragma: no cover — DB died between sync and bookkeeping
        logger.exception("[sync-drug-catalog] could not finalise run %s", run_id)


async def catalog_coverage(session: AsyncSession) -> dict:
    """Formulary + safety-resolver data-quality counts over ACTIVE rows.

    One query, FILTER-per-column: how complete is the catalogue for every
    field the formulary ranks/filters on AND every field the substance
    resolver keys on. The onboarding gate reads this after the first full
    production sync — near-zero with_coverage means the sync hasn't run (or
    upstream stopped supplying positiveList) and the `strict` coverage filter
    would return nothing.

    `with_atc` / `with_inn_name` / `with_substance` are the resolver-readiness
    triad (services/substance_resolver): live intolerance + co-medication
    checks can only resolve a drug name→ATC when these are populated, so a
    formulary-green sync with empty ATC/INN would still leave those checks
    silent. `atc_code` is NOT NULL (stored "" when upstream omits it), so it is
    counted non-blank rather than non-null.
    """

    def _non_null(col):
        return func.count(DrugCatalog.id).filter(col.is_not(None))

    stmt = select(
        func.count(DrugCatalog.id).label("total_active"),
        _non_null(DrugCatalog.eopyy_coverage).label("with_coverage"),
        _non_null(DrugCatalog.retail_price).label("with_price"),
        _non_null(DrugCatalog.participation_pct).label("with_participation"),
        _non_null(DrugCatalog.form_code).label("with_form"),
        _non_null(DrugCatalog.substance_code).label("with_substance"),
        func.count(DrugCatalog.id).filter(DrugCatalog.atc_code != "").label("with_atc"),
        _non_null(DrugCatalog.name_en).label("with_inn_name"),
    ).where(DrugCatalog.active.is_(True))
    row = (await session.execute(stmt)).one()
    return {
        "total_active": row.total_active,
        "with_coverage": row.with_coverage,
        "with_price": row.with_price,
        "with_participation": row.with_participation,
        "with_form": row.with_form,
        "with_substance": row.with_substance,
        "with_atc": row.with_atc,
        "with_inn_name": row.with_inn_name,
    }


async def _sync_drug_catalog(
    db: AsyncSession,
    since: str | None = None,
    page_size: int = 500,
) -> dict:
    """Paginate Pharmapi medicines and upsert into drug_catalog.

    Existing rows matched on gns_code are updated; interaction_group and
    atc_class are intentionally excluded from the update set so manually
    assigned values are preserved.

    Returns {"fetched": N, "upserted": N, "skipped": N}.
    """
    fetched = upserted = skipped = 0
    page = 0

    while True:
        data = await pharmapi_get_masterdata_medicines(page=page, size=page_size, since=since)
        items = (data or {}).get("contents")
        if not items:
            break

        rows = [r for item in items if (r := _to_row(item)) is not None]
        skipped += len(items) - len(rows)
        rows = list({r["gns_code"]: r for r in rows}.values())
        fetched += len(rows)
        if rows:
            stmt = insert(DrugCatalog).values(rows)
            stmt = stmt.on_conflict_do_update(
                index_elements=["gns_code"],
                set_={k: getattr(stmt.excluded, k) for k in _SYNC_UPDATE_COLUMNS},
            )
            await db.execute(stmt)
            upserted += len(rows)
        await db.commit()

        if data.get("lastPage", True):
            break
        page += 1

    return {"fetched": fetched, "upserted": upserted, "skipped": skipped}
