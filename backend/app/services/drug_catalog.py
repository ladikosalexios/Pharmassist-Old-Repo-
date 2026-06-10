"""Sync the drug_catalog table from Pharmapi masterdata + the /v1 search read path."""

from sqlalchemy import func, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.drug_catalog import DrugCatalog
from app.services.formulary import parse_strength
from app.services.pharmapi import pharmapi_get_masterdata_medicines

from ..db.session import AsyncSessionLocal

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


async def run_sync(since: str | None) -> None:
    async with AsyncSessionLocal() as db:
        try:
            result = await _sync_drug_catalog(db, since=since)
            print(
                f"[sync-drug-catalog] Complete — "
                f"fetched={result['fetched']} upserted={result['upserted']} "
                f"skipped={result['skipped']}"
            )
        except Exception as exc:
            print(f"[sync-drug-catalog] Failed — {exc}")


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
