"""Audit-log viewer — read-only window over the audit_log table.

The table is append-only; this router only ever reads. Actor and pharmacy
names are resolved with batched lookups (audit_log has no ORM relationships).
"""

from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...db.models.audit_log import AuditLog
from ...db.models.pharmacist import Pharmacist
from ...db.models.pharmacy import Pharmacy
from ...db.models.staff_user import StaffUser
from ...db.session import get_session
from ...deps import get_current_staff
from ...schemas.admin import AuditLogListResponse, AuditLogOut

router = APIRouter()


async def _name_map(db: AsyncSession, model, ids: set, name_attr: str) -> dict:
    """{id: display_name} for the given model, or {} when there are no ids."""
    if not ids:
        return {}
    rows = (await db.scalars(select(model).where(model.id.in_(ids)))).all()
    return {row.id: getattr(row, name_attr) for row in rows}


@router.get("/audit-logs", response_model=AuditLogListResponse)
async def list_audit_logs(
    current: dict = Depends(get_current_staff),
    db: AsyncSession = Depends(get_session),
    action: str | None = Query(None),
    resource_type: str | None = Query(None),
    date_from: datetime | None = Query(None),
    date_to: datetime | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> AuditLogListResponse:
    conds = []
    if action:
        conds.append(AuditLog.action == action)
    if resource_type:
        conds.append(AuditLog.resource_type == resource_type)
    if date_from:
        conds.append(AuditLog.occurred_at >= date_from)
    if date_to:
        conds.append(AuditLog.occurred_at <= date_to)

    total = await db.scalar(select(func.count()).select_from(AuditLog).where(*conds))
    rows = (
        await db.scalars(
            select(AuditLog)
            .where(*conds)
            .order_by(AuditLog.occurred_at.desc(), AuditLog.id.desc())
            .limit(limit)
            .offset(offset)
        )
    ).all()

    staff_names = await _name_map(
        db, StaffUser, {r.staff_id for r in rows if r.staff_id}, "full_name"
    )
    pharmacist_names = await _name_map(
        db, Pharmacist, {r.pharmacist_id for r in rows if r.pharmacist_id}, "full_name"
    )
    pharmacy_names = await _name_map(
        db, Pharmacy, {r.pharmacy_id for r in rows if r.pharmacy_id}, "name"
    )

    items = []
    for r in rows:
        if r.staff_id:
            actor_type, actor_name = "staff", staff_names.get(r.staff_id)
        elif r.pharmacist_id:
            actor_type, actor_name = "pharmacist", pharmacist_names.get(r.pharmacist_id)
        else:
            actor_type, actor_name = "system", None
        items.append(
            AuditLogOut(
                id=r.id,
                action=r.action,
                resource_type=r.resource_type,
                resource_id=r.resource_id,
                actor_type=actor_type,
                actor_name=actor_name,
                pharmacy_name=pharmacy_names.get(r.pharmacy_id) if r.pharmacy_id else None,
                response_code=r.response_code,
                ip_address=str(r.ip_address) if r.ip_address else None,
                request_body=r.request_body,
                occurred_at=r.occurred_at,
            )
        )
    return AuditLogListResponse(items=items, total=total or 0)
