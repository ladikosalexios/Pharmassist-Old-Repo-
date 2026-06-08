import uuid
from datetime import datetime

from pydantic import field_validator

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

    condition_code: str
    name: str
    severity: str | None = None
    notes: str | None = None

    @field_validator("condition_code", "name")
    @classmethod
    def _required_nonblank(cls, v: str) -> str:
        # Trim and reject blank server-side — min_length alone would accept "   ".
        v = v.strip()
        if not v:
            raise ValueError("must not be blank")
        return v


class PatientConditionUpdate(AppSchema):
    """Request body for PATCH — every field optional; only those sent are applied."""

    condition_code: str | None = None
    name: str | None = None
    severity: str | None = None
    notes: str | None = None

    @field_validator("condition_code", "name")
    @classmethod
    def _nonblank_if_present(cls, v: str | None) -> str:
        # Runs only when the field is actually present in the body (omitted fields
        # keep their default and skip validation). An explicit null on a NOT NULL
        # column would 500 at commit, so reject it here; trim + reject blank too.
        if v is None:
            raise ValueError("cannot be null; omit the field to leave it unchanged")
        v = v.strip()
        if not v:
            raise ValueError("must not be blank")
        return v
