"""Patient profile + per-patient prescription / ADR history.

Order matters: ``/{patient_id}/prescriptions`` and
``/{patient_id}/side-effects`` are declared *before* ``/{patient_id}`` so the
sub-resource paths win over the catch-all profile fetch.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.pharmacy import find_pharmacy_by_name

from ..db.session import get_session
from ..deps import get_current_user
from ..services.patients import adr_history, conditions, resolve, rx_history

router = APIRouter(prefix="/patients", tags=["patients"])


@router.get("/{patient_id}/prescriptions")
async def get_patient_prescriptions(patient_id: str, current: dict = Depends(get_current_user)):
    profile = await resolve(patient_id)
    if profile is None:
        raise HTTPException(status_code=404, detail=f"Patient {patient_id} not found")
    return {"items": rx_history(profile["id"])}


@router.get("/{patient_id}/side-effects")
async def get_patient_side_effects(patient_id: str, current: dict = Depends(get_current_user)):
    profile = await resolve(patient_id)
    if profile is None:
        raise HTTPException(status_code=404, detail=f"Patient {patient_id} not found")
    return {"items": adr_history(profile["id"])}


@router.get("/{patient_id}/conditions")
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


@router.get("/{patient_id}")
async def get_patient(patient_id: str, current: dict = Depends(get_current_user)):
    profile = await resolve(patient_id)
    if profile is None:
        raise HTTPException(status_code=404, detail=f"Patient {patient_id} not found")
    return profile
