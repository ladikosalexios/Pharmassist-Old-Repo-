"""Onboarding — create a new pharmacy and invite its first pharmacist.

A single staff action: the form supplies the new pharmacy's details plus the
pharmacist's email; this creates the Pharmacy and the Invitation together. The
pharmacist then completes signup through the existing /auth/accept-invite flow.
"""

import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...db.models.invitation import INVITE_EXPIRE_DAYS, Invitation
from ...db.models.pharmacist import Pharmacist
from ...db.models.pharmacy import Pharmacy
from ...db.session import get_session
from ...deps import get_current_staff
from ...schemas.admin import OnboardRequest
from ...schemas.auth import InviteResponse
from ...services.audit import write_staff_audit

router = APIRouter()


@router.post("/invitations", response_model=InviteResponse, status_code=201)
async def onboard_pharmacy(
    body: OnboardRequest,
    request: Request,
    current: dict = Depends(get_current_staff),
    db: AsyncSession = Depends(get_session),
) -> InviteResponse:
    """Create a new pharmacy and an onboarding invite for its first pharmacist."""
    existing = await db.scalar(
        select(Pharmacist).where(Pharmacist.email == body.pharmacist_email)
    )
    if existing:
        raise HTTPException(409, "A pharmacist with this email already exists")

    pharmacy = Pharmacy(**body.pharmacy.model_dump())
    db.add(pharmacy)
    await db.flush()  # assign pharmacy.id before it is referenced below

    now = datetime.now(UTC)
    invitation = Invitation(
        token=Invitation.generate_token(),
        email=body.pharmacist_email,
        pharmacy_id=pharmacy.id,
        invited_by_staff_id=uuid.UUID(current["staff_id"]),
        expires_at=now + timedelta(days=INVITE_EXPIRE_DAYS),
    )
    db.add(invitation)
    await db.flush()  # assign invitation.id before the audit row references it

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
    write_staff_audit(
        db,
        staff_id=current["staff_id"],
        action="invitation.create",
        resource_type="invitation",
        resource_id=str(invitation.id),
        pharmacy_id=str(pharmacy.id),
        request_body={"email": body.pharmacist_email},
        request=request,
    )
    await db.commit()
    await db.refresh(invitation)

    invite_url = f"/accept-invite?token={invitation.token}"
    print(f"[INVITE] {body.pharmacist_email} → {invite_url} (expires {invitation.expires_at})")
    return InviteResponse(
        invite_url=invite_url,
        expires_at=invitation.expires_at.isoformat(),
        email=invitation.email,
    )
