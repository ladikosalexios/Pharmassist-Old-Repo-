"""Rule-based safety evaluation engine.

Evaluates a prescription against three data sources and returns a sorted list
of safety alerts. Replaces per-prescription MOCK_SAFETY_CHECKS for any rx_id
not already covered by that mock.
"""

from datetime import UTC, datetime
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select, true
from sqlalchemy.ext.asyncio import AsyncSession

from ..constants import AdrSeverity, AlertStatus, CheckType
from ..db.models.safety_rule import SafetyRule
from ..schemas.safety import STATUS_ORDER, SafetyAlertPayload, SafetyChecksPayload
from .patients import conditions, rx_history
from .prescriptions import MOCK_PRESCRIPTIONS
from .safety_checks import MOCK_SAFETY_CHECKS

# Intolerances fallback for mock mode. Live intolerances are fetched from
# Pharmapi in patients.resolve() but carry activeSubstance + intolerance type
# with no ATC code — a drug_catalog/activesubstances lookup is needed to map
# them to ATC before the engine can use them. Until that mapping is in place,
# the mock covers the demo patients used in development.
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
    CheckType.PREGNANCY: "Pregnancy",
    CheckType.G6PD: "G6PD Deficiency",
}


def _rule_to_alert(rule: SafetyRule, rx_id: str) -> SafetyAlertPayload:
    return SafetyAlertPayload(
        id=f"{rx_id}_{rule.rule_code}",
        name=_CHECK_TYPE_NAME.get(rule.check_type, rule.check_type),
        check_type=rule.check_type,
        status=_SEVERITY_TO_STATUS.get(rule.severity, AlertStatus.REVIEW),
        severity=rule.severity,
        message=rule.message_en,
        details=rule.details_en,
        recommended_action=rule.recommended_action_en,
        rx_id=rx_id,
        created_at=datetime.now(UTC),
    )


def live_rx_to_engine_shape(rx: dict, atc: str | None) -> dict:
    """Reshape a Pharmapi v2 search item into the dict shape evaluate_safety expects.

    `patientAmka` drives both `patient.id` and `patient.amka` — both are required
    by the engine for intolerance and condition lookups. If AMKA is absent from
    the Pharmapi response, all ATC-keyed patient checks will silently skip.
    The v2 search schema includes `amka` on every result, but callers should be
    aware of this dependency when handling edge cases.
    """
    amka = rx.get("patientAmka")
    return {
        "rxId": rx.get("rxId"),
        "patient": {"id": amka, "amka": amka},
        "medication": {"atcCode": atc},
    }


async def load_active_safety_rules(session: AsyncSession) -> list[SafetyRule]:
    """One-shot load of every active safety rule.

    Intended for callers that batch many evaluate_safety calls per request
    (e.g. the alerts dashboard) so the per-rx WHERE-filtering moves to
    Python and the DB sees a single query instead of N.
    """
    result = await session.scalars(select(SafetyRule).where(SafetyRule.active == true()))
    return list(result.all())


async def checks_for_prescription(
    session: AsyncSession,
    rx_id: str,
    rx: dict | None,
    pharmacy_id: UUID,
    rules: list[SafetyRule] | None = None,
) -> SafetyChecksPayload:
    """Single source of truth for a prescription's safety checks.

    Demo prescriptions (rx_id in MOCK_SAFETY_CHECKS) are served from their
    curated, clinically-authored checklist; everything else is evaluated by
    the rule engine. BOTH the dashboard (/alerts/active) and the per-rx
    verification view (/safety-checks/{rx}) call this, so the two views can
    never disagree about a prescription — a block on one is a block on the
    other by construction.
    """
    mock_checks = MOCK_SAFETY_CHECKS.get(rx_id)
    if mock_checks is not None:
        checks = []
        for c in mock_checks:
            payload = SafetyAlertPayload.model_validate(c)
            # The curated dicts don't carry rx_id, and their `id` is generic
            # ("interactions", …). Stamp both so dashboard cards link back to
            # the right prescription and React keys stay unique across the
            # queue — matching what the engine path emits.
            payload.rx_id = rx_id
            payload.id = f"{rx_id}_{c['id']}"
            checks.append(payload)
        return SafetyChecksPayload(rx_id=rx_id, checks=checks, source="mock")
    if rx is None:
        raise HTTPException(status_code=404, detail=f"Prescription {rx_id} not found")
    return await evaluate_safety(session, rx, pharmacy_id, rules=rules)


