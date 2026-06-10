"""B2B /v1 prescriptions — search (pending + dispensed) and detail-by-barcode.

Contract decision (audit finding): `status=dispensed` REQUIRES `amka`. ΗΔΥΚΑ
rejects prescribed=true without an AMKA (code 606) and the B2C router papers
over that by silently degrading to a mixed unfiltered search — a paid API
must refuse loudly instead of returning the wrong data class.
"""

from typing import Literal

from fastapi import APIRouter, Depends, Query

from app.schemas.v1 import V1PrescriptionItem, V1PrescriptionPage
from app.services.pharmapi import pharmapi_search_prescriptions
from app.services.v1_mock import MOCK_V1_PRESCRIPTIONS
from app.utils.environment import is_mock_pharmapi

from .deps import ApiContext, get_api_context
from .errors import V1Error

router = APIRouter(prefix="/prescriptions", tags=["b2b-v1"])

_MOCK_STATUS = {"pending": "PENDING", "dispensed": "COMPLETED"}


@router.get("", response_model=V1PrescriptionPage)
async def search_prescriptions(
    status: Literal["pending", "dispensed"] = Query("pending"),
    amka: str | None = Query(None, description="Patient AMKA (required for status=dispensed)"),
    from_date: str | None = Query(None, alias="from", description="Start date YYYY-MM-DD"),
    to_date: str | None = Query(None, alias="to", description="End date YYYY-MM-DD"),
    page: int = Query(0, ge=0),
    size: int = Query(50, ge=1, le=200),
    ctx: ApiContext = Depends(get_api_context),
):
    if status == "dispensed" and not amka:
        raise V1Error(
            "validation_failed",
            422,
            "status=dispensed requires amka — ΗΔΥΚΑ rejects a dispensed-search "
            "without a patient (upstream code 606)",
        )
    if is_mock_pharmapi():
        items = [
            item
            for item in MOCK_V1_PRESCRIPTIONS
            if item["status"] == _MOCK_STATUS[status] and (not amka or item["patientAmka"] == amka)
        ]
        return {"items": items, "count": len(items)}
    items = await pharmapi_search_prescriptions(
        prescribed=(status == "dispensed"),
        page=page,
        size=size,
        from_date=from_date,
        to_date=to_date,
        amka=amka,
        ctx=ctx.pharmapi,
    )
    return {"items": items, "count": len(items)}


@router.get("/{barcode}", response_model=V1PrescriptionItem)
async def get_prescription(barcode: str, ctx: ApiContext = Depends(get_api_context)):
    """Prescription by barcode — the search endpoint filtered to one result
    (Pharmapi v2 has no richer read-only detail endpoint; the CDA retrieval
    path is dispense-scoped and out of Tier-1)."""
    if is_mock_pharmapi():
        for item in MOCK_V1_PRESCRIPTIONS:
            if item["rxId"] == barcode:
                return item
        raise V1Error("not_found", 404, f"Prescription {barcode} not found")
    results = await pharmapi_search_prescriptions(barcode=barcode, ctx=ctx.pharmapi)
    if not results:
        raise V1Error("not_found", 404, f"Prescription {barcode} not found")
    return results[0]
