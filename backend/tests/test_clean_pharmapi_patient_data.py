"""Unit tests for clean_pharmapi_patient_data.

Covers the AMKA branch, EKAA-fallback branch, and the both-absent error case.
The function has no I/O — it is pure data transformation — so no mocking is needed.
"""

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

import pytest  # noqa: E402
from fastapi import HTTPException  # noqa: E402

from app.services.pharmapi import clean_pharmapi_patient_data  # noqa: E402

_BASE = {
    "dateOfBirth": "1990-06-15",
    "firstName": "Test",
    "lastName": "Patient",
    "sex": "M",
    "mobile": "6900000000",
}


def test_amka_branch():
    data = {**_BASE, "amka": "15031962456"}
    result = clean_pharmapi_patient_data(data)
    assert result.id == "15031962456"
    assert result.amka == "15031962456"
    assert result.ekaa is None


def test_ekaa_fallback_branch():
    data = {**_BASE, "ekaa": "GR1234567890123456"}
    result = clean_pharmapi_patient_data(data)
    assert result.id == "GR1234567890123456"
    assert result.amka is None
    assert result.ekaa == "GR1234567890123456"


def test_amka_takes_priority_when_both_present():
    data = {**_BASE, "amka": "15031962456", "ekaa": "GR1234567890123456"}
    result = clean_pharmapi_patient_data(data)
    assert result.id == "15031962456"
    assert result.amka == "15031962456"
    assert result.ekaa == "GR1234567890123456"


def test_raises_502_when_both_absent():
    with pytest.raises(HTTPException) as exc_info:
        clean_pharmapi_patient_data(_BASE)
    assert exc_info.value.status_code == 502