async def evaluate_safety(
    session: AsyncSession,
    rx: dict,
    pharmacy_id: UUID,
    rules: list[SafetyRule] | None = None,
    history_atcs: set[str] | None = None,
    patient_conditions: list | None = None,
) -> SafetyChecksPayload:
    """Evaluate a single prescription against the safety-rule catalogue.

    Pass `rules` from a prior `load_active_safety_rules(session)` to skip
    the per-call DB round-trip. When `rx["medication"]["atcCode"]` is
    missing (e.g. live Pharmapi search hasn't been enriched yet), all
    ATC-keyed checks are skipped — DB-condition checks that don't need
    ATC still run when relevant rule shape supports it.

    The two seams for the B2B /v1 path (additive — B2C behaviour is
    unchanged when they are omitted):

    * `history_atcs` — explicit co-medication ATC set. When provided, the
      interaction/duplicate checks match against it directly instead of
      deriving history from the (mock-only) prescription store. This is what
      makes drug-drug checks work in live mode for callers that supply the
      patient's other drugs.
    * `patient_conditions` — pre-loaded condition rows (each carrying a
      `.condition_code`). When provided, the per-pharmacy DB read is skipped;
      /v1 loads them from b2b_patient_conditions scoped to its location.
    """
    if rules is None:
        rules = await load_active_safety_rules(session)

    medication = rx.get("medication") or {}
    rx_atc = medication.get("atcCode") if isinstance(medication, dict) else None
    patient = rx.get("patient") or {}
    patient_id = patient.get("id")
    amka = patient.get("amka")

    checks: list[SafetyAlertPayload] = []
    seen: set[str] = set()

    # --- 1. Drug-drug interactions & duplicate therapy ---
    # Pre-filter rules so we don't make the rx_history call (Pharmapi round-trip
    # in live mode) when no interaction/duplicate rules can possibly match.
    # Live mode gap: Pharmapi medicine history returns commercialName but no
    # medicine barcode, so ATC resolution via drug_catalog is not yet possible.
    # history_atcs will be empty in live mode; interaction checks don't fire.
    interaction_rules = [
        r for r in rules if r.check_type in (CheckType.INTERACTIONS, CheckType.DUPLICATE_THERAPY)
    ]
    if rx_atc and interaction_rules and (history_atcs is not None or patient_id):
        if history_atcs is None:
            history = await rx_history(patient_id)
            history_atcs = {
                hist_rx["medication"]["atcCode"]
                for entry in history
                if entry["rxId"] != rx["rxId"]
                and (hist_rx := MOCK_PRESCRIPTIONS.get(entry["rxId"]))
            }

        if history_atcs:
            # Bidirectional ATC match: WARFARIN_ASPIRIN_BLEED fires whether
            # warfarin is the new or the historical drug.
            for rule in interaction_rules:
                matches = (rule.trigger_atc == rx_atc and rule.conflicting_atc in history_atcs) or (
                    rule.conflicting_atc == rx_atc and rule.trigger_atc in history_atcs
                )
                if matches and rule.rule_code not in seen:
                    seen.add(rule.rule_code)
                    checks.append(_rule_to_alert(rule, rx["rxId"]))

    # --- 2. Intolerances / contraindications (Pharmapi) ---
    # Match on the first four characters of the ATC code (level-3 class) so
    # that a penicillin intolerance catches all J01CA-* drugs, not just the
    # exact molecule recorded.
    if rx_atc and amka:
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
                            severity=intol["severity"],
                            message=intol["name"],
                            rx_id=rx["rxId"],
                            created_at=datetime.now(UTC),
                        )
                    )

    # --- 3. Patient-specific conditions (DB) ---
    # Skip the DB call entirely when no rule could possibly match this rx's
    # ATC — saves a query per evaluated prescription on the alerts dashboard.
    condition_rule_candidates = [
        r for r in rules if r.trigger_atc == rx_atc and r.trigger_condition_code is not None
    ]
    if rx_atc and amka and condition_rule_candidates:
        pt_conditions = (
            patient_conditions
            if patient_conditions is not None
            else await conditions(session, amka, pharmacy_id)
        )
        condition_codes = {c.condition_code for c in pt_conditions}

        if condition_codes:
            for rule in condition_rule_candidates:
                if rule.trigger_condition_code in condition_codes and rule.rule_code not in seen:
                    seen.add(rule.rule_code)
                    checks.append(_rule_to_alert(rule, rx["rxId"]))

    checks.sort(key=lambda a: STATUS_ORDER.get(a.status, 99))
    return SafetyChecksPayload(rx_id=rx["rxId"], checks=checks, source="engine")
