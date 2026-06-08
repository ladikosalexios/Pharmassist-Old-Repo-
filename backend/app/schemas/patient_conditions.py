import uuid
from datetime import datetime

from pydantic import Field

from .base import AppSchema


class PatientConditionPayload(AppSchema):
    id: uuid.UUID
    amka: str
    condition_code: str
    name: str
    severity: str | None
    notes: str | None
    recorded_by: uuid.UUID
    pharmacy_id: uuid.UUID
    active: bool
    created_at: datetime
    updated_at: datetime


class PatientConditionCreate(AppSchema):
    """Request body for POST /patients/{id}/conditions (camelCase in)."""

    condition_code: str = Field(min_length=1)
    name: str = Field(min_length=1)
    severity: str | None = None
    notes: str | None = None


class PatientConditionUpdate(AppSchema):
    """Request body for PATCH — every field optional; only those sent are applied."""

    condition_code: str | None = Field(default=None, min_length=1)
    name: str | None = Field(default=None, min_length=1)
    severity: str | None = None
    notes: str | None = None
