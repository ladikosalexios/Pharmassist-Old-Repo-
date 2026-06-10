"""B2B /v1 drugs — national catalogue search + formulary substitution.

DB-backed (drug_catalog), so mock/live parity is structural: the 20 seeded
rows serve mock stacks, a masterdata sync serves live ones. Field names are
deliberately honest (BC-11): `barcode` is what the internal gns_code column
actually stores, `activeSubstance` is the INN description.
"""

from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.drug_catalog import DrugCatalog
from app.db.session import get_session
from app.schemas.v1 import V1AlternativesResponse, V1Drug, V1DrugPage
from app.services.drug_catalog import search_catalog
from app.services.formulary import alternatives as formulary_alternatives

from .deps import ApiContext, get_api_context
from .errors import V1Error

router = APIRouter(prefix="/drugs", tags=["b2b-v1"])


def _to_v1_drug(row: DrugCatalog) -> V1Drug:
    return V1Drug(
        barcode=row.gns_code,
        atc_code=row.atc_code or None,
        name=row.name_gr,
        active_substance=row.name_en,
        substance_code=row.substance_code,
        form_code=row.form_code,
        strength=row.strength_raw,
        retail_price=row.retail_price,
        reference_price=row.reference_price,
        eopyy_coverage=row.eopyy_coverage,
        participation_pct=row.participation_pct,
        package_size=row.package_size,
        active=row.active,
    )


@router.get("", response_model=V1DrugPage)
async def search_drugs(
    q: str | None = Query(None, min_length=2, description="Name substring (Greek or INN)"),
    atc: str | None = Query(None, min_length=1, description="ATC code prefix"),
    barcode: str | None = Query(None, description="Exact EOF barcode"),
    page: int = Query(0, ge=0),
    size: int = Query(50, ge=1, le=200),
    ctx: ApiContext = Depends(get_api_context),
    session: AsyncSession = Depends(get_session),
):
    result = await search_catalog(session, q=q, atc=atc, barcode=barcode, page=page, size=size)
    return {
        "items": [_to_v1_drug(row) for row in result["items"]],
        "total": result["total"],
        "page": result["page"],
        "size": result["size"],
        "lastPage": result["last_page"],
    }


@router.get("/{barcode}/alternatives", response_model=V1AlternativesResponse)
async def drug_alternatives(
    barcode: str,
    coverage_filter: Literal["strict", "lenient"] = Query("lenient", alias="coverageFilter"),
    limit: int = Query(10, ge=1, le=50),
    ctx: ApiContext = Depends(get_api_context),
    session: AsyncSession = Depends(get_session),
):
    """Ranked therapeutic alternatives for an unavailable/uncovered drug
    (BC-14): generic equivalents (same ATC-5 + form) first, then same ATC-4
    class; filtered by ΕΟΠΥΥ coverage; every response says where catalogue
    data was too thin to enforce a constraint (dataCaveats)."""
    result = await formulary_alternatives(
        session, barcode=barcode, coverage_filter=coverage_filter, limit=limit
    )
    if result is None:
        raise V1Error("not_found", 404, f"Drug {barcode} not found in the catalogue")
    return {
        "source": _to_v1_drug(result["source"]) if result["source"] is not None else None,
        "sourceAtc": result["source_atc"],
        "coverageFilter": coverage_filter,
        "alternatives": [
            {
                "drug": _to_v1_drug(entry["row"]),
                "tier": entry["tier"],
                "doseNote": entry["dose_note"],
            }
            for entry in result["alternatives"]
        ],
        "dataCaveats": result["data_caveats"],
    }
