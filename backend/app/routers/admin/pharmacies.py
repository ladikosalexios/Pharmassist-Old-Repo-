"""Pharmacy management — list, view, create, and edit pharmacies."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...db.models.pharmacy import Pharmacy
from ...db.session import get_session
from ...deps import get_current_staff
from ...schemas.admin import (
    PharmacyCreate,
    PharmacyListResponse,
    PharmacyOut,
    PharmacyUpdate,
)
from ...services.audit import write_staff_audit

router = APIRouter()


@router.get("/pharmacies", response_model=PharmacyListResponse)
async def list_pharmacies(
    current: dict = Depends(get_current_staff),
    db: AsyncSession = Depends(get_session),
    q: str | None = Query(None, description="name / city substring"),
    active: bool | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> PharmacyListResponse:
    conds = []
    if q:
        conds.append(or_(Pharmacy.name.ilike(f"%{q}%"), Pharmacy.city.ilike(f"%{q}%")))
    if active is not None:
        conds.append(Pharmacy.active.is_(active))
    total = await db.scalar(select(func.count()).select_from(Pharmacy).where(*conds))
    rows = (
        await db.scalars(
            select(Pharmacy).where(*conds).order_by(Pharmacy.name).limit(limit).offset(offset)
        )
    ).all()
    return PharmacyListResponse(
        items=[PharmacyOut.model_validate(r) for r in rows], total=total or 0
    )


@router.get("/pharmacies/{pharmacy_id}", response_model=PharmacyOut)
async def get_pharmacy(
    pharmacy_id: uuid.UUID,
    current: dict = Depends(get_current_staff),
    db: AsyncSession = Depends(get_session),
) -> PharmacyOut:
    pharmacy = await db.get(Pharmacy, pharmacy_id)
    if pharmacy is None:
        raise HTTPException(404, "Pharmacy not found")
    return PharmacyOut.model_validate(pharmacy)


@router.post("/pharmacies", response_model=PharmacyOut, status_code=201)
async def create_pharmacy(
    body: PharmacyCreate,
    request: Request,
    current: dict = Depends(get_current_staff),
    db: AsyncSession = Depends(get_session),
) -> PharmacyOut:
    pharmacy = Pharmacy(**body.model_dump())
    db.add(pharmacy)
    await db.flush()  # assign pharmacy.id before the audit row references it
    write_staff_audit(
        db,
        staff_id=current["staff_id"],
        action="pharmacy.create",
        resource_type="pharmacy",
        resource_id=str(pharmacy.id),
        pharmacy_id=str(pharmacy.id),
        request_body={"name": pharmacy.name},
        request=request,
    )
    await db.commit()
    await db.refresh(pharmacy)
    return PharmacyOut.model_validate(pharmacy)


@router.patch("/pharmacies/{pharmacy_id}", response_model=PharmacyOut)
async def update_pharmacy(
    pharmacy_id: uuid.UUID,
    body: PharmacyUpdate,
    request: Request,
    current: dict = Depends(get_current_staff),
    db: AsyncSession = Depends(get_session),
) -> PharmacyOut:
    pharmacy = await db.get(Pharmacy, pharmacy_id)
    if pharmacy is None:
        raise HTTPException(404, "Pharmacy not found")
    changes = body.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(pharmacy, field, value)
    write_staff_audit(
        db,
        staff_id=current["staff_id"],
        action="pharmacy.update",
        resource_type="pharmacy",
        resource_id=str(pharmacy.id),
        pharmacy_id=str(pharmacy.id),
        request_body={"fields": sorted(changes.keys())},
        request=request,
    )
    await db.commit()
    await db.refresh(pharmacy)
    return PharmacyOut.model_validate(pharmacy)
