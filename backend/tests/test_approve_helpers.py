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

from app.routers.prescriptions import _rx_to_dispense_items  # noqa: E402
from app.services.cda import build_dispense_cda, parse_dispense_response  # noqa: E402


def test_rx_to_items_uses_nhrn_when_medicine_barcode_absent():
    items = _rx_to_dispense_items(
        {
            "rxId": "RX2024-001",
            "medication": {"nhrn": "5201234500017"},
        }
    )
    assert len(items) == 1
    assert items[0].medicine_barcode == "5201234500017"
    assert items[0].therapy_line_id == "RX2024-001-L1"
    assert items[0].dispense_mode == 0  # ΕΟΦ strip
    assert items[0].consent == 1


def test_rx_to_items_prefers_live_medicine_barcode():
    items = _rx_to_dispense_items(
        {
            "rxId": "2411223344556",
            "medicineBarcode": "2802676702022",
            "medication": {"nhrn": "ignored"},
        }
    )
    assert items[0].medicine_barcode == "2802676702022"


def test_rx_to_items_roundtrips_through_cda_builder():
    """Whatever the helper emits must satisfy build_dispense_cda — guards
    against an accidental change to the helper that produces unbuildable
    items (e.g. dispense_mode=1 with no qr_*)."""
    items = _rx_to_dispense_items({"rxId": "RX2024-005", "medication": {"nhrn": "5201234500017"}})
    cda = build_dispense_cda(barcode="RX2024-005", pharmacy_unit_id=6543, items=items)
    # Sanity: must contain the barcode and the synthetic therapy id.
    text = cda.decode("utf-8")
    assert "RX2024-005-L1" in text
    assert "5201234500017" in text


def test_mock_envelope_parses_round_trip(monkeypatch):
    """Belt-and-braces — the mock branch's stub CDA must round-trip through
    parse_dispense_response. Already covered in test_pharmapi_dispense; mirrored
    here so a Phase-3 refactor of the mock template doesn't slip past."""
    from app.services.pharmapi import _mock_dispense_envelope

    env = _mock_dispense_envelope("2411223344556")
    parsed = parse_dispense_response(env["response_cda"])
    assert parsed.exec_ref == env["exec_ref"]
    assert parsed.barcode == "2411223344556"
