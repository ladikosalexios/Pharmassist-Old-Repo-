"""B2B patient-conditions CRUD — location-scoped twin of services/patients.py (D-3).

Every query is scoped by location_id from the ApiContext, so one tenant can
never read, edit, collide with, or infer the existence of another tenant's
records. Feeds the safety engine through evaluate_safety(patient_conditions=).
"""

import logging
import uuid

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.b2b_patient_condition import B2bPatientCondition

logger = logging.getLogger(__name__)

_DUPLICATE_CONSTRAINT = "uq_b2b_patient_conditions_location_amka_condition_active"


def _is_duplicate(exc: IntegrityError) -> bool:
    return _DUPLICATE_CONSTRAINT in str(exc.orig)


async def list_conditions(
    session: AsyncSession, location_id: uuid.UUID, amka: str
) -> list[B2bPatientCondition]:
    return list(
        await session.scalars(
            select(B2bPatientCondition)
            .where(
                B2bPatientCondition.location_id == location_id,
                B2bPatientCondition.amka == amka,
                B2bPatientCondition.active.is_(True),
            )
            .order_by(B2bPatientCondition.created_at.desc())
        )
    )


async def get_condition(
    session: AsyncSession,
    location_id: uuid.UUID,
    amka: str,
    condition_id: uuid.UUID,
) -> B2bPatientCondition | None:
    return (
        await session.scalars(
            select(B2bPatientCondition).where(
                B2bPatientCondition.id == condition_id,
                B2bPatientCondition.location_id == location_id,
                B2bPatientCondition.amka == amka,
                B2bPatientCondition.active.is_(True),
            )
        )
    ).one_or_none()


async def create_condition(
    session: AsyncSession,
    *,
    location_id: uuid.UUID,
    amka: str,
    condition_code: str,
    name: str,
    severity: str | None,
    notes: str | None,
    created_via_api_key_id: uuid.UUID | None,
) -> B2bPatientCondition:
    condition = B2bPatientCondition(
        location_id=location_id,
        amka=amka,
        condition_code=condition_code,
        name=name,
        severity=severity,
        notes=notes,
        created_via_api_key_id=created_via_api_key_id,
        active=True,
    )
    session.add(condition)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        if _is_duplicate(exc):
            # Per-location uniqueness only — a 409 here can never leak another
            # tenant's record (no AMKA in the log line either).
            logger.info("Duplicate active B2B condition blocked: location=%s", location_id)
            raise HTTPException(
                status_code=409,
                detail="Condition already recorded for this patient at this location",
            ) from None
        raise
    await session.refresh(condition)
    return condition


async def update_condition(
    session: AsyncSession,
    condition: B2bPatientCondition,
    *,
    fields: dict,
) -> B2bPatientCondition:
    for key, value in fields.items():
        setattr(condition, key, value)
    location_snapshot = condition.location_id
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        if _is_duplicate(exc):
            logger.info(
                "Duplicate active B2B condition blocked on PATCH: location=%s", location_snapshot
            )
            raise HTTPException(
                status_code=409,
                detail="Condition already recorded for this patient at this location",
            ) from None
        raise
    await session.refresh(condition)
    return condition


async def deactivate_condition(
    session: AsyncSession, condition: B2bPatientCondition
) -> B2bPatientCondition:
    """Soft delete: keep the row for audit, flip active=false."""
    condition.active = False
    await session.commit()
    await session.refresh(condition)
    return condition
