"""Invitation management — list, create, and revoke onboarding invites."""

import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ...db.models.invitation import INVITE_EXPIRE_DAYS, Invitation
from ...db.models.pharmacist import Pharmacist
from ...db.models.pharmacy import Pharmacy
from ...db.session import get_session
from ...deps import get_current_staff
from ...schemas.admin import InvitationListResponse, InvitationOut
from ...schemas.auth import InviteRequest, InviteResponse
from ...services.audit import write_staff_audit

router = APIRouter()


def _status(inv: Invitation, now: datetime) -> str:
    if inv.accepted_at is not None:
        return "accepted"
    if now > inv.expires_at:
        return "expired"
    return "pending"


def _inviter_name(inv: Invitation) -> str | None:
    if inv.inviter_staff is not None:
        return inv.inviter_staff.full_name
    if inv.inviter is not None:
        return inv.inviter.full_name
    return None


def _to_out(inv: Invitation, now: datetime) -> InvitationOut:
    return InvitationOut(
        id=inv.id,
        email=inv.email,
        pharmacy_id=inv.pharmacy_id,
        pharmacy_name=inv.pharmacy.name,
        status=_status(inv, now),
        invite_url=f"/accept-invite?token={inv.token}",
        invited_by_name=_inviter_name(inv),
        expires_at=inv.expires_at,
        accepted_at=inv.accepted_at,
        created_at=inv.created_at,
    )


@router.get("/invitations", response_model=InvitationListResponse)
async def list_invitations(
    current: dict = Depends(get_current_staff),
    db: AsyncSession = Depends(get_session),
    status: str | None = Query(None, description="pending | accepted | expired"),
    q: str | None = Query(None, description="email substring"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> InvitationListResponse:
    now = datetime.now(UTC)
    conds = []
    if q:
        conds.append(Invitation.email.ilike(f"%{q}%"))
    if status == "accepted":
        conds.append(Invitation.accepted_at.is_not(None))
    elif status == "pending":
        conds.append(Invitation.accepted_at.is_(None))
        conds.append(Invitation.expires_at > now)
    elif status == "expired":
        conds.append(Invitation.accepted_at.is_(None))
        conds.append(Invitation.expires_at <= now)

    total = await db.scalar(select(func.count()).select_from(Invitation).where(*conds))
    rows = (
        await db.scalars(
            select(Invitation)
            .where(*conds)
            .options(
                selectinload(Invitation.pharmacy),
                selectinload(Invitation.inviter),
                selectinload(Invitation.inviter_staff),
            )
            .order_by(Invitation.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
    ).all()
    return InvitationListResponse(items=[_to_out(r, now) for r in rows], total=total or 0)


@router.post("/invitations", response_model=InviteResponse, status_code=201)
async def create_invitation(
    body: InviteRequest,
    request: Request,
    current: dict = Depends(get_current_staff),
    db: AsyncSession = Depends(get_session),
) -> InviteResponse:
    """Create an onboarding invitation for a pharmacist at a pharmacy."""
    pharmacy = await db.get(Pharmacy, body.pharmacy_id)
    if not pharmacy:
        raise HTTPException(404, "Pharmacy not found")
    existing = await db.scalar(select(Pharmacist).where(Pharmacist.email == body.email))
    if existing:
        raise HTTPException(409, "A pharmacist with this email already exists")

    now = datetime.now(UTC)
    invitation = Invitation(
        token=Invitation.generate_token(),
        email=body.email,
        pharmacy_id=pharmacy.id,
        invited_by_staff_id=uuid.UUID(current["staff_id"]),
        expires_at=now + timedelta(days=INVITE_EXPIRE_DAYS),
    )
    db.add(invitation)
    await db.flush()  # assign invitation.id before the audit row references it
    write_staff_audit(
        db,
        staff_id=current["staff_id"],
        action="invitation.create",
        resource_type="invitation",
        resource_id=str(invitation.id),
        pharmacy_id=str(pharmacy.id),
        request_body={"email": body.email},
        request=request,
    )
    await db.commit()
    await db.refresh(invitation)

    invite_url = f"/accept-invite?token={invitation.token}"
    print(f"[INVITE] {body.email} → {invite_url} (expires {invitation.expires_at})")
    return InviteResponse(
        invite_url=invite_url,
        expires_at=invitation.expires_at.isoformat(),
        email=invitation.email,
    )


@router.post("/invitations/{invitation_id}/revoke")
async def revoke_invitation(
    invitation_id: uuid.UUID,
    request: Request,
    current: dict = Depends(get_current_staff),
    db: AsyncSession = Depends(get_session),
) -> dict:
    """Revoke a pending invitation by expiring it immediately."""
    invitation = await db.get(Invitation, invitation_id)
    if invitation is None:
        raise HTTPException(404, "Invitation not found")
    if invitation.accepted_at is not None:
        raise HTTPException(409, "Invitation has already been accepted")

    invitation.expires_at = datetime.now(UTC)
    write_staff_audit(
        db,
        staff_id=current["staff_id"],
        action="invitation.revoke",
        resource_type="invitation",
        resource_id=str(invitation.id),
        request=request,
    )
    await db.commit()
    return {"ok": True}
