"""Pharmacist account management — list and activate/deactivate.

Pharmacists self-onboard via the invitation flow, so there is no create
endpoint here. Deactivating sets `active=False`; /auth/login and
get_current_user already reject inactive pharmacists, so it locks out at once.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...db.models.pharmacist import Pharmacist
from ...db.session import get_session
from ...deps import get_current_staff
from ...schemas.admin import PharmacistListResponse, PharmacistOut
from ...services.audit import write_staff_audit

router = APIRouter()


@router.get("/pharmacists", response_model=PharmacistListResponse)
async def list_pharmacists(
    current: dict = Depends(get_current_staff),
    db: AsyncSession = Depends(get_session),
    q: str | None = Query(None, description="name / email substring"),
    active: bool | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> PharmacistListResponse:
    conds = []
    if q:
        conds.append(
            or_(Pharmacist.full_name.ilike(f"%{q}%"), Pharmacist.email.ilike(f"%{q}%"))
        )
    if active is not None:
        conds.append(Pharmacist.active.is_(active))
    total = await db.scalar(select(func.count()).select_from(Pharmacist).where(*conds))
    rows = (
        await db.scalars(
            select(Pharmacist)
            .where(*conds)
            .order_by(Pharmacist.full_name)
            .limit(limit)
            .offset(offset)
        )
    ).all()
    return PharmacistListResponse(
        items=[PharmacistOut.model_validate(r) for r in rows], total=total or 0
    )


async def _set_active(
    pharmacist_id: uuid.UUID,
    active: bool,
    current: dict,
    request: Request,
    db: AsyncSession,
) -> PharmacistOut:
    pharmacist = await db.get(Pharmacist, pharmacist_id)
    if pharmacist is None:
        raise HTTPException(404, "Pharmacist not found")
    pharmacist.active = active
    write_staff_audit(
        db,
        staff_id=current["staff_id"],
        action="pharmacist.activate" if active else "pharmacist.deactivate",
        resource_type="pharmacist",
        resource_id=str(pharmacist.id),
        request=request,
    )
    await db.commit()
    await db.refresh(pharmacist)
    return PharmacistOut.model_validate(pharmacist)


@router.post("/pharmacists/{pharmacist_id}/activate", response_model=PharmacistOut)
async def activate_pharmacist(
    pharmacist_id: uuid.UUID,
    request: Request,
    current: dict = Depends(get_current_staff),
    db: AsyncSession = Depends(get_session),
) -> PharmacistOut:
    return await _set_active(pharmacist_id, True, current, request, db)


@router.post("/pharmacists/{pharmacist_id}/deactivate", response_model=PharmacistOut)
async def deactivate_pharmacist(
    pharmacist_id: uuid.UUID,
    request: Request,
    current: dict = Depends(get_current_staff),
    db: AsyncSession = Depends(get_session),
) -> PharmacistOut:
    return await _set_active(pharmacist_id, False, current, request, db)
