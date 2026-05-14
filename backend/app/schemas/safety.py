from .base import AppSchema

SEVERITY_ORDER = {"SEVERE": 0, "MODERATE": 1, "MILD": 2}


class SafetyAlertPayload(AppSchema):
    type: str
    severity: str
    rule_code: str
    message: str
    details: str | None = None
    recommended_action: str | None = None


class SafetyChecksPayload(AppSchema):
    rx_id: str
    alerts: list[SafetyAlertPayload]
    source: str
    legacy_checks: list | None = None
