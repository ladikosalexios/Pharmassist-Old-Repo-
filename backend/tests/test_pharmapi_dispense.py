"""Tests for app.services.pharmapi.pharmapi_dispense.

Mock-mode envelope shape parity is the load-bearing assertion: the router
and dispense_log writer must work identically against the mock and live
branches.

Mirrors test_hmvs.py — env vars set before app imports; async coroutines
driven via asyncio.run inside sync tests so the suite stays
pytest-asyncio-free.

NOTE: live-mode tests are minimal until the exact ΗΔΥΚΑ dispense endpoint
is confirmed (see TODO at top of services/pharmapi.py dispense section).
"""

from __future__ import annotations

import asyncio
import base64
import os

# Match the env-setup pattern in test_auth_db.py — settings are @lru_cache-d so
# every required secret must be set BEFORE the first `from app.*` import.
os.environ["ENV"] = "test"
os.environ["PHARMAPI_MOCK"] = "true"
os.environ["COOKIE_SECURE"] = "false"
os.environ.setdefault("CREDENTIAL_ENCRYPTION_KEY", base64.b64encode(b"\x01" * 32).decode())
os.environ.setdefault("SECRET_KEY", "test-secret-key-do-not-use-in-prod")
os.environ.setdefault("PHARMAPI_USERNAME", "test-pharmapi-user")
os.environ.setdefault("PHARMAPI_PASSWORD", "test-pharmapi-pass")
os.environ.setdefault("PHARMAPI_API_KEY", "test-pharmapi-key")
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+asyncpg://pharmassist:pharmassist_dev@localhost:5432/pharmassist_test",
)

import pytest  # noqa: E402

from app.services import pharmapi as pharmapi_module  # noqa: E402


def _call_dispense(**overrides):
    args = {
        "barcode": "2411223344556",
        "pharmacy_id": 6543,
        "amka": "05055505340",
        "medicine_barcodes": ["2802676702022"],
        "eof_licence_no": "EOF-12345",
        "doctor_ip": "10.0.0.1",
    }
    args.update(overrides)
    return asyncio.run(pharmapi_module.pharmapi_dispense(**args))


def test_mock_envelope_shape():
    os.environ["PHARMAPI_MOCK"] = "true"
    envelope = _call_dispense()
    assert set(envelope.keys()) >= {
        "exec_ref",
        "executed_at",
        "status",
        "barcode",
        "response_xml",
    }
    assert envelope["status"] == "EXECUTED"
    assert envelope["barcode"] == "2411223344556"
    assert envelope["exec_ref"].startswith("MOCK-EXEC-")


def test_doctor_ip_required():
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as excinfo:
        _call_dispense(doctor_ip="")
    assert excinfo.value.status_code == 500
    assert "X-DOCTOR-IP" in excinfo.value.detail


def test_live_endpoint_pending_501(monkeypatch):
    """Until the exact ΗΔΥΚΑ dispense endpoint + DTO is confirmed, live mode
    raises 501 — preserves the fail-closed behaviour the brief asked for.
    """
    from fastapi import HTTPException

    monkeypatch.setenv("PHARMAPI_MOCK", "false")
    with pytest.raises(HTTPException) as excinfo:
        _call_dispense()
    assert excinfo.value.status_code == 501
    assert "TODO" in excinfo.value.detail or "not yet confirmed" in excinfo.value.detail.lower()


def test_build_request_xml_contains_required_fields():
    xml_bytes = pharmapi_module._build_dispense_request_xml(
        barcode="2411223344556",
        pharmacy_id=6543,
        amka="05055505340",
        medicine_barcodes=["2802676702022", "2802009201024"],
        eof_licence_no="EOF-12345",
    )
    text = xml_bytes.decode("utf-8")
    assert "<pharmacyId>6543</pharmacyId>" in text
    assert "<prescriptionBarcode>2411223344556</prescriptionBarcode>" in text
    assert "<amka>05055505340</amka>" in text
    assert "<eofLicenceNo>EOF-12345</eofLicenceNo>" in text
    assert "<medicineBarcode>2802676702022</medicineBarcode>" in text
    assert "<medicineBarcode>2802009201024</medicineBarcode>" in text
