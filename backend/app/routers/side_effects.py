"""Pharmacovigilance / adverse drug reaction reports."""

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query

from ..deps import get_current_user
from ..services.side_effects import (
    MOCK_SIDE_EFFECTS,
    SEVERITY_RANK,
    STATUS_RANK,
    next_status,
    stats,
)

router = APIRouter(prefix="/side-effects", tags=["side-effects"])


@router.get("")
async def list_side_effects(
    q: str | None = Query(None, description="Free-text search across patient, drug, symptom."),
    sort: str | None = Query("date", description="date | severity | status"),
    current: dict = Depends(get_current_user),
):
    items = list(MOCK_SIDE_EFFECTS)
    if q:
        needle = q.lower().strip()
        items = [
            r
            for r in items
            if needle in r["patientName"].lower()
            or needle in r["drugName"].lower()
            or needle in r["symptom"].lower()
        ]
    sort_key = (sort or "date").lower()
    if sort_key == "severity":
        items.sort(
            key=lambda r: (SEVERITY_RANK.get(r["severity"], -1), r["reportedAt"]), reverse=True
        )
    elif sort_key == "status":
        items.sort(key=lambda r: (STATUS_RANK.get(r["status"], -1), r["reportedAt"]), reverse=True)
    else:
        items.sort(key=lambda r: r["reportedAt"], reverse=True)
    return {"items": items, "stats": stats()}


@router.post("/{report_id}/flag")
async def flag_side_effect(report_id: str, current: dict = Depends(get_current_user)):
    """Advance the report's pharmacovigilance status one step (PENDING_REVIEW → ESCALATED → EOF_REPORTED)."""
    rec = next((r for r in MOCK_SIDE_EFFECTS if r["id"] == report_id), None)
    if rec is None:
        raise HTTPException(status_code=404, detail=f"Side-effect report {report_id} not found")
    previous = rec["status"]
    rec["status"] = next_status(previous)
    rec["lastFlaggedAt"] = datetime.now(UTC).isoformat()
    rec["lastFlaggedBy"] = current["email"]
    return {"success": True, "id": report_id, "previousStatus": previous, "status": rec["status"]}
