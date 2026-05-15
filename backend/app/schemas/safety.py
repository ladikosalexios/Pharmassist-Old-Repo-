from typing import Literal

from .base import AppSchema

STATUS_ORDER = {"block": 0, "review": 1, "ok": 2}


class SafetyAlertPayload(AppSchema):
    id: str
    name: str
    status: Literal["ok", "review", "block"]
    message: str
    details: str | None = None
    recommended_action: str | None = None
    rx_id: str | None = None


class SafetyChecksPayload(AppSchema):
    rx_id: str
    checks: list[SafetyAlertPayload]
    source: Literal["mock", "engine"]
