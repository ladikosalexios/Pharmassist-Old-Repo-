"""Sync the drug_catalog table from Pharmapi masterdata."""

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.drug_catalog import DrugCatalog
from app.services.pharmapi import pharmapi_get_masterdata_medicines

from ..db.session import AsyncSessionLocal


def _inn_name(item: dict) -> str | None:
    """Extract the main active substance INN (International Nonproprietary Name) description."""
    for entry in item.get("activeSubstances") or []:
        if entry.get("mainActiveSubstance"):
            return (entry.get("activeSubstance") or {}).get("description")
    return None


def _to_row(item: dict) -> dict | None:
    """Map one Pharmapi medicine dict to a DrugCatalog insert dict.
    Returns None if barcode is missing (row is skipped)."""
    barcode = item.get("barcode")
    if not barcode:
        return None
    brand = item.get("commercialNameOnly") or ""
    strength = item.get("content") or ""
    name_gr = f"{brand} {strength}".strip() if strength else brand
    return {
        "gns_code": str(barcode),
        "atc_code": item.get("atcCode") or "",
        "atc_class": "",  # not supplied by Pharmapi masterdata
        "name_gr": name_gr,
        "name_en": _inn_name(item),
        "interaction_group": None,  # not supplied by Pharmapi
        "active": item["inCirculation"] if item.get("inCirculation") is not None else True,
    }


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
                set_={
                    k: getattr(stmt.excluded, k)
                    for k in ("atc_code", "name_gr", "name_en", "active")
                },
            )
            await db.execute(stmt)
            upserted += len(rows)
        await db.commit()

        if data.get("lastPage", True):
            break
        page += 1

    return {"fetched": fetched, "upserted": upserted, "skipped": skipped}
