"""B2B /v1 patients — lookup, insurances, intolerances, medicine history, conditions.

Mock/live parity: every upstream-backed endpoint serves live-shaped fixtures
from services/v1_mock.py when PHARMAPI_MOCK=true; conditions are DB-backed in
both modes. Consent (D-5) is caller-attested via ?patientConsent=true on the
two ΕΟΠΥΥ-gated endpoints; non-ΕΟΠΥΥ locations get an explicit 403 instead of
an opaque upstream 609.

The four upstream-backed routes (demographics, insurances, intolerances,
medicine history) sit behind require_retrieval: a location provisioned without
ΗΔΥΚΑ credentials gets 409 `retrieval_unavailable` (T0-2), and a customer below
`core` gets 403 `tier_required` (retrieval is Core scope, D-20). The conditions
CRUD is DB-only and deliberately NOT gated — conditions are the only way a
caller feeds contraindication screening on POST /v1/safety/check, which must
keep working for a credential-less location and for every tier.
"""

import re
import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.schemas.patient_conditions import PatientConditionCreate, PatientConditionUpdate
from app.schemas.patient_insurances import PatientInsurancePayload
from app.schemas.patients import RxHistoryPage
from app.schemas.v1 import V1Condition, V1Intolerance, V1Patient
from app.services import b2b_conditions
from app.services.patients import _map_history_item
from app.services.pharmapi import (
    pharmapi_get_patient,
    pharmapi_get_patient_insurances,
    pharmapi_get_patient_intolerances,
    pharmapi_get_patient_medicine_history,
)
from app.services.v1_mock import (
    MOCK_V1_INSURANCES,
    MOCK_V1_INTOLERANCES,
    MOCK_V1_MEDICINE_HISTORY,
    MOCK_V1_PATIENTS,
)
from app.utils.environment import is_mock_pharmapi

from .deps import RETRIEVAL_RESPONSES, ApiContext, get_api_context, require_retrieval
from .errors import V1Error

router = APIRouter(prefix="/patients", tags=["b2b-v1"])

_AMKA_RE = re.compile(r"^\d{11}$")
_EKAA_RE = re.compile(r"^[A-Za-z0-9]{6,20}$")


def classify_patient_key(patient_key: str) -> tuple[str | None, str | None]:
    """(amka, ekaa) routing with explicit validation — B2C sends any non-AMKA
    string upstream as EKAA; the /v1 contract rejects garbage instead."""
    key = patient_key.strip()
    if _AMKA_RE.match(key):
        return key, None
    if _EKAA_RE.match(key):
        return None, key
    raise V1Error(
        "validation_failed",
        422,
        "patient key must be an 11-digit AMKA or a 6-20 char alphanumeric EKAA",
    )


def _require_amka(patient_key: str) -> str:
    amka, _ = classify_patient_key(patient_key)
    if amka is None:
        raise V1Error("validation_failed", 422, "this endpoint requires an 11-digit AMKA")
    return amka


def _require_consent(patient_consent: bool) -> None:
    if not patient_consent:
        raise V1Error(
            "consent_required",
            422,
            "patientConsent=true is required — the caller must attest the patient's consent",
        )


def _require_eopyy(ctx: ApiContext) -> None:
    if not ctx.is_eopyy:
        raise V1Error(
            "forbidden",
            403,
            "This location's ΗΔΥΚΑ account is not in the ΕΟΠΥΥ category (isIka) — "
            "intolerances and medicine history are unavailable (upstream code 609)",
        )


@router.get("/{patient_key}", response_model=V1Patient, responses=RETRIEVAL_RESPONSES)
async def get_patient(patient_key: str, ctx: ApiContext = Depends(require_retrieval)):
    """Patient demographics by AMKA or EKAA."""
    amka, ekaa = classify_patient_key(patient_key)
    if is_mock_pharmapi():
        profile = MOCK_V1_PATIENTS.get(amka or ekaa)
        if profile is None:
            raise V1Error("not_found", 404, "Patient not found")
        return V1Patient.model_validate(profile)
    payload = await pharmapi_get_patient(amka=amka, ekaa=ekaa, ctx=ctx.pharmapi)
    return V1Patient.model_validate(payload.model_dump())


@router.get(
    "/{patient_key}/insurances",
    response_model=list[PatientInsurancePayload],
    responses=RETRIEVAL_RESPONSES,
)
async def get_patient_insurances(patient_key: str, ctx: ApiContext = Depends(require_retrieval)):
    """ΕΟΠΥΥ/fund coverage entries, incl. the fund's `eopyy` flag (D-9 probe).

    NOTE: ΗΔΥΚΑ supplies no numeric patient-level co-pay % on this payload
    (D-7/D-9, verified — docs/b2b-core/insurances-probe.md). Patient co-pay
    EXEMPTIONS ride the patient profile (`participationExceptions` on
    GET /v1/patients/{key}); drug-level participation lives on /v1/drugs
    (participationPct)."""
    amka, ekaa = classify_patient_key(patient_key)
    if is_mock_pharmapi():
        return MOCK_V1_INSURANCES.get(amka or ekaa, [])
    return await pharmapi_get_patient_insurances(amka=amka, ekaa=ekaa, ctx=ctx.pharmapi)


