import uuid
from datetime import datetime

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
