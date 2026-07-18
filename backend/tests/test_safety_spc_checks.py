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
            "interactionsText": fields.get("interactionsText"),
        }

    return _resolve


def _spc_by_atc(mapping):
    """resolve_spc replacement that returns a different canned SPC per ATC."""

    async def _resolve(session, atc_code, barcode=None):
        return mapping.get(atc_code)

    return _resolve


class _Cond:
    """Minimal patient-condition row (engine reads .condition_code/.name/.severity)."""

    def __init__(self, condition_code, name, severity=None):
        self.condition_code = condition_code
        self.name = name
        self.severity = severity


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


# ── v2: patient-factor gating, de-dup, §4.5 cross-ref ────────────────────────


def _rx_aged(age):
    return {
        "rxId": "SPC-T",
        "patient": {"id": AMKA, "amka": AMKA, "age": age},
        "medication": {"atcCode": OLANZAPINE},
    }


def test_elderly_precaution_elevated_and_stripped_from_pointer(monkeypatch):
    # age 72 → elderly factor. The "elderly" precaution line becomes a
    # patient-specific REVIEW and is REMOVED from the generic pointer (which
    # keeps only the unrelated line) — so the card never repeats it.
    payload = _evaluate(
        monkeypatch,
        _spc_stub(precautions=["Caution in elderly patients with dementia.", "Take with water."]),
        rx=_rx_aged(72),
        rules=[],
        intolerances=[],
        patient_conditions=[],
        verbose_spc=True,
    )
    elevated = [c for c in payload.checks if c.name == "Προφύλαξη — αφορά τον ασθενή"]
    assert len(elevated) == 1
    assert "elderly" in elevated[0].message.lower()
    pointer = [c for c in payload.checks if c.id.endswith("_SPC_PRECAUTIONS_" + OLANZAPINE)]
    assert len(pointer) == 1
    assert "Take with water." in (pointer[0].details or "")
    assert "elderly" not in (pointer[0].details or "").lower()  # not repeated


def test_younger_patient_no_elderly_elevation(monkeypatch):
    payload = _evaluate(
        monkeypatch,
        _spc_stub(precautions=["Caution in elderly patients with dementia."]),
        rx=_rx_aged(40),
        rules=[],
        intolerances=[],
        patient_conditions=[],
        verbose_spc=True,
    )
    assert not any(c.name == "Προφύλαξη — αφορά τον ασθενή" for c in payload.checks)
    # The unmatched precaution still shows once, in the generic pointer.
    assert any(c.id.endswith("_SPC_PRECAUTIONS_" + OLANZAPINE) for c in payload.checks)


def test_pregnancy_contraindication_blocks(monkeypatch):
    payload = _evaluate(
        monkeypatch,
        _spc_stub(contraindications=["Contraindicated during pregnancy and lactation."]),
        rx=_rx(),
        rules=[],
        intolerances=[],
        patient_conditions=[_Cond("PREGNANCY", "Εγκυμοσύνη")],
        verbose_spc=True,
    )
    contra = [c for c in payload.checks if c.name == "Αντένδειξη — αφορά τον ασθενή"]
    assert len(contra) == 1
    assert contra[0].status == AlertStatus.BLOCK  # condition contraindication → block
    assert "Εγκυμοσύνη" in (contra[0].details or "")


def test_spc_45_comed_interaction_flagged(monkeypatch):
    # Two-med prescription: olanzapine's §4.5 text names the co-med (lisinopril
    # brand) → a "possible interaction" REVIEW, beyond the 18 seeded rules.
    rx = {
        "rxId": "SPC-T",
        "patient": {"id": AMKA, "amka": AMKA, "age": 50},
        "medications": [
            {"atcCode": OLANZAPINE, "nhrn": None, "drugName": "OLENXA"},
            {"atcCode": "C09AA03", "nhrn": None, "drugName": "ZESTRIL"},
        ],
    }
    spc_map = {
        OLANZAPINE: {
            "contraindications": [],
            "precautions": [],
            "majorInteractions": [],
            "interactionsText": "Concomitant use with ZESTRIL may enhance hypotensive effect.",
        },
        "C09AA03": {
            "contraindications": [],
            "precautions": [],
            "majorInteractions": [],
            "interactionsText": "",
        },
    }
    payload = _evaluate(
        monkeypatch,
        _spc_by_atc(spc_map),
        rx=rx,
        rules=[],
        intolerances=[],
        patient_conditions=[],
        verbose_spc=True,
    )
    inter = [c for c in payload.checks if c.name == "Πιθανή αλληλεπίδραση (ΠΧΠ §4.5)"]
    assert len(inter) == 1
    assert "ZESTRIL" in inter[0].message
    assert inter[0].status == AlertStatus.REVIEW
    # An interaction fired → NO "no interaction" green confirmation.
    assert not any(c.id.endswith("_OK_INTERACTION") for c in payload.checks)


def test_screened_comeds_named_in_confirmation(monkeypatch):
    # Co-med present, nothing matched → the green confirmation NAMES the screened
    # co-medication instead of just a count.
    rx = {
        "rxId": "SPC-T",
        "patient": {"id": AMKA, "amka": AMKA, "age": 50},
        "medications": [
            {"atcCode": OLANZAPINE, "nhrn": None, "drugName": "OLENXA"},
            {"atcCode": "C09AA03", "nhrn": None, "drugName": "ZESTRIL"},
        ],
    }
    payload = _evaluate(
        monkeypatch,
        _spc_stub(interactionsText="No relevant interactions reported."),
        rx=rx,
        rules=[],
        intolerances=[],
        patient_conditions=[],
        verbose_spc=True,
    )
    ok = [c for c in payload.checks if c.id.endswith("_OK_INTERACTION")]
    assert len(ok) == 1
    assert "ZESTRIL" in ok[0].name