@router.get(
    "/{patient_key}/intolerances",
    response_model=list[V1Intolerance],
    responses=RETRIEVAL_RESPONSES,
)
async def get_patient_intolerances(
    patient_key: str,
    patient_consent: bool = Query(False, alias="patientConsent"),
    ctx: ApiContext = Depends(require_retrieval),
):
    """Recorded intolerances from ΗΔΥΚΑ (standalone — B2C only embeds these in
    the profile). Requires ΕΟΠΥΥ category + caller-attested consent."""
    amka, ekaa = classify_patient_key(patient_key)
    _require_consent(patient_consent)
    _require_eopyy(ctx)
    if is_mock_pharmapi():
        return MOCK_V1_INTOLERANCES.get(amka or ekaa, [])
    return await pharmapi_get_patient_intolerances(amka or ekaa, ctx=ctx.pharmapi)


@router.get(
    "/{patient_key}/medicine-history",
    response_model=RxHistoryPage,
    responses=RETRIEVAL_RESPONSES,
)
async def get_patient_medicine_history(
    patient_key: str,
    patient_consent: bool = Query(False, alias="patientConsent"),
    page: int = Query(0, ge=0),
    size: int = Query(50, ge=1, le=200),
    ctx: ApiContext = Depends(require_retrieval),
):
    """Executed-prescription history (cross-pharmacy, by AMKA/EKAA). Keeps the
    upstream pagination envelope incl. `blocked: true` on upstream 609."""
    amka, ekaa = classify_patient_key(patient_key)
    _require_consent(patient_consent)
    _require_eopyy(ctx)
    if is_mock_pharmapi():
        rows = MOCK_V1_MEDICINE_HISTORY.get(amka or ekaa, [])
        return {
            "items": rows,
            "page": page,
            "totalPages": 1,
            "lastPage": True,
            "totalEntries": len(rows),
            "blocked": False,
        }
    data = await pharmapi_get_patient_medicine_history(
        amka or ekaa, page=page, size=size, ctx=ctx.pharmapi
    )
    return {
        "items": [_map_history_item(item) for item in data.get("items", [])],
        "page": page,
        "totalPages": data.get("totalPages", 1),
        "lastPage": data.get("lastPage", True),
        "totalEntries": data.get("totalEntries", 0),
        "blocked": data.get("blocked", False),
    }


# ── Patient conditions CRUD (DB-backed, location-scoped — BC-12b / D-3) ─────


@router.get("/{patient_key}/conditions", response_model=list[V1Condition])
async def list_patient_conditions(
    patient_key: str,
    ctx: ApiContext = Depends(get_api_context),
    session: AsyncSession = Depends(get_session),
):
    amka = _require_amka(patient_key)
    return await b2b_conditions.list_conditions(session, ctx.location_id, amka)


@router.post("/{patient_key}/conditions", response_model=V1Condition, status_code=201)
async def create_patient_condition(
    patient_key: str,
    body: PatientConditionCreate,
    ctx: ApiContext = Depends(get_api_context),
    session: AsyncSession = Depends(get_session),
):
    """Record a condition for this patient AT THIS LOCATION. Conditions feed
    the safety engine on POST /v1/safety/check. 409 when an active row for the
    same (patient, condition) already exists at this location."""
    amka = _require_amka(patient_key)
    return await b2b_conditions.create_condition(
        session,
        location_id=ctx.location_id,
        amka=amka,
        # Normalise to upper-case so it matches the safety rules' trigger codes
        # (e.g. "PREGNANCY", "G6PD") — a lower-case code would store fine but
        # never fire a contraindication. B2C's shared schema stays untouched;
        # we normalise here at the /v1 boundary only.
        condition_code=body.condition_code.upper(),
        name=body.name,
        severity=body.severity,
        notes=body.notes,
        created_via_api_key_id=ctx.api_key_id,
    )


@router.patch("/{patient_key}/conditions/{condition_id}", response_model=V1Condition)
async def update_patient_condition(
    patient_key: str,
    condition_id: uuid.UUID,
    body: PatientConditionUpdate,
    ctx: ApiContext = Depends(get_api_context),
    session: AsyncSession = Depends(get_session),
):
    amka = _require_amka(patient_key)
    condition = await b2b_conditions.get_condition(session, ctx.location_id, amka, condition_id)
    if condition is None:
        raise V1Error("not_found", 404, "Condition not found")
    fields = body.model_dump(exclude_unset=True)
    if not fields:
        return condition
    if "condition_code" in fields:
        fields["condition_code"] = fields["condition_code"].upper()  # match rule trigger codes
    return await b2b_conditions.update_condition(session, condition, fields=fields)


@router.delete("/{patient_key}/conditions/{condition_id}", response_model=V1Condition)
async def delete_patient_condition(
    patient_key: str,
    condition_id: uuid.UUID,
    ctx: ApiContext = Depends(get_api_context),
    session: AsyncSession = Depends(get_session),
):
    """Soft delete — the row stays for audit, drops out of lists + safety checks."""
    amka = _require_amka(patient_key)
    condition = await b2b_conditions.get_condition(session, ctx.location_id, amka, condition_id)
    if condition is None:
        raise V1Error("not_found", 404, "Condition not found")
    return await b2b_conditions.deactivate_condition(session, condition)
