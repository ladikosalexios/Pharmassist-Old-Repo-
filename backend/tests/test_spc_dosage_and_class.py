"""Unit tests for SPC dosage/duration validation and class/bidirectional §4.5 checks."""

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

from app.constants import AlertStatus  # noqa: E402
from app.services import safety_engine  # noqa: E402
from app.services.safety_engine import (  # noqa: E402
    _check_spc_dosage_and_duration,
    _match_atc_class_in_text,
    _parse_duration_days,
    _parse_freq_per_day,
    _parse_prescribed_daily_mg,
    _parse_spc_daily_bounds_mg,
    _to_mg,
    evaluate_safety,
)


def test_to_mg_handles_micro_glyph_and_micrograms():
    assert _to_mg("100", "\u00b5g") == 0.1
    assert _to_mg("100", "μg") == 0.1
    assert _to_mg("250", "micrograms") == 0.25
    assert _to_mg("1.5", "g") == 1500.0
    assert _to_mg("5", "mg") == 5.0


def test_parse_freq_per_day_rejects_weekly_and_substrings():
    assert _parse_freq_per_day("Once weekly") is None
    assert _parse_freq_per_day("Twice weekly") is None
    assert _parse_freq_per_day("12x") is None
    assert _parse_freq_per_day("μια φορά την ημέρα") == 1.0
    assert _parse_freq_per_day("2 φορές την ημέρα") == 2.0
    assert _parse_freq_per_day("Once daily") == 1.0
    assert _parse_freq_per_day("Every 8 hours") == 3.0


def test_parse_duration_days_handles_greek_uppercase():
    assert _parse_duration_days("30 ΗΜΕΡΕΣ") == 30
    assert _parse_duration_days("2 weeks") == 14
    assert _parse_duration_days("3 months") == 90


def test_parse_spc_bounds_skips_mg_per_kg():
    spc = {
        "recommendedDosage": (
            "Paediatric dose is 20 to 90 mg/kg daily. "
            "Adult daily maintenance dose is 3 to 9mg."
        )
    }
    lo, hi = _parse_spc_daily_bounds_mg(spc)
    assert lo == 3.0
    assert hi == 9.0


def test_prescribed_daily_mg_with_micro_glyph():
    daily, freq = _parse_prescribed_daily_mg({"dose": "100 \u00b5g", "frequency": "Once daily"})
    assert freq == 1.0
    assert daily == 0.1


def test_dosage_above_max_is_review_and_safe_int_prevents_crash():
    spc = {"recommendedDosage": "Daily maintenance dose is 3 to 9mg."}
    alerts = _check_spc_dosage_and_duration(
        "RX-T1",
        "B01AA03",
        {
            "dose": "20 mg",
            "frequency": "Once daily",
            "treatmentDuration": "30 days",
            "boxes": "2 boxes",
            "packSize": 30,
        },
        spc,
        seen=set(),
        line_idx=0,
    )
    dose_alert = next(a for a in alerts if "SPC_DOSE" in a.id)
    assert dose_alert.status == AlertStatus.REVIEW
    # Non-numeric "2 boxes" falls back to verification reminder instead of crashing
    qty_alert = next(a for a in alerts if "SPC_QTY" in a.id)
    assert qty_alert.status == AlertStatus.REVIEW


def test_dedupe_allows_multiple_same_class_drugs():
    spc = {"recommendedDosage": "Daily maintenance dose is 3 to 9mg."}
    seen: set[str] = set()
    a1 = _check_spc_dosage_and_duration(
        "RX-T2", "B01AA03", {"dose": "5 mg", "frequency": "Once daily"}, spc, seen, line_idx=0
    )
    a2 = _check_spc_dosage_and_duration(
        "RX-T2", "B01AC06", {"dose": "5 mg", "frequency": "Once daily"}, spc, seen, line_idx=1
    )
    assert len(a1) == 1
    assert len(a2) == 1


def test_class_matching_uses_word_boundaries():
    # "stopping" must NOT trigger "ppi"
    assert _match_atc_class_in_text("A02BC01", "When stopping therapy, monitor.", []) is None
    # "nystatin" must NOT trigger "statin"
    assert _match_atc_class_in_text("C10AA05", "Co-administration with nystatin.", []) is None
    # Actual "statins" DOES trigger C10AA05
    assert _match_atc_class_in_text("C10AA05", "Avoid concurrent statins.", []) == "statins"


def test_unnamed_comed_outside_class_table_does_not_emit_false_ok(monkeypatch=None):
    orig_resolve = safety_engine.resolve_spc
    orig_resolve_atcs = safety_engine.resolve_atcs

    async def fake_resolve_spc(_session, atc, _barcode=None):
        if atc == "B01AA03":
            return {
                "atcCode": "B01AA03",
                "contraindications": [],
                "precautions": [],
                "majorInteractions": [],
                "interactionsText": "Avoid NSAIDs and statins.",
            }
        return None

    async def fake_resolve_atcs(_session, _hints):
        return {}

    safety_engine.resolve_spc = fake_resolve_spc
    safety_engine.resolve_atcs = fake_resolve_atcs
    try:
        res = asyncio.run(
            evaluate_safety(
                None,
                {
                    "rxId": "RX-M6",
                    "patient": {"amka": "01010101010"},
                    "medication": {"drugName": "Warfarin", "atcCode": "B01AA03"},
                },
                None,
                rules=[],
                history_atcs={"N05AH03"},
                intolerances=[],
                patient_conditions=[],
                verbose_spc=True,
            )
        )
        assert not any(c.id.endswith("_OK_INTERACTION") for c in res.checks)
    finally:
        safety_engine.resolve_spc = orig_resolve
        safety_engine.resolve_atcs = orig_resolve_atcs
