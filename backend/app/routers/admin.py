"""Admin-only endpoints — pharmacist invitations."""

import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.models.invitation import INVITE_EXPIRE_DAYS, Invitation
from ..db.models.pharmacist import Pharmacist
from ..db.models.pharmacy import Pharmacy
from ..db.session import get_session
from ..deps import get_current_user
from ..schemas.auth import InviteRequest, InviteResponse

router = APIRouter(prefix="/admin", tags=["admin"])


@router.post("/invite", response_model=InviteResponse)
async def create_invite(
    body: InviteRequest,
    current: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
) -> InviteResponse:
    """Create an invitation for a pharmacist to onboard at a given pharmacy."""
    # 1. Enforce admin role
    if current.get("role") != "admin":
        raise HTTPException(403, "Admin role required")

    # 2. Verify pharmacy exists
    pharmacy = await db.get(Pharmacy, body.pharmacy_id)
    if not pharmacy:
        raise HTTPException(404, "Pharmacy not found")

    # 3. Check no existing pharmacist already has this email
    existing = await db.scalar(select(Pharmacist).where(Pharmacist.email == body.email))
    if existing:
        raise HTTPException(409, "A pharmacist with this email already exists")

    # 4. Create invitation
    now = datetime.now(UTC)
    invitation = Invitation(
        token=Invitation.generate_token(),
        email=body.email,
        pharmacy_id=pharmacy.id,
        invited_by=uuid.UUID(current["pharmacist_id"]),
        expires_at=now + timedelta(days=INVITE_EXPIRE_DAYS),
    )
    db.add(invitation)
    await db.commit()
    await db.refresh(invitation)

    # 5. v1: log the URL to stdout (no email service yet).
    # TODO(security): the token is a secret — printing it to stdout leaks it
    # into container/aggregated logs. Replace with an email service before prod.
    invite_url = f"/accept-invite?token={invitation.token}"
    print(f"[INVITE] {body.email} → {invite_url} (expires {invitation.expires_at})")

    return InviteResponse(
        invite_url=invite_url,
        expires_at=invitation.expires_at.isoformat(),
        email=invitation.email,
    )
