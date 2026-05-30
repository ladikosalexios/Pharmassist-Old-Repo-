"""Patient profile + per-patient prescription / ADR history.

Order matters: ``/{patient_id}/prescriptions`` and
``/{patient_id}/side-effects`` are declared *before* ``/{patient_id}`` so the
sub-resource paths win over the catch-all profile fetch.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.patient_conditions import PatientConditionPayload
from app.schemas.patient_insurances import PatientInsurancePayload
from app.services.pharmacy import find_pharmacy_by_name
from app.services.pharmapi import pharmapi_get_patient_insurances
from app.utils.environment import is_mock_pharmapi

from ..db.session import get_session
from ..deps import get_current_user
from ..services.patients import adr_history, conditions, resolve, rx_history_page

router = APIRouter(prefix="/patients", tags=["patients"])


@router.get("/{patient_id}/prescriptions")
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
    return await conditions(session, profile["amka"], pharmacy.id)


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


@router.get("/{patient_id}")
async def get_patient(patient_id: str, current: dict = Depends(get_current_user)):
    profile = await resolve(patient_id)
    if profile is None:
        raise HTTPException(status_code=404, detail=f"Patient {patient_id} not found")
    return profile
