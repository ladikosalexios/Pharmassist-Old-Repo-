"""Staff account management — list, create, and activate/deactivate staff."""

import uuid

import bcrypt
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...db.models.staff_user import StaffUser
from ...db.session import get_session
from ...deps import get_current_staff
from ...schemas.admin import StaffCreate, StaffListResponse, StaffOut
from ...services.audit import write_staff_audit

router = APIRouter()


@router.get("/staff", response_model=StaffListResponse)
async def list_staff(
    current: dict = Depends(get_current_staff),
    db: AsyncSession = Depends(get_session),
    q: str | None = Query(None, description="name / email substring"),
    active: bool | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> StaffListResponse:
    conds = []
    if q:
        conds.append(
            or_(StaffUser.full_name.ilike(f"%{q}%"), StaffUser.email.ilike(f"%{q}%"))
        )
    if active is not None:
        conds.append(StaffUser.active.is_(active))
    total = await db.scalar(select(func.count()).select_from(StaffUser).where(*conds))
    rows = (
        await db.scalars(
            select(StaffUser)
            .where(*conds)
            .order_by(StaffUser.full_name)
            .limit(limit)
            .offset(offset)
        )
    ).all()
    return StaffListResponse(
        items=[StaffOut.model_validate(r) for r in rows], total=total or 0
    )


@router.post("/staff", response_model=StaffOut, status_code=201)
async def create_staff(
    body: StaffCreate,
    request: Request,
    current: dict = Depends(get_current_staff),
    db: AsyncSession = Depends(get_session),
) -> StaffOut:
    existing = await db.scalar(select(StaffUser).where(StaffUser.email == body.email))
    if existing:
        raise HTTPException(409, "A staff account with this email already exists")
    hashed = bcrypt.hashpw(body.password.encode(), bcrypt.gensalt(rounds=12)).decode()
    staff = StaffUser(email=body.email, password_hash=hashed, full_name=body.full_name)
    db.add(staff)
    await db.flush()  # assign staff.id before the audit row references it
    write_staff_audit(
        db,
        staff_id=current["staff_id"],
        action="staff.create",
        resource_type="staff",
        resource_id=str(staff.id),
        request_body={"email": body.email},
        request=request,
    )
    await db.commit()
    await db.refresh(staff)
    return StaffOut.model_validate(staff)


async def _set_active(
    staff_id: uuid.UUID,
    active: bool,
    current: dict,
    request: Request,
    db: AsyncSession,
) -> StaffOut:
    # A staff member cannot lock themselves out — create_staff.py is the
    # only recovery path if every account is deactivated.
    if not active and str(staff_id) == current["staff_id"]:
        raise HTTPException(400, "You cannot deactivate your own account")
    staff = await db.get(StaffUser, staff_id)
    if staff is None:
        raise HTTPException(404, "Staff account not found")
    staff.active = active
    write_staff_audit(
        db,
        staff_id=current["staff_id"],
        action="staff.activate" if active else "staff.deactivate",
        resource_type="staff",
        resource_id=str(staff.id),
        request=request,
    )
    await db.commit()
    await db.refresh(staff)
    return StaffOut.model_validate(staff)


@router.post("/staff/{staff_id}/activate", response_model=StaffOut)
async def activate_staff(
    staff_id: uuid.UUID,
    request: Request,
    current: dict = Depends(get_current_staff),
    db: AsyncSession = Depends(get_session),
) -> StaffOut:
    return await _set_active(staff_id, True, current, request, db)


@router.post("/staff/{staff_id}/deactivate", response_model=StaffOut)
async def deactivate_staff(
    staff_id: uuid.UUID,
    request: Request,
    current: dict = Depends(get_current_staff),
    db: AsyncSession = Depends(get_session),
) -> StaffOut:
    return await _set_active(staff_id, False, current, request, db)
