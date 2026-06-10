"""Admin-only endpoints — pharmacist invitations and catalogue management."""

import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.models.catalog_sync_run import CatalogSyncRun
from ..db.models.invitation import INVITE_EXPIRE_DAYS, Invitation
from ..db.models.pharmacist import Pharmacist
from ..db.models.pharmacy import Pharmacy
from ..db.session import get_session
from ..deps import get_current_user
from ..schemas.admin import (
    CatalogCoveragePayload,
    CatalogSyncRunPayload,
    SyncDrugCatalogRequest,
    SyncDrugCatalogResponse,
    SyncDrugCatalogStatusResponse,
)
from ..schemas.auth import InviteRequest, InviteResponse
from ..services.drug_catalog import catalog_coverage, run_sync

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


@router.post("/sync-drug-catalog", response_model=SyncDrugCatalogResponse, status_code=202)
async def trigger_drug_catalog_sync(
    body: SyncDrugCatalogRequest,
    background_tasks: BackgroundTasks,
    current: dict = Depends(get_current_user),
) -> SyncDrugCatalogResponse:
    """Trigger a drug catalogue sync from Pharmapi masterdata. Admin only.

    Returns 202 immediately; the sync runs in the background.
    Check container logs for fetched/upserted/skipped counts and any errors.
    Use 'since' for incremental updates (omit for a full re-sync).
    """
    if current.get("role") != "admin":
        raise HTTPException(403, "Admin role required")
    background_tasks.add_task(
        run_sync,
        body.since.isoformat() if body.since else None,
        f"admin:{current.get('email') or current.get('pharmacist_id')}",
    )
    return SyncDrugCatalogResponse(
        message="Sync started — poll GET /admin/sync-drug-catalog/status for the outcome."
    )


@router.get("/sync-drug-catalog/status", response_model=SyncDrugCatalogStatusResponse)
async def drug_catalog_sync_status(
    current: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
) -> SyncDrugCatalogStatusResponse:
    """Last sync runs + formulary data-quality coverage counts. Admin only.

    The FT-3 onboarding gate reads this after the first full production sync:
    a recent `success` run AND with_coverage ≈ total_active means the strict
    ΕΟΠΥΥ coverage filter operates on real data rather than tri-state NULLs.
    """
    if current.get("role") != "admin":
        raise HTTPException(403, "Admin role required")
    runs = (
        await db.scalars(
            select(CatalogSyncRun).order_by(CatalogSyncRun.started_at.desc()).limit(10)
        )
    ).all()
    coverage = await catalog_coverage(db)
    return SyncDrugCatalogStatusResponse(
        runs=[CatalogSyncRunPayload.model_validate(r) for r in runs],
        coverage=CatalogCoveragePayload(**coverage),
    )
