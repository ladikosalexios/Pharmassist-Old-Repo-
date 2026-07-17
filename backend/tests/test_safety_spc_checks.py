"""SPC-driven safety checks + positive confirmations (verbose_spc path).

These pin the single-rx review behaviour: when ``verbose_spc=True`` the engine
enriches the result from the drug's own SPC (``resolve_spc``) and adds green
positive-confirmation rows for every screening path that ran clean, so the
review card is populated instead of blank. ``resolve_spc`` is monkeypatched so
the tests are hermetic (no DB) and ``session=None`` proves the verbose path does
no DB I/O when intolerances + conditions are supplied — matching the /v1 tests.

The default (``verbose_spc=False``) must stay byte-identical to the lean
alerts-only output the dashboard batch and /v1 path depend on.
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
from app.db.models.safety_rule import SafetyRule  # noqa: E402
from app.services import safety_engine  # noqa: E402
from app.services.safety_engine import evaluate_safety  # noqa: E402

AMKA = "01010101010"


def _interaction_rules() -> list[SafetyRule]:
    # A real interaction rule that does NOT match olanzapine/metformin — proves
    # interaction screening RAN (rules present) and cleared, so the confirmation
    # fires. Mirrors production, where the 18 seeded rules are always loaded.
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
    ]


# Olanzapine — matches none of the seeded rules, so nothing fires from the rule
# table; only the SPC path and confirmations can populate the card.
OLANZAPINE = "N05AH03"


def _rx(atc: str = OLANZAPINE) -> dict:
    return {"rxId": "SPC-T", "patient": {"id": AMKA, "amka": AMKA}, "medication": {"atcCode": atc}}


def _spc_stub(**fields):
    """Return an async resolve_spc replacement yielding a canned SPC dict (or None)."""

    async def _resolve(session, atc_code, barcode=None):
        if fields.get("_none"):
            return None
        return {
            "contraindications": fields.get("contraindications", []),
            "precautions": fields.get("precautions", []),
            "majorInteractions": fields.get("majorInteractions", []),
        }

    return _resolve


def _evaluate(monkeypatch, spc, **kwargs):
    monkeypatch.setattr(safety_engine, "resolve_spc", spc)
    return asyncio.run(evaluate_safety(None, kwargs.pop("rx"), pharmacy_id=uuid.uuid4(), **kwargs))


def test_spc_contraindication_matches_intolerance(monkeypatch):
    # Drug ATC (N05A) does NOT class-match the intolerance (J01C), so §2 stays
    # silent — the alert must come from the SPC §4.3 text mentioning the allergen.
    payload = _evaluate(
        monkeypatch,
        _spc_stub(contraindications=["Υπερευαισθησία στην amoxicillin ή σε άλλες πενικιλλίνες."]),
        rx=_rx(),
        rules=[],
        intolerances=[
            {"atcCode": "J01CA04", "name": "Amoxicillin", "severity": AdrSeverity.SEVERE}
        ],
        patient_conditions=[],
        verbose_spc=True,
    )
    contra = [c for c in payload.checks if c.check_type == CheckType.CONTRAINDICATIONS]
    assert len(contra) == 1
    assert contra[0].status == AlertStatus.BLOCK  # SEVERE intolerance → block
    assert "amoxicillin" in contra[0].message.lower()
    assert "Amoxicillin" in (contra[0].details or "")
    # The allergy path fired, so there is NO "no allergy" green confirmation.
    assert not any(c.id.endswith("_OK_ALLERGY") for c in payload.checks)


def test_spc_precautions_pointer(monkeypatch):
    payload = _evaluate(
        monkeypatch,
        _spc_stub(precautions=["Παρακολούθηση ηπατικής λειτουργίας.", "Προσοχή σε ηλικιωμένους."]),
        rx=_rx(),
        rules=[],
        intolerances=[],
        patient_conditions=[],
        verbose_spc=True,
    )
    prec = [c for c in payload.checks if c.id.endswith("_SPC_PRECAUTIONS_" + OLANZAPINE)]
    assert len(prec) == 1
    assert prec[0].check_type == CheckType.SPC_ALIGNMENT
    assert prec[0].status == AlertStatus.REVIEW  # expandable so the list shows
    assert "Παρακολούθηση ηπατικής λειτουργίας." in (prec[0].details or "")
    assert "Προσοχή σε ηλικιωμένους." in (prec[0].details or "")
    # Allergy screening ran clean (empty intolerance list) → green confirmation.
    assert any(c.id.endswith("_OK_ALLERGY") for c in payload.checks)


def test_clean_scan_yields_positive_confirmations(monkeypatch):
    # No SPC, no matching rule, but a co-med is present → both screening paths
    # ran and cleared, so the card is populated with two green confirmations.
    payload = _evaluate(
        monkeypatch,
        _spc_stub(_none=True),
        rx=_rx(),
        rules=_interaction_rules(),
        history_atcs={"A10BA02"},  # a co-medication (metformin)
        intolerances=[],
        patient_conditions=[],
        verbose_spc=True,
    )
    ids = {c.id for c in payload.checks}
    assert "SPC-T_OK_ALLERGY" in ids
    assert "SPC-T_OK_INTERACTION" in ids
    assert all(c.status == AlertStatus.OK for c in payload.checks)
    # "N co-medications" reflects the one co-med in the set.
    inter = next(c for c in payload.checks if c.id == "SPC-T_OK_INTERACTION")
    assert "1" in inter.name


def test_no_interaction_confirmation_without_comeds(monkeypatch):
    # Single med, no history → interaction path never ran, so NO interaction
    # confirmation (never a false "all clear" for a path with no data).
    payload = _evaluate(
        monkeypatch,
        _spc_stub(_none=True),
        rx=_rx(),
        rules=[],
        history_atcs=set(),
        intolerances=[],
        patient_conditions=[],
        verbose_spc=True,
    )
    assert not any(c.id.endswith("_OK_INTERACTION") for c in payload.checks)
    assert any(c.id.endswith("_OK_ALLERGY") for c in payload.checks)


def test_verbose_off_is_byte_identical(monkeypatch):
    # Same inputs as the clean-scan case but verbose_spc defaulted off → the lean
    # alerts-only output (empty here) the dashboard/v1 path relies on. resolve_spc
    # must never be consulted.
    def _boom(*a, **k):
        raise AssertionError("resolve_spc must not be called when verbose_spc is off")

    payload = _evaluate(
        monkeypatch,
        _boom,
        rx=_rx(),
        rules=_interaction_rules(),
        history_atcs={"A10BA02"},
        intolerances=[],
        patient_conditions=[],
    )
    assert payload.checks == []
