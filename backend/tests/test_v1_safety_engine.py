"""BC-12 engine-seam unit tests — explicit drug lists + injected conditions.

These pin the two additive evaluate_safety parameters the /v1 surface relies
on: `history_atcs` (caller-supplied co-medication — what revives interaction
and duplicate-therapy checks in live mode) and `patient_conditions`
(pre-loaded location-scoped rows). `session=None` everywhere proves the
engine performs NO database I/O when both seams are supplied — if it did,
these tests would explode on the None session.
"""

import asyncio
import base64
import os

os.environ.setdefault("PHARMAPI_MOCK", "true")
os.environ.setdefault("COOKIE_SECURE", "false")
os.environ.setdefault("CREDENTIAL_ENCRYPTION_KEY", base64.b64encode(b"\x01" * 32).decode())
os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("PHARMAPI_USERNAME", "u")
os.environ.setdefault("PHARMAPI_PASSWORD", "p")
os.environ.setdefault("PHARMAPI_API_KEY", "k")
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+asyncpg://pharmassist:pharmassist_dev@localhost:5432/pharmassist_test",
)

import uuid  # noqa: E402

from app.constants import AdrSeverity, AlertStatus, CheckType  # noqa: E402
from app.db.models.b2b_patient_condition import B2bPatientCondition  # noqa: E402
from app.db.models.safety_rule import SafetyRule  # noqa: E402
from app.services.safety_engine import evaluate_safety  # noqa: E402

# An AMKA with no MOCK_INTOLERANCES entry, so only the seams under test fire.
AMKA = "01010101010"


def _rules() -> list[SafetyRule]:
    return [
        SafetyRule(
            rule_code="WARFARIN_ASPIRIN_BLEED",
            check_type=CheckType.INTERACTIONS,
            trigger_atc="B01AA03",
            conflicting_atc="B01AC06",
            severity=AdrSeverity.MODERATE,
            message_en="Bleeding risk",
            details_en="d",
            recommended_action_en="review",
            active=True,
        ),
        SafetyRule(
            rule_code="WARFARIN_ACENOCOUMAROL_DUPLICATE",
            check_type=CheckType.DUPLICATE_THERAPY,
            trigger_atc="B01AA03",
            conflicting_atc="B01AA07",
            severity=AdrSeverity.SEVERE,
            message_en="Duplicate anticoagulation",
            details_en="d",
            recommended_action_en="block",
            active=True,
        ),
        SafetyRule(
            rule_code="WARFARIN_PREGNANCY",
            check_type=CheckType.CONTRAINDICATIONS,
            trigger_atc="B01AA03",
            trigger_condition_code="PREGNANCY",
            severity=AdrSeverity.SEVERE,
            message_en="Teratogenic risk",
            details_en="d",
            recommended_action_en="block",
            active=True,
        ),
    ]


def _rx(atc: str | None, amka: str | None = AMKA) -> dict:
    return {"rxId": "V1-T", "patient": {"id": amka, "amka": amka}, "medication": {"atcCode": atc}}


def _evaluate(**kwargs):
    return asyncio.run(evaluate_safety(None, kwargs.pop("rx"), pharmacy_id=uuid.uuid4(), **kwargs))


def test_interaction_fires_from_explicit_history_atcs():
    payload = _evaluate(
        rx=_rx("B01AA03"),
        rules=_rules(),
        history_atcs={"B01AC06"},
        patient_conditions=[],
    )
    codes = [c.id for c in payload.checks]
    assert codes == ["V1-T_WARFARIN_ASPIRIN_BLEED"]
    assert payload.checks[0].status == AlertStatus.REVIEW
    assert payload.checks[0].severity == AdrSeverity.MODERATE


def test_interaction_is_bidirectional():
    # Aspirin as the NEW drug, warfarin in the co-medication set.
    payload = _evaluate(
        rx=_rx("B01AC06"),
        rules=_rules(),
        history_atcs={"B01AA03"},
        patient_conditions=[],
    )
    assert [c.id for c in payload.checks] == ["V1-T_WARFARIN_ASPIRIN_BLEED"]


def test_duplicate_therapy_fires_and_blocks():
    payload = _evaluate(
        rx=_rx("B01AA03"),
        rules=_rules(),
        history_atcs={"B01AA07"},
        patient_conditions=[],
    )
    check = payload.checks[0]
    assert check.check_type == CheckType.DUPLICATE_THERAPY
    assert check.status == AlertStatus.BLOCK
    assert check.severity == AdrSeverity.SEVERE


def test_empty_history_means_no_interaction_checks():
    payload = _evaluate(
        rx=_rx("B01AA03"), rules=_rules(), history_atcs=set(), patient_conditions=[]
    )
    assert payload.checks == []


def test_condition_contraindication_from_injected_conditions():
    condition = B2bPatientCondition(
        location_id=uuid.uuid4(),
        amka=AMKA,
        condition_code="PREGNANCY",
        name="Pregnancy",
        active=True,
    )
    payload = _evaluate(
        rx=_rx("B01AA03"),
        rules=_rules(),
        history_atcs=set(),
        patient_conditions=[condition],
    )
    check = payload.checks[0]
    assert check.id == "V1-T_WARFARIN_PREGNANCY"
    assert check.status == AlertStatus.BLOCK
    assert check.severity == AdrSeverity.SEVERE


def test_injected_empty_conditions_skip_db_entirely():
    # session=None would raise on any DB call — passing [] must short-circuit.
    payload = _evaluate(
        rx=_rx("B01AA03"), rules=_rules(), history_atcs=set(), patient_conditions=[]
    )
    assert payload.source == "engine"


def test_missing_atc_skips_all_checks():
    payload = _evaluate(
        rx=_rx(None), rules=_rules(), history_atcs={"B01AC06"}, patient_conditions=[]
    )
    assert payload.checks == []
