"""Reference-data management — drug catalog and safety rules.

These tables drive the clinical safety engine and were previously editable
only by hand-editing scripts/seed_data.py and re-seeding. Soft-delete only
(the `active` flag) — rows are referenced by safety checks.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...db.models.drug_catalog import DrugCatalog
from ...db.models.safety_rule import SafetyRule
from ...db.session import get_session
from ...deps import get_current_staff
from ...schemas.admin import (
    DrugCreate,
    DrugListResponse,
    DrugOut,
    DrugUpdate,
    SafetyRuleCreate,
    SafetyRuleListResponse,
    SafetyRuleOut,
    SafetyRuleUpdate,
)
from ...services.audit import write_staff_audit

router = APIRouter()


# --- Drug catalog ---
@router.get("/drugs", response_model=DrugListResponse)
async def list_drugs(
    current: dict = Depends(get_current_staff),
    db: AsyncSession = Depends(get_session),
    q: str | None = Query(None, description="name / GNS-code substring"),
    active: bool | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> DrugListResponse:
    conds = []
    if q:
        like = f"%{q}%"
        conds.append(
            or_(
                DrugCatalog.name_gr.ilike(like),
                DrugCatalog.name_en.ilike(like),
                DrugCatalog.gns_code.ilike(like),
            )
        )
    if active is not None:
        conds.append(DrugCatalog.active.is_(active))
    total = await db.scalar(select(func.count()).select_from(DrugCatalog).where(*conds))
    rows = (
        await db.scalars(
            select(DrugCatalog)
            .where(*conds)
            .order_by(DrugCatalog.name_gr)
            .limit(limit)
            .offset(offset)
        )
    ).all()
    return DrugListResponse(items=[DrugOut.model_validate(r) for r in rows], total=total or 0)


@router.post("/drugs", response_model=DrugOut, status_code=201)
async def create_drug(
    body: DrugCreate,
    request: Request,
    current: dict = Depends(get_current_staff),
    db: AsyncSession = Depends(get_session),
) -> DrugOut:
    existing = await db.scalar(
        select(DrugCatalog).where(DrugCatalog.gns_code == body.gns_code)
    )
    if existing:
        raise HTTPException(409, "A drug with this GNS code already exists")
    drug = DrugCatalog(**body.model_dump())
    db.add(drug)
    await db.flush()  # assign drug.id before the audit row references it
    write_staff_audit(
        db,
        staff_id=current["staff_id"],
        action="drug.create",
        resource_type="drug",
        resource_id=str(drug.id),
        request_body={"gns_code": body.gns_code},
        request=request,
    )
    await db.commit()
    await db.refresh(drug)
    return DrugOut.model_validate(drug)


@router.patch("/drugs/{drug_id}", response_model=DrugOut)
async def update_drug(
    drug_id: uuid.UUID,
    body: DrugUpdate,
    request: Request,
    current: dict = Depends(get_current_staff),
    db: AsyncSession = Depends(get_session),
) -> DrugOut:
    drug = await db.get(DrugCatalog, drug_id)
    if drug is None:
        raise HTTPException(404, "Drug not found")
    changes = body.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(drug, field, value)
    write_staff_audit(
        db,
        staff_id=current["staff_id"],
        action="drug.update",
        resource_type="drug",
        resource_id=str(drug.id),
        request_body={"fields": sorted(changes.keys())},
        request=request,
    )
    await db.commit()
    await db.refresh(drug)
    return DrugOut.model_validate(drug)


# --- Safety rules ---
@router.get("/safety-rules", response_model=SafetyRuleListResponse)
async def list_safety_rules(
    current: dict = Depends(get_current_staff),
    db: AsyncSession = Depends(get_session),
    q: str | None = Query(None, description="rule-code / message substring"),
    active: bool | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> SafetyRuleListResponse:
    conds = []
    if q:
        like = f"%{q}%"
        conds.append(
            or_(SafetyRule.rule_code.ilike(like), SafetyRule.message_en.ilike(like))
        )
    if active is not None:
        conds.append(SafetyRule.active.is_(active))
    total = await db.scalar(select(func.count()).select_from(SafetyRule).where(*conds))
    rows = (
        await db.scalars(
            select(SafetyRule)
            .where(*conds)
            .order_by(SafetyRule.rule_code)
            .limit(limit)
            .offset(offset)
        )
    ).all()
    return SafetyRuleListResponse(
        items=[SafetyRuleOut.model_validate(r) for r in rows], total=total or 0
    )


@router.post("/safety-rules", response_model=SafetyRuleOut, status_code=201)
async def create_safety_rule(
    body: SafetyRuleCreate,
    request: Request,
    current: dict = Depends(get_current_staff),
    db: AsyncSession = Depends(get_session),
) -> SafetyRuleOut:
    existing = await db.scalar(
        select(SafetyRule).where(SafetyRule.rule_code == body.rule_code)
    )
    if existing:
        raise HTTPException(409, "A safety rule with this code already exists")
    rule = SafetyRule(**body.model_dump())
    db.add(rule)
    await db.flush()  # assign rule.id before the audit row references it
    write_staff_audit(
        db,
        staff_id=current["staff_id"],
        action="safety_rule.create",
        resource_type="safety_rule",
        resource_id=str(rule.id),
        request_body={"rule_code": body.rule_code},
        request=request,
    )
    await db.commit()
    await db.refresh(rule)
    return SafetyRuleOut.model_validate(rule)


@router.patch("/safety-rules/{rule_id}", response_model=SafetyRuleOut)
async def update_safety_rule(
    rule_id: uuid.UUID,
    body: SafetyRuleUpdate,
    request: Request,
    current: dict = Depends(get_current_staff),
    db: AsyncSession = Depends(get_session),
) -> SafetyRuleOut:
    rule = await db.get(SafetyRule, rule_id)
    if rule is None:
        raise HTTPException(404, "Safety rule not found")
    changes = body.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(rule, field, value)
    write_staff_audit(
        db,
        staff_id=current["staff_id"],
        action="safety_rule.update",
        resource_type="safety_rule",
        resource_id=str(rule.id),
        request_body={"fields": sorted(changes.keys())},
        request=request,
    )
    await db.commit()
    await db.refresh(rule)
    return SafetyRuleOut.model_validate(rule)
