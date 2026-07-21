"""Patient profile + per-patient prescription / ADR history.

Order matters: ``/{patient_id}/prescriptions`` and
``/{patient_id}/side-effects`` are declared *before* ``/{patient_id}`` so the
sub-resource paths win over the catch-all profile fetch.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.patient_conditions import (
    PatientConditionCreate,
    PatientConditionPayload,
    PatientConditionUpdate,
)
from app.schemas.patient_insurances import PatientInsurancePayload
from app.schemas.patients import RxHistoryPage
from app.services.pharmacy import find_pharmacy_by_name
from app.services.pharmapi import pharmapi_get_patient_insurances
from app.utils.environment import is_mock_pharmapi

from ..db.models.patient import Patient
from ..db.session import get_session
from ..deps import get_current_user
from ..services.patients import (
    adr_history,
    conditions,
    create_condition,
    deactivate_condition,
    get_condition,
    recent_patients,
    resolve,
    rx_history_page,
    search_patients,
    update_condition,
)

router = APIRouter(prefix="/patients", tags=["patients"])


@router.get("/{patient_id}/prescriptions", response_model=RxHistoryPage)
async def get_patient_prescriptions(
    patient_id: str,
    page: int = Query(0, ge=0, description="Page number (0-indexed)"),
    size: int = Query(50, ge=1, le=200, description="Results per page"),
    current: dict = Depends(get_current_user),
):
    """
    Paginated executed prescription history for a patient, sourced from ΗΔΥΚΑ.

    Returns cross-pharmacy history using the patient's AMKA. When error 609
    prevents access (pharmacy permission not yet enabled by ΗΔΥΚΑ), returns
    an empty page with `blocked: true` rather than an error.
    """
    profile = await resolve(patient_id)
    if profile is None:
        raise HTTPException(status_code=404, detail=f"Patient {patient_id} not found")
    return await rx_history_page(profile["id"], page=page, size=size)


@router.get("/{patient_id}/side-effects")
async def get_patient_side_effects(patient_id: str, current: dict = Depends(get_current_user)):
    profile = await resolve(patient_id)
    if profile is None:
        raise HTTPException(status_code=404, detail=f"Patient {patient_id} not found")
    return {"items": adr_history(profile["id"])}


@router.get("/{patient_id}/conditions", response_model=list[PatientConditionPayload])
async def get_patient_conditions(
    patient_id: str,
    current: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    profile = await resolve(patient_id)
    if profile is None:
        raise HTTPException(status_code=404, detail=f"Patient {patient_id} not found")
    pharmacy = await find_pharmacy_by_name(session, current["pharmacy"])
    if pharmacy is None:
        raise HTTPException(status_code=403, detail="Pharmacy not found")
    return await conditions(session, profile["amka"], pharmacy.id)


@router.post(
    "/{patient_id}/conditions",
    response_model=PatientConditionPayload,
    status_code=201,
)
async def create_patient_condition(
    patient_id: str,
    body: PatientConditionCreate,
    current: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Record a new condition for a patient at the current pharmacy.

    `recordedBy` is the signed-in pharmacist; `pharmacyId` comes from the
    session (resolved the same way GET does), so the created row is visible to
    the GET list and picked up by the safety engine on the next evaluation.
    """
    profile = await resolve(patient_id)
    if profile is None:
        raise HTTPException(status_code=404, detail=f"Patient {patient_id} not found")
    pharmacy = await find_pharmacy_by_name(session, current["pharmacy"])
    if pharmacy is None:
        raise HTTPException(status_code=403, detail="Pharmacy not found")
    return await create_condition(
        session,
        amka=profile["amka"],
        condition_code=body.condition_code,
        name=body.name,
        severity=body.severity,
        notes=body.notes,
        recorded_by=uuid.UUID(current["pharmacist_id"]),
        pharmacy_id=pharmacy.id,
    )


