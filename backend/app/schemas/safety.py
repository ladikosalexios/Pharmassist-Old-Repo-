from datetime import datetime
from typing import Literal

from ..constants import AlertStatus, CheckType
from .base import AppSchema

STATUS_ORDER = {AlertStatus.BLOCK: 0, AlertStatus.REVIEW: 1, AlertStatus.OK: 2}


class SafetyAlertPayload(AppSchema):
    id: str
    name: str
    check_type: CheckType
    status: AlertStatus
    # Raw rule severity (MILD/MODERATE/SEVERE) alongside the mapped status —
    # the /v1 B2B contract exposes it; curated mock checks predate it → None.
    severity: str | None = None
    message: str
    details: str | None = None
    recommended_action: str | None = None
    rx_id: str | None = None
    created_at: datetime | None = None


class SafetyChecksPayload(AppSchema):
    rx_id: str
    checks: list[SafetyAlertPayload]
    source: Literal["mock", "engine"]
