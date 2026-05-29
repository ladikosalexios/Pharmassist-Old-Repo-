"""Tests for the T9 live-mode helpers in routers/alerts.py and the
defensive paths added to services/safety_engine.evaluate_safety.

No DB and no real Pharmapi are involved — pure dict reshaping plus
evaluate_safety invocations with an explicit empty rules list and the
DB-touching code paths gated off by missing ATC / amka.
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

from app.routers.alerts import _live_rx_to_engine_shape  # noqa: E402
from app.services.safety_engine import evaluate_safety  # noqa: E402

# ── _live_rx_to_engine_shape ─────────────────────────────────────────────────


def test_live_rx_reshape_collapses_amka_into_patient_id():
    rx = {"rxId": "1234567890123456", "patientAmka": "15031962456"}
    shaped = _live_rx_to_engine_shape(rx, "B01AA03")
    assert shaped == {
        "rxId": "1234567890123456",
        "patient": {"id": "15031962456", "amka": "15031962456"},
        "medication": {"atcCode": "B01AA03"},
    }


def test_live_rx_reshape_with_no_atc():
    rx = {"rxId": "1234567890123456", "patientAmka": "15031962456"}
    shaped = _live_rx_to_engine_shape(rx, None)
    assert shaped["medication"] == {"atcCode": None}


# ── evaluate_safety defensive paths ──────────────────────────────────────────


def test_evaluate_safety_missing_atc_returns_empty_checks_no_db():
    """rx_atc=None must short-circuit every check block, so no DB / pharmapi
    calls happen even if `session` is None and `rules` is an empty list."""
    rx = {
        "rxId": "rx-1",
        "patient": {"id": "15031962456", "amka": "15031962456"},
        "medication": {"atcCode": None},
    }
    result = asyncio.run(evaluate_safety(session=None, rx=rx, pharmacy_id=uuid.uuid4(), rules=[]))
    assert result.rx_id == "rx-1"
    assert result.checks == []
    assert result.source == "engine"


def test_evaluate_safety_missing_patient_id_skips_history_block():
    """With ATC present but patient.id None, history lookup is skipped — the
    intolerance and DB-condition blocks still gate on amka, so empty result."""
    rx = {
        "rxId": "rx-2",
        "patient": {"id": None, "amka": None},
        "medication": {"atcCode": "B01AA03"},
    }
    result = asyncio.run(evaluate_safety(session=None, rx=rx, pharmacy_id=uuid.uuid4(), rules=[]))
    assert result.checks == []


def test_evaluate_safety_empty_rules_returns_no_alerts():
    """Even with a full rx, an empty rules list cannot produce any alerts."""
    rx = {
        "rxId": "rx-3",
        "patient": {"id": "P001", "amka": "15031962456"},
        "medication": {"atcCode": "B01AA03"},
    }
    # Only the intolerance block can fire without DB / rules: amka 15031962456
    # is in MOCK_INTOLERANCES with J01CA04, ATC class J01C. Our ATC is B01A,
    # so no class match → still empty.
    result = asyncio.run(evaluate_safety(session=None, rx=rx, pharmacy_id=uuid.uuid4(), rules=[]))
    assert result.checks == []


def test_evaluate_safety_intolerance_fires_without_db_or_rules():
    """MOCK_INTOLERANCES[15031962456] -> J01CA04. A penicillin-class rx
    should fire the intolerance alert; no rules / DB / history needed."""
    rx = {
        "rxId": "rx-4",
        "patient": {"id": "P001", "amka": "15031962456"},
        "medication": {"atcCode": "J01CA01"},  # amoxicillin-family
    }
    result = asyncio.run(evaluate_safety(session=None, rx=rx, pharmacy_id=uuid.uuid4(), rules=[]))
    assert len(result.checks) == 1
    alert = result.checks[0]
    assert alert.check_type == "contraindications"
    assert "Amoxicillin" in alert.message