@router.patch(
    "/{patient_id}/conditions/{condition_id}",
    response_model=PatientConditionPayload,
)
async def update_patient_condition(
    patient_id: str,
    condition_id: uuid.UUID,
    body: PatientConditionUpdate,
    current: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Partial update — only the fields present in the body are changed."""
    profile = await resolve(patient_id)
    if profile is None:
        raise HTTPException(status_code=404, detail=f"Patient {patient_id} not found")
    pharmacy = await find_pharmacy_by_name(session, current["pharmacy"])
    if pharmacy is None:
        raise HTTPException(status_code=403, detail="Pharmacy not found")
    condition = await get_condition(session, condition_id, profile["amka"], pharmacy.id)
    if condition is None:
        raise HTTPException(status_code=404, detail=f"Condition {condition_id} not found")
    fields = body.model_dump(exclude_unset=True)
    if not fields:
        return condition
    return await update_condition(session, condition, fields=fields)


@router.delete(
    "/{patient_id}/conditions/{condition_id}",
    response_model=PatientConditionPayload,
)
async def delete_patient_condition(
    patient_id: str,
    condition_id: uuid.UUID,
    current: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Soft delete — flips active=false so the row stays for audit but drops
    out of the GET list and the safety engine."""
    profile = await resolve(patient_id)
    if profile is None:
        raise HTTPException(status_code=404, detail=f"Patient {patient_id} not found")
    pharmacy = await find_pharmacy_by_name(session, current["pharmacy"])
    if pharmacy is None:
        raise HTTPException(status_code=403, detail="Pharmacy not found")
    condition = await get_condition(session, condition_id, profile["amka"], pharmacy.id)
    if condition is None:
        raise HTTPException(status_code=404, detail=f"Condition {condition_id} not found")
    return await deactivate_condition(session, condition)


@router.get("/{patient_id}/insurances", response_model=list[PatientInsurancePayload])
async def get_patient_insurances(patient_id: str, current: dict = Depends(get_current_user)):
    profile = await resolve(patient_id)
    if profile is None:
        raise HTTPException(status_code=404, detail=f"Patient {patient_id} not found")
    if is_mock_pharmapi():
        return []
    return await pharmapi_get_patient_insurances(
        amka=profile.get("amka"),
        ekaa=profile.get("ekaa"),
    )


def _intolerance_names(profile: dict | None) -> list[str]:
    """Distinct intolerance substance names from a stored patient profile.
    ΗΔΥΚΑ lists one row per recorded reaction — the same substance repeats; the
    chips only need distinct substances."""
    out: list[str] = []
    for item in (profile or {}).get("intolerances") or []:
        if isinstance(item, dict):
            name = item.get("activeSubstance") or item.get("name")
        else:
            name = item if isinstance(item, str) else None
        if name and str(name) not in out:
            out.append(str(name))
    return out


def _registry_row(p: Patient) -> dict:
    """A scanned-registry Patient → the chip/result shape the frontend renders
    (matches the mock directory: amka/name/age/sex/intolerances)."""
    return {
        "amka": p.amka,
        "name": p.name or "Άγνωστος",
        "age": p.age,
        "sex": p.sex,
        "intolerances": _intolerance_names(p.profile),
    }


@router.get("/recent")
async def get_recent_patients(
    current: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Recently-seen patients for the Patients landing-page chips.

    Declared before ``/{patient_id}`` so the static path wins over the
    catch-all profile fetch. Mock mode keeps the curated fixture; live mode
    reads the local patient registry that every barcode scan upserts
    (services/scan_log.py) — ΗΔΥΚΑ has no "my patients" feed to pull.
    """
    if is_mock_pharmapi():
        return recent_patients()

    pharmacy = await find_pharmacy_by_name(session, current["pharmacy"])
    if pharmacy is None:
        return []
    rows = await session.scalars(
        select(Patient)
        .where(Patient.pharmacy_id == pharmacy.id)
        .order_by(Patient.last_seen_at.desc())
        .limit(6)
    )
    return [_registry_row(p) for p in rows]


@router.get("/search")
async def search_patients_route(
    q: str = Query(..., min_length=1),
    current: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Name / AMKA substring search.

    Mock: the curated directory. Live: the local scanned-patient registry that
    every barcode scan upserts (services/scan_log.py) — ΗΔΥΚΑ has no name-search
    endpoint, so this searches patients THIS pharmacy has already scanned (AMKA
    always matches; name matches where a scan captured one). No 501.
    """
    if is_mock_pharmapi():
        return search_patients(q)

    pharmacy = await find_pharmacy_by_name(session, current["pharmacy"])
    if pharmacy is None:
        return []
    like = f"%{q.strip()}%"
    rows = await session.scalars(
        select(Patient)
        .where(
            Patient.pharmacy_id == pharmacy.id,
            or_(Patient.name.ilike(like), Patient.amka.ilike(like)),
        )
        .order_by(Patient.last_seen_at.desc())
        .limit(20)
    )
    return [_registry_row(p) for p in rows]


@router.get("/{patient_id}")
async def get_patient(patient_id: str, current: dict = Depends(get_current_user)):
    profile = await resolve(patient_id)
    if profile is None:
        raise HTTPException(status_code=404, detail=f"Patient {patient_id} not found")
    return profile
