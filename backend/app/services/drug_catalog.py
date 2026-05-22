"""Sync the drug_catalog table from Pharmapi masterdata."""

import uuid

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.drug_catalog import DrugCatalog
from app.services.pharmapi import pharmapi_get_masterdata_medicines

def _inn_name(item: dict) -> str | None:
    """Extract the main active substance INN description."""
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
        "id": uuid.uuid4(),
        "gns_code": str(barcode),
        "atc_code": item.get("atcCode") or "",
        "atc_class": "",  # not supplied by Pharmapi masterdata
        "name_gr": name_gr,
        "name_en": _inn_name(item),
        "interaction_group": None,  # not supplied by Pharmapi
        "active": item["inCirculation"] if item.get("inCirculation") is not None else True,
    }


async def sync_drug_catalog(
    db: AsyncSession,
    since: str | None = None,
    page_size: int = 500,
) -> dict:
    """Paginate Pharmapi medicines and upsert into drug_catalog.

    Existing rows matched on gns_code are updated; interaction_group is
    intentionally excluded from the update set so manually assigned values
    are preserved.

    Returns {"fetched": N, "upserted": N, "skipped": N}.
    """
    fetched = upserted = skipped = 0
    page = 0

    while True:
        data = await pharmapi_get_masterdata_medicines(page=page, size=page_size, since=since)
        items = data.get("contents") if isinstance(data, dict) else data
        if not items:
            break

        for item in items:
            row = _to_row(item)
            if row is None:
                skipped += 1
                continue
            fetched += 1
            stmt = (
                insert(DrugCatalog)
                .values(**row)
                .on_conflict_do_update(
                    index_elements=["gns_code"],
                    set_={
                        "atc_code": row["atc_code"],
                        "atc_class": row["atc_class"],
                        "name_gr": row["name_gr"],
                        "name_en": row["name_en"],
                        "active": row["active"],
                    },
                )
            )
            await db.execute(stmt)
            upserted += 1

        await db.commit()

        if data.get("lastPage", True):
            break
        page += 1

    return {"fetched": fetched, "upserted": upserted, "skipped": skipped}
