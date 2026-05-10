"""Pharmacovigilance / adverse drug reaction reports."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.adr_event import AdrEvent
from app.db.models.adr_report import AdrReport
from app.db.models.pharmacist import Pharmacist
from app.db.session import get_session

from ..deps import get_current_user
from ..services.side_effects import (
    SEVERITY_RANK,
    STATUS_RANK,
    get_adr_report_dict,
    next_status,
    stats,
)

router = APIRouter(prefix="/side-effects", tags=["side-effects"])


@router.get("")
async def list_side_effects(
    q: str | None = Query(None, description="Free-text search across patient, drug, symptom."),
    sort: str | None = Query("date", description="date | severity | status"),
    current: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    items = await AdrReport.get_all(session)
    if q:
        needle = q.lower().strip()
        items = [
            r
            for r in items
            if needle in r.patient_name.lower()
            or needle in r.medicine_name.lower()
            or needle in r.symptom_description.lower()
        ]
    sort_key = (sort or "date").lower()
    if sort_key == "severity":
        items.sort(
            key=lambda r: (SEVERITY_RANK.get(r["severity"], -1), r["reportedAt"]),
            reverse=True,
        )
    elif sort_key == "status":
        items.sort(
            key=lambda r: (STATUS_RANK.get(r.status, -1), r.reported_at),
            reverse=True,
        )
    else:
        items.sort(key=lambda r: r.reported_at, reverse=True)
    return {
        "items": [get_adr_report_dict(i) for i in items],
        "stats": await stats(session),
    }


@router.post("/{report_id}/flag")
async def flag_side_effect(
    report_id: str,
    current: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Advance the report's pharmacovigilance status one step (PENDING_REVIEW → ESCALATED → EOF_REPORTED)."""
    rec = await AdrReport.get_by_id(session, report_id)
    if rec is None:
        raise HTTPException(status_code=404, detail=f"Side-effect report {report_id} not found")
    previous = rec.status
    rec.status = next_status(previous)

    # create the associated adr_event
    pharmacist_id = await session.scalar(
        select(Pharmacist.id).where(func.lower(Pharmacist.email) == current["email"].lower())
    )
    if pharmacist_id is None:
        raise HTTPException(401, detail="Pharmacist not found")
    session.add(
        AdrEvent(
            adr_id=rec.id,
            actor_id=pharmacist_id,
            event_type="STATUS_CHANGED",
            from_status=previous,
            to_status=rec.status,
        )
    )

    await session.commit()
    return {
        "success": True,
        "id": report_id,
        "previousStatus": previous,
        "status": rec.status,
    }
