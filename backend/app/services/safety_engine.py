"""Rule-based safety evaluation engine.

Evaluates a prescription against three data sources and returns a sorted list
of safety alerts. Replaces per-prescription MOCK_SAFETY_CHECKS for any rx_id
not already covered by that mock.
"""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import and_, or_, select, true
from sqlalchemy.ext.asyncio import AsyncSession

from ..constants import AdrSeverity, AlertStatus, CheckType
from ..db.models.safety_rule import SafetyRule
from ..schemas.safety import STATUS_ORDER, SafetyAlertPayload, SafetyChecksPayload
from .patients import conditions, rx_history
from .prescriptions import MOCK_PRESCRIPTIONS

# Intolerances are not yet available from Pharmapi, so a minimal mock is used.
# Each entry mirrors the shape the Pharmapi endpoint will eventually return.
# Keyed by patient AMKA.
# TODO: replace with live Pharmapi intolerances endpoint when wired.
MOCK_INTOLERANCES: dict = {
    # P001 Maria Stavrou — "Penicillin (anaphylaxis)" allergy maps to J01CA (penicillins)
    "15031962456": [
        {"atcCode": "J01CA04", "name": "Amoxicillin", "severity": "SEVERE"},
    ],
}


_SEVERITY_TO_STATUS = {
    AdrSeverity.SEVERE: AlertStatus.BLOCK,
    AdrSeverity.MODERATE: AlertStatus.REVIEW,
    AdrSeverity.MILD: AlertStatus.REVIEW,
}

_CHECK_TYPE_NAME = {
    CheckType.INTERACTIONS: "Drug-Drug Interactions",
    CheckType.DUPLICATE_THERAPY: "Duplicate Therapy Check",
    CheckType.CONTRAINDICATIONS: "Contraindications",
    CheckType.DOSE_VALIDATION: "Dose Validation",
}


def _rule_to_alert(rule: SafetyRule, rx_id: str) -> SafetyAlertPayload:
    return SafetyAlertPayload(
        id=rule.rule_code,
        name=_CHECK_TYPE_NAME.get(rule.check_type, rule.check_type),
        check_type=rule.check_type,
        status=_SEVERITY_TO_STATUS.get(rule.severity, AlertStatus.REVIEW),
        message=rule.message_en,
        details=rule.details_en,
        recommended_action=rule.recommended_action_en,
        rx_id=rx_id,
        created_at=datetime.now(UTC),
    )


async def evaluate_safety(
    session: AsyncSession,
    rx: dict,
    pharmacy_id: UUID,
) -> SafetyChecksPayload:
    rx_atc = rx["medication"]["atcCode"]
    patient_id = rx["patient"]["id"]
    amka = rx["patient"]["amka"]

    checks: list[SafetyAlertPayload] = []
    seen: set[str] = set()

    # --- 1. Drug-drug interactions & duplicate therapy ---
    # Build the list of ATC codes from the patient's prescription history.
    # Only history entries whose rx_id exists in MOCK_PRESCRIPTIONS yield an
    # ATC code; older entries without a full record are silently skipped.
    # TODO: replace MOCK_PRESCRIPTIONS lookup with Pharmapi medicine history.
    history_atcs = [
        hist_rx["medication"]["atcCode"]
        for entry in rx_history(patient_id)
        if entry["rxId"] != rx["rxId"] and (hist_rx := MOCK_PRESCRIPTIONS.get(entry["rxId"]))
    ]

    if history_atcs:
        # Fetch every active interaction/duplicate rule where one ATC matches
        # the current prescription and the other matches any history drug.
        # The OR across both column directions gives bidirectional matching:
        # WARFARIN_ASPIRIN_BLEED fires whether Warfarin is new or historical.
        interaction_rules = await session.scalars(
            select(SafetyRule).where(
                SafetyRule.active == true(),
                SafetyRule.check_type.in_([CheckType.INTERACTIONS, CheckType.DUPLICATE_THERAPY]),
                or_(
                    and_(
                        SafetyRule.trigger_atc == rx_atc,
                        SafetyRule.conflicting_atc.in_(history_atcs),
                    ),
                    and_(
                        SafetyRule.conflicting_atc == rx_atc,
                        SafetyRule.trigger_atc.in_(history_atcs),
                    ),
                ),
            )
        )
        for rule in interaction_rules:
            if rule.rule_code not in seen:
                seen.add(rule.rule_code)
                checks.append(_rule_to_alert(rule, rx["rxId"]))

    # --- 2. Intolerances / contraindications (Pharmapi) ---
    # Match on the first four characters of the ATC code (level-3 class) so
    # that a penicillin intolerance catches all J01CA-* drugs, not just the
    # exact molecule recorded.
    for intol in MOCK_INTOLERANCES.get(amka, []):
        if rx_atc[:4] == intol["atcCode"][:4]:
            key = f"INTOLERANCE_{intol['atcCode'][:4]}"
            if key not in seen:
                seen.add(key)
                checks.append(
                    SafetyAlertPayload(
                        id=f"{rx['rxId']}_INTOLERANCE_{intol['atcCode'][:4]}",
                        name=_CHECK_TYPE_NAME[CheckType.CONTRAINDICATIONS],
                        check_type=CheckType.CONTRAINDICATIONS,
                        status=_SEVERITY_TO_STATUS.get(intol["severity"], AlertStatus.REVIEW),
                        message=intol["name"],
                        rx_id=rx["rxId"],
                        created_at=datetime.now(UTC),
                    )
                )

    # --- 3. Patient-specific conditions (DB) ---
    # Fetch conditions recorded by the pharmacy for this patient, then query
    # for any active rules whose trigger_atc matches the prescription and whose
    # trigger_condition_code matches one of those recorded conditions.
    pt_conditions = await conditions(session, amka, pharmacy_id)
    condition_codes = [c.condition_code for c in pt_conditions]

    if condition_codes:
        condition_rules = await session.scalars(
            select(SafetyRule).where(
                SafetyRule.active == true(),
                SafetyRule.trigger_atc == rx_atc,
                SafetyRule.trigger_condition_code.in_(condition_codes),
            )
        )
        for rule in condition_rules:
            if rule.rule_code not in seen:
                seen.add(rule.rule_code)
                checks.append(_rule_to_alert(rule, rx["rxId"]))

    checks.sort(key=lambda a: STATUS_ORDER.get(a.status, 99))
    return SafetyChecksPayload(rx_id=rx["rxId"], checks=checks, source="engine")
