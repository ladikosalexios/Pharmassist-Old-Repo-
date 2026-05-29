"""Unit tests for the Pharmapi v2 parsers — no DB, no network.

Covers `_parse_prescription_search_json` (the JSON search→queue mapper) and
`_map_pharmapi_status` (ΗΔΥΚΑ status string → internal PrescriptionStatus).
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

from app.constants import PrescriptionStatus  # noqa: E402
from app.services.pharmapi import (  # noqa: E402
    _map_pharmapi_status,
    _parse_prescription_search_json,
)

# A full v2 search item as ΗΔΥΚΑ returns it under `contents[*]`.
_VALID_ITEM = {
    "id": 88234,
    "barcode": "1234567890123456",
    "status": "ACTIVE",
    "issueDate": "2026-04-09",
    "expiryDate": "2026-05-09",
    "patientName": "Μαρία Παπαδάκη",
    "amka": "12345678901",
    "doctorName": "Δρ. Αθανάσιος Νικολάου",
    "socialInsurance": {"id": 1, "name": "ΕΟΠΥΓ"},
    "medicines": [{"barcode": "5201234567890", "name": "Brufen 400mg tabs", "quantity": 2}],
    "repeatNo": 1,
    "totalRepeats": 3,
}


# ── _parse_prescription_search_json ──────────────────────────────────────────


def test_parse_valid_item_maps_all_fields():
    [out] = _parse_prescription_search_json([_VALID_ITEM])
    assert out["rxId"] == "1234567890123456"
    assert out["patientName"] == "Μαρία Παπαδάκη"
    assert out["patientAmka"] == "12345678901"
    assert out["medication"] == "Brufen 400mg tabs"
    assert out["medicineBarcode"] == "5201234567890"
    assert out["physician"] == "Δρ. Αθανάσιος Νικολάου"
    assert out["date"] == "2026-04-09"
    assert out["expiryDate"] == "2026-05-09"
    assert out["status"] == PrescriptionStatus.PENDING  # ACTIVE → PENDING
    assert out["pharmApiStatus"] == "ACTIVE"
    assert out["socialInsurance"] == "ΕΟΠΥΓ"
    assert out["repeatNo"] == 1
    assert out["totalRepeats"] == 3
    assert out["medicineDrug"] is False
    assert out["executions"] is None


def test_parse_empty_list_returns_empty():
    assert _parse_prescription_search_json([]) == []


def test_parse_missing_medicines_key_no_keyerror():
    item = {k: v for k, v in _VALID_ITEM.items() if k != "medicines"}
    [out] = _parse_prescription_search_json([item])
    assert out["medication"] is None
    assert out["medicineBarcode"] is None


def test_parse_missing_patient_name_falls_back():
    item = {k: v for k, v in _VALID_ITEM.items() if k != "patientName"}
    [out] = _parse_prescription_search_json([item])
    assert out["patientName"] == "Άγνωστος"


# ── _map_pharmapi_status ─────────────────────────────────────────────────────


def test_map_known_statuses():
    assert _map_pharmapi_status("ACTIVE") == PrescriptionStatus.PENDING
    assert _map_pharmapi_status("PENDING") == PrescriptionStatus.PENDING
    assert _map_pharmapi_status("PARTIAL") == PrescriptionStatus.PENDING
    assert _map_pharmapi_status("COMPLETED") == PrescriptionStatus.COMPLETED
    assert _map_pharmapi_status("EXECUTED") == PrescriptionStatus.COMPLETED
    assert _map_pharmapi_status("CANCELLED") == PrescriptionStatus.FLAGGED
    assert _map_pharmapi_status("EXPIRED") == PrescriptionStatus.FLAGGED


def test_map_is_case_insensitive():
    assert _map_pharmapi_status("active") == PrescriptionStatus.PENDING
    assert _map_pharmapi_status(" Completed ") == PrescriptionStatus.COMPLETED


def test_map_unknown_string_returns_unknown():
    assert _map_pharmapi_status("WAT") == PrescriptionStatus.UNKNOWN


def test_map_none_and_empty_return_unknown():
    assert _map_pharmapi_status(None) == PrescriptionStatus.UNKNOWN
    assert _map_pharmapi_status("") == PrescriptionStatus.UNKNOWN
