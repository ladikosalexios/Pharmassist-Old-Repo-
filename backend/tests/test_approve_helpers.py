"""Unit tests for the small helpers behind POST /prescriptions/{rx_id}/approve.

The full handler is exercised by the docker-stack smoke (login → approve →
SELECT dispense_logs); these tests pin the deterministic helpers in
isolation so a contract regression fails fast in CI without needing the DB.
"""

from __future__ import annotations

import base64
import os

os.environ.setdefault("ENV", "test")
os.environ.setdefault("PHARMAPI_MOCK", "true")
os.environ.setdefault("COOKIE_SECURE", "false")
os.environ.setdefault("CREDENTIAL_ENCRYPTION_KEY", base64.b64encode(b"\x01" * 32).decode())
os.environ.setdefault("SECRET_KEY", "test-secret-key-do-not-use-in-prod")
os.environ.setdefault("PHARMAPI_USERNAME", "u")
os.environ.setdefault("PHARMAPI_PASSWORD", "p")
os.environ.setdefault("PHARMAPI_API_KEY", "k")
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+asyncpg://pharmassist:pharmassist_dev@localhost:5432/pharmassist_test",
)

from app.routers.prescriptions import _rx_to_dispense_fields  # noqa: E402


def test_rx_to_fields_uses_nhrn_when_medicine_barcode_absent():
    fields = _rx_to_dispense_fields(
        {
            "rxId": "RX2024-001",
            "patient": {"amka": "22071993789"},
            "medication": {"nhrn": "5201234500017"},
        }
    )
    assert fields == {
        "amka": "22071993789",
        "medicine_barcodes": ["5201234500017"],
    }


def test_rx_to_fields_prefers_live_medicine_barcode():
    fields = _rx_to_dispense_fields(
        {
            "rxId": "2411223344556",
            "patientAmka": "ignored-top-level",
            "patient": {"amka": "05055505340"},
            "medicineBarcode": "2802676702022",
            "medication": {"nhrn": "ignored"},
        }
    )
    assert fields["medicine_barcodes"] == ["2802676702022"]
    assert fields["amka"] == "05055505340"


def test_rx_to_fields_empty_when_no_medicine_or_patient():
    fields = _rx_to_dispense_fields({"rxId": "x"})
    assert fields == {"amka": "", "medicine_barcodes": []}


def test_cached_approve_response_reuses_original_metadata():
    """Idempotent return path: the cached receipt MUST surface the original
    exec_ref + dispense_log id + created_at — not "now". A future drift here
    would make retries look like fresh dispenses to the client."""
    import uuid as _uuid
    from datetime import UTC, datetime

    from app.db.models.dispense_log import DispenseLog
    from app.routers.prescriptions import _cached_approve_response

    log = DispenseLog(
        id=_uuid.UUID("76c161dc-e4cb-4b45-9557-ffc526c420d9"),
        pharmacy_id=_uuid.uuid4(),
        pharmacist_id=_uuid.uuid4(),
        barcode="RX2024-001",
        exec_ref="MOCK-EXEC-D7A9F91349D1",
        request_cda="",
        response_cda="<x/>",
        request_id="req-original",
    )
    log.created_at = datetime(2026, 6, 9, 1, 45, 33, tzinfo=UTC)

    resp = _cached_approve_response(log)
    assert resp.success is True
    assert resp.idempotent is True
    assert resp.rxId == "RX2024-001"
    assert resp.status == "COMPLETED"
    assert resp.execId == "MOCK-EXEC-D7A9F91349D1"
    assert resp.executionNo == "MOCK-EXEC-D7A9F91349D1"
    assert resp.dispenseLogId == "76c161dc-e4cb-4b45-9557-ffc526c420d9"
    assert resp.documentationLogId is None  # No new counsel log on retry.
    # Truthful timestamp — the moment of the ORIGINAL dispense, not "now".
    assert resp.completedAt == "2026-06-09T01:45:33+00:00"
