"""Pharmacy views — read-only list and per-pharmacy operational detail.

Pharmacies are created through onboarding (see invitations.py); this router
only reads. The detail endpoint aggregates a pharmacy's operational records —
its pharmacists, its invitations, and its audit-log entries.
"""

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...db.models.audit_log import AuditLog
from ...db.models.invitation import Invitation
from ...db.models.pharmacist import Pharmacist
from ...db.models.pharmacist_pharmacy import PharmacistPharmacy
from ...db.models.pharmacy import Pharmacy
from ...db.models.staff_user import StaffUser
from ...db.session import get_session
from ...deps import get_current_staff
from ...schemas.admin import (
    AuditLogOut,
    InvitationOut,
    PharmacistOut,
    PharmacyDetail,
    PharmacyListItem,
    PharmacyListResponse,
    PharmacyOut,
)

router = APIRouter()


async def _name_map(db: AsyncSession, model, ids: set, name_attr: str) -> dict:
    """{id: display_name} for the given model, or {} when there are no ids."""
    if not ids:
        return {}
    rows = (await db.scalars(select(model).where(model.id.in_(ids)))).all()
    return {row.id: getattr(row, name_attr) for row in rows}


async def _pharmacist_counts(db: AsyncSession, pharmacy_ids: list) -> dict:
    if not pharmacy_ids:
        return {}
    rows = await db.execute(
        select(PharmacistPharmacy.pharmacy_id, func.count())
        .where(PharmacistPharmacy.pharmacy_id.in_(pharmacy_ids))
        .group_by(PharmacistPharmacy.pharmacy_id)
    )
    return dict(rows.all())


async def _pending_invite_counts(db: AsyncSession, pharmacy_ids: list) -> dict:
    if not pharmacy_ids:
        return {}
    now = datetime.now(UTC)
    rows = await db.execute(
        select(Invitation.pharmacy_id, func.count())
        .where(
            Invitation.pharmacy_id.in_(pharmacy_ids),
            Invitation.accepted_at.is_(None),
            Invitation.expires_at > now,
        )
        .group_by(Invitation.pharmacy_id)
    )
    return dict(rows.all())


def _invitation_status(inv: Invitation, now: datetime) -> str:
    if inv.accepted_at is not None:
        return "accepted"
    if now > inv.expires_at:
        return "expired"
    return "pending"


def _invitation_out(inv: Invitation, now: datetime) -> InvitationOut:
    return InvitationOut(
        id=inv.id,
        email=inv.email,
        status=_invitation_status(inv, now),
        invite_url=f"/accept-invite?token={inv.token}",
        expires_at=inv.expires_at,
        accepted_at=inv.accepted_at,
        created_at=inv.created_at,
    )


def _audit_out(row: AuditLog, staff_names: dict, pharmacist_names: dict) -> AuditLogOut:
    if row.staff_id:
        actor_type, actor_name = "staff", staff_names.get(row.staff_id)
    elif row.pharmacist_id:
        actor_type, actor_name = "pharmacist", pharmacist_names.get(row.pharmacist_id)
    else:
        actor_type, actor_name = "system", None
    return AuditLogOut(
        id=row.id,
        action=row.action,
        resource_type=row.resource_type,
        resource_id=row.resource_id,
        actor_type=actor_type,
        actor_name=actor_name,
        occurred_at=row.occurred_at,
    )


@router.get("/pharmacies", response_model=PharmacyListResponse)
async def list_pharmacies(
    current: dict = Depends(get_current_staff),
    db: AsyncSession = Depends(get_session),
    q: str | None = Query(None, description="name / city substring"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> PharmacyListResponse:
    conds = []
    if q:
        conds.append(or_(Pharmacy.name.ilike(f"%{q}%"), Pharmacy.city.ilike(f"%{q}%")))
    total = await db.scalar(select(func.count()).select_from(Pharmacy).where(*conds))
    rows = (
        await db.scalars(
            select(Pharmacy).where(*conds).order_by(Pharmacy.name).limit(limit).offset(offset)
        )
    ).all()
    ids = [p.id for p in rows]
    pharmacist_counts = await _pharmacist_counts(db, ids)
    pending_counts = await _pending_invite_counts(db, ids)
    items = [
        PharmacyListItem(
            id=p.id,
            name=p.name,
            city=p.city,
            pharmacist_count=pharmacist_counts.get(p.id, 0),
            pending_invite_count=pending_counts.get(p.id, 0),
        )
        for p in rows
    ]
    return PharmacyListResponse(items=items, total=total or 0)


@router.get("/pharmacies/{pharmacy_id}", response_model=PharmacyDetail)
async def get_pharmacy(
    pharmacy_id: uuid.UUID,
    current: dict = Depends(get_current_staff),
    db: AsyncSession = Depends(get_session),
) -> PharmacyDetail:
    pharmacy = await db.get(Pharmacy, pharmacy_id)
    if pharmacy is None:
        raise HTTPException(404, "Pharmacy not found")

    pharmacists = (
        await db.scalars(
            select(Pharmacist)
            .join(PharmacistPharmacy, PharmacistPharmacy.pharmacist_id == Pharmacist.id)
            .where(PharmacistPharmacy.pharmacy_id == pharmacy_id)
            .order_by(Pharmacist.full_name)
        )
    ).all()

    invitations = (
        await db.scalars(
            select(Invitation)
            .where(Invitation.pharmacy_id == pharmacy_id)
            .order_by(Invitation.created_at.desc())
        )
    ).all()

    audit_rows = (
        await db.scalars(
            select(AuditLog)
            .where(AuditLog.pharmacy_id == pharmacy_id)
            .order_by(AuditLog.occurred_at.desc(), AuditLog.id.desc())
            .limit(50)
        )
    ).all()
    staff_names = await _name_map(
        db, StaffUser, {r.staff_id for r in audit_rows if r.staff_id}, "full_name"
    )
    pharmacist_names = await _name_map(
        db, Pharmacist, {r.pharmacist_id for r in audit_rows if r.pharmacist_id}, "full_name"
    )

    now = datetime.now(UTC)
    return PharmacyDetail(
        pharmacy=PharmacyOut.model_validate(pharmacy),
        pharmacists=[PharmacistOut.model_validate(p) for p in pharmacists],
        invitations=[_invitation_out(inv, now) for inv in invitations],
        audit=[_audit_out(r, staff_names, pharmacist_names) for r in audit_rows],
    )