# ── v2: duplicate therapy vs ACTIVE history medication ───────────────────────


class _Res:
    def __init__(self, atc, substance_code=None, inn_name=None):
        self.atc_code = atc
        self.substance_code = substance_code
        self.inn_name = inn_name


def _patch_history(monkeypatch, items, resolve_by_name):
    """Make the engine load these history items and resolve brand→record by name.

    ``resolve_by_name`` maps a substring of the brand → a ``_Res`` (or a bare ATC
    string, wrapped)."""

    async def _history(patient_id):
        return items

    def _rec(v):
        return v if isinstance(v, _Res) else _Res(v)

    async def _resolve(session, hints):
        return [
            next(
                (_rec(v) for n, v in resolve_by_name.items() if n in (h.commercial_name or "")),
                None,
            )
            for h in hints
        ]

    monkeypatch.setattr(safety_engine, "rx_history", _history)
    monkeypatch.setattr(safety_engine, "resolve_atcs", _resolve)


def test_duplicate_therapy_same_drug_active(monkeypatch):
    _patch_history(
        monkeypatch,
        [
            {
                "rxId": "H1",
                "drugName": "OLANZAPINE 10MG",
                "status": "PENDING",
                "quantityOutstanding": 30,
            },
            {
                "rxId": "H2",
                "drugName": "OLD COURSE",
                "status": "COMPLETED",
                "quantityOutstanding": 0,
            },
        ],
        {"OLANZAPINE": OLANZAPINE, "OLD COURSE": "A10BA02"},
    )
    payload = _evaluate(
        monkeypatch,
        _spc_stub(_none=True),
        rx=_rx(),  # dispensing olanzapine N05AH03
        rules=_interaction_rules(),
        intolerances=[],
        patient_conditions=[],
        verbose_spc=True,
    )
    dup = [c for c in payload.checks if c.check_type == CheckType.DUPLICATE_THERAPY]
    assert len(dup) == 1
    assert "ίδιο φάρμακο" in dup[0].name
    assert "OLANZAPINE" in dup[0].message
    assert dup[0].status == AlertStatus.REVIEW


def test_duplicate_therapy_same_class_active(monkeypatch):
    # Active co-med is a DIFFERENT antipsychotic in the same ATC-4 class (N05AH).
    _patch_history(
        monkeypatch,
        [{"rxId": "H1", "drugName": "CLOZAPINE", "status": "PENDING", "quantityOutstanding": 10}],
        {"CLOZAPINE": "N05AH02"},
    )
    payload = _evaluate(
        monkeypatch,
        _spc_stub(_none=True),
        rx=_rx(),
        rules=_interaction_rules(),
        intolerances=[],
        patient_conditions=[],
        verbose_spc=True,
    )
    dup = [c for c in payload.checks if c.check_type == CheckType.DUPLICATE_THERAPY]
    assert len(dup) == 1
    assert "ίδια κατηγορία" in dup[0].name
    assert "CLOZAPINE" in dup[0].message


def test_completed_history_is_not_duplicate(monkeypatch):
    # Same drug, but the prior course is fully COMPLETED (not active) → no flag.
    _patch_history(
        monkeypatch,
        [{"rxId": "H1", "drugName": "OLANZAPINE", "status": "COMPLETED", "quantityOutstanding": 0}],
        {"OLANZAPINE": OLANZAPINE},
    )
    payload = _evaluate(
        monkeypatch,
        _spc_stub(_none=True),
        rx=_rx(),
        rules=_interaction_rules(),
        intolerances=[],
        patient_conditions=[],
        verbose_spc=True,
    )
    assert not any(c.check_type == CheckType.DUPLICATE_THERAPY for c in payload.checks)


def test_duplicate_therapy_matches_on_substance_not_atc(monkeypatch):
    # The point of the change: a different BRAND of the same drug is flagged even
    # when the resolved ATC differs — the match is on substance_code, not ATC.
    _patch_history(
        monkeypatch,
        [{"rxId": "H1", "drugName": "ZALASTA", "status": "PENDING", "quantityOutstanding": 28}],
        {"ZALASTA": _Res("N05AH99", substance_code="SUB_OLZ")},  # different ATC, same substance
    )
    rx = {
        "rxId": "SPC-T",
        "patient": {"id": AMKA, "amka": AMKA},
        "medication": {"atcCode": OLANZAPINE, "substanceCode": "SUB_OLZ"},
    }
    payload = _evaluate(
        monkeypatch,
        _spc_stub(_none=True),
        rx=rx,
        rules=_interaction_rules(),
        intolerances=[],
        patient_conditions=[],
        verbose_spc=True,
    )
    dup = [c for c in payload.checks if c.check_type == CheckType.DUPLICATE_THERAPY]
    assert len(dup) == 1
    assert "ίδιο φάρμακο" in dup[0].name  # same drug (by substance), not just class
    assert "ZALASTA" in dup[0].message
