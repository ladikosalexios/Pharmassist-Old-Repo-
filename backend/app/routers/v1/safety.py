"""B2B /v1 safety check — explicit-drug-list evaluation (BC-12).

The caller supplies the medication list (and optionally co-medications), so
drug-drug interaction + duplicate-therapy checks run LIVE — unlike the B2C
path, which derives co-medication from upstream history and can't resolve it
to ATC outside mock mode. Conditions come from b2b_patient_conditions scoped
to the calling location (D-3).

Calls evaluate_safety directly — NEVER checks_for_prescription, whose demo
short-circuit serves curated mock checklists regardless of PHARMAPI_MOCK.
Unknown barcodes are surfaced as `unknownDrug: true` per medication: absence
of an alert must never read as "safe".
"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import AlertStatus
from app.db.session import get_session
from app.schemas.v1 import (
    V1MedicationInput,
    V1MedicationResult,
    V1SafetyCheckRequest,
    V1SafetyCheckResponse,
)
from app.services.b2b_conditions import list_conditions
from app.services.drug_catalog import atc_codes_for_barcodes
from app.services.safety_engine import evaluate_safety, load_active_safety_rules

from .deps import ApiContext, get_api_context

router = APIRouter(prefix="/safety", tags=["b2b-v1"])

_STATUS_RANK = {AlertStatus.OK: 0, AlertStatus.REVIEW: 1, AlertStatus.BLOCK: 2}

# This endpoint evaluates drug-drug interactions, duplicate therapy, and
# condition-based contraindications. It does NOT screen ΗΔΥΚΑ intolerances /
# allergies: live intolerance records carry an active-substance description
# with no ATC code, and that activeSubstance→ATC mapping is not yet wired into
# the rule engine. Stated explicitly so a clean status is never read as
# "allergies were checked" — see GET /v1/patients/{amka}/intolerances.
_INTOLERANCE_CAVEAT = (
    "Intolerance/allergy screening is not performed by this endpoint — fetch "
    "GET /v1/patients/{amka}/intolerances and screen separately (ΗΔΥΚΑ "
    "intolerances are not yet mapped to ATC for rule evaluation)."
)


def _resolved_atc(med: V1MedicationInput, barcode_atcs: dict[str, str]) -> str | None:
    if med.atc:
        return med.atc.strip().upper()
    return barcode_atcs.get(med.barcode)


@router.post("/check", response_model=V1SafetyCheckResponse)
async def safety_check(
    body: V1SafetyCheckRequest,
    ctx: ApiContext = Depends(get_api_context),
    session: AsyncSession = Depends(get_session),
):
    amka = body.patient.amka if body.patient else None

    barcodes = [m.barcode for m in body.medications + body.comedications if m.barcode]
    barcode_atcs = await atc_codes_for_barcodes(session, barcodes)
    rules = await load_active_safety_rules(session)
    conditions = await list_conditions(session, ctx.location_id, amka) if amka else []

    med_atcs = [_resolved_atc(m, barcode_atcs) for m in body.medications]
    comed_atcs = {a for m in body.comedications if (a := _resolved_atc(m, barcode_atcs))}

    results: list[V1MedicationResult] = []
    worst = AlertStatus.OK
    for i, (med, atc) in enumerate(zip(body.medications, med_atcs, strict=True)):
        # Co-medication set for THIS drug = every other submitted medication
        # plus the explicit comedications — so a warfarin+aspirin pair in one
        # request fires the interaction on both entries.
        other_atcs = {a for j, a in enumerate(med_atcs) if j != i and a} | comed_atcs
        payload = await evaluate_safety(
            session,
            {
                "rxId": f"V1-CHECK-{i + 1}",
                "patient": {"id": amka, "amka": amka},
                "medication": {"atcCode": atc},
            },
            # Only consulted when patient_conditions is None — always provided
            # here, so the engine never runs its pharmacy-scoped B2C query.
            pharmacy_id=ctx.location_id,
            rules=rules,
            history_atcs=other_atcs,
            patient_conditions=conditions,
            # Explicit empty list: allergy screening on /v1 is gated behind
            # consent + ΕΟΠΥΥ (see _INTOLERANCE_CAVEAT). Passing it stops the
            # engine's B2C internal fetch from firing a legacy-credential
            # intolerance call under this location's context.
            intolerances=[],
        )
        for check in payload.checks:
            if _STATUS_RANK[check.status] > _STATUS_RANK[worst]:
                worst = check.status
        results.append(
            V1MedicationResult(
                input=med,
                atc_code=atc,
                unknown_drug=bool(med.barcode) and atc is None,
                checks=payload.checks,
            )
        )

    return V1SafetyCheckResponse(
        status=worst,
        results=results,
        conditions_considered=len(conditions),
        data_caveats=[_INTOLERANCE_CAVEAT],
    )
