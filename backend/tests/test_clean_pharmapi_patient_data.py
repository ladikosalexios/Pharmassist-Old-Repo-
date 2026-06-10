"""Unit tests for clean_pharmapi_patient_data — no DB, no network.

Exercises the v2 camelCase /common/getpatient normaliser, including the
EKAA fallback (ΗΔΥΚΑ returns the European id under `identificationNo`) and
the both-identifiers-absent guard.
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

# Real-shaped camelCase response from GET /api/v1/common/getpatient.
_AMKA_PATIENT = {
    "firstName": "ONOMA-A",
    "lastName": "EPONYMO-A",
    "amka": "01010003430",
    "sex": {"id": 2, "name": "Θήλυ"},
    "birthDate": "2018-01-01",
    "telephone": "2109823392",
    "email": "test@test.gr",
}


def test_amka_patient_maps_correctly():
    p = clean_pharmapi_patient_data(_AMKA_PATIENT)
    assert p.id == "01010003430"
    assert p.amka == "01010003430"
    assert p.ekaa is None
    assert p.first_name == "ONOMA-A"
    assert p.last_name == "EPONYMO-A"
    assert p.date_of_birth == "2018-01-01"
    assert p.sex == "Θήλυ"  # flattened from the {id, name} object
    assert p.phone == "2109823392"
    assert isinstance(p.age, int)
    # Key absent upstream → None (distinct from supplied-but-empty []).
    assert p.participation_exceptions is None


def test_participation_exceptions_map():
    # Real shape from the FT-2 probe: patientPartExceptions on /common/getpatient.
    data = {
        **_AMKA_PATIENT,
        "patientPartExceptions": [
            {
                "id": 7,
                "exceptionReason": "Χρόνια πάθηση",
                "effectiveFrom": "2025-01-01",
                "effectiveTo": None,
            }
        ],
    }
    p = clean_pharmapi_patient_data(data)
    assert p.participation_exceptions is not None
    (exc,) = p.participation_exceptions
    assert exc.id == 7
    assert exc.reason == "Χρόνια πάθηση"
    assert exc.effective_from == "2025-01-01"
    assert exc.effective_to is None


def test_participation_exceptions_empty_list_is_preserved():
    p = clean_pharmapi_patient_data({**_AMKA_PATIENT, "patientPartExceptions": []})
    assert p.participation_exceptions == []


def test_ekaa_fallback_when_amka_absent():
    # ΗΔΥΚΑ exposes the European identifier under `identificationNo`.
    data = {
        **_AMKA_PATIENT,
        "amka": None,
        "identificationNo": "GR-EKAA-001",
        "sex": {"id": 1, "name": "Άρρεν"},
    }
    p = clean_pharmapi_patient_data(data)
    assert p.amka is None
    assert p.ekaa == "GR-EKAA-001"
    assert p.id == "GR-EKAA-001"  # id falls back to the EKAA
    assert p.sex == "Άρρεν"


def test_raises_502_when_no_identifier():
    data = {k: v for k, v in _AMKA_PATIENT.items() if k != "amka"}
    with pytest.raises(HTTPException) as exc:
        clean_pharmapi_patient_data(data)
    assert exc.value.status_code == 502
