"""Tests for parse_prescription_cda (Άντληση Συνταγής retrieval parser).

Fixture is SYNTHETIC (tests/fixtures/cda/prescription_get_sample.xml) — no real
PHI — but its structure mirrors a live testeps prescription so the parser's
element paths stay honest.
"""

from __future__ import annotations

import base64
import os

# Settings are @lru_cache-d, so every required secret must be set BEFORE the
# first `from app.*` import (matches test_pharmapi_dispense.py / test_auth_db.py).
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

from pathlib import Path  # noqa: E402

from app.constants import PrescriptionStatus  # noqa: E402
from app.services.cda import parse_prescription_cda  # noqa: E402
from app.services.pharmapi import _map_pharmapi_status  # noqa: E402

FIXTURE = Path(__file__).parent / "fixtures" / "cda" / "prescription_get_sample.xml"


def _parsed():
    return parse_prescription_cda(FIXTURE.read_bytes())


def test_extracts_barcode_and_patient():
    p = _parsed()
    assert p.barcode == "2606094071443"
    assert p.patient_amka == "01010003430"
    assert p.patient_name == "TEST PATIENT"
    assert p.physician == "DOC WHO"


def test_extracts_validity_dates():
    p = _parsed()
    assert p.issue_date == "2026-06-09"
    assert p.expiry_date == "2027-06-09"


def test_extracts_medicine_line_with_real_therapy_id():
    p = _parsed()
    assert len(p.lines) == 1
    line = p.lines[0]
    # The real per-line therapy id (id[@root='1.21.1']) — NOT a synthetic one.
    assert line.line_id == "2606094071443-1"
    assert line.medicine_code == "093360504"  # ΕΟΦ code
    assert line.medicine_barcode == "2800933605048"  # narrative #med_barcode_1 EAN
    assert line.status == "active"


def test_to_rx_dict_matches_search_shape():
    rx = _parsed().to_rx_dict(status_mapper=_map_pharmapi_status)
    # Same keys the /search path emits, so downstream is unchanged.
    for key in (
        "rxId",
        "patientName",
        "patientAmka",
        "medication",
        "medicineBarcode",
        "physician",
        "date",
        "expiryDate",
        "status",
        "pharmApiStatus",
        "therapyLines",
    ):
        assert key in rx, f"missing key {key}"
    assert rx["rxId"] == "2606094071443"
    assert rx["medicineBarcode"] == "2800933605048"
    # "active" maps to PENDING (awaiting dispense) via _map_pharmapi_status.
    assert rx["status"] == PrescriptionStatus.PENDING
    assert rx["pharmApiStatus"] == "active"
    # therapyLines carries the real per-line id the eDispensation must echo.
    assert rx["therapyLines"][0]["lineId"] == "2606094071443-1"
    assert rx["therapyLines"][0]["medicineBarcode"] == "2800933605048"


def test_dispense_items_use_real_therapy_line():
    """The router maps therapyLines → DispenseItem with the real 1.21.1 id."""
    from app.routers.prescriptions import _rx_to_dispense_items

    rx = _parsed().to_rx_dict(status_mapper=_map_pharmapi_status)
    items = _rx_to_dispense_items(rx)
    assert len(items) == 1
    assert items[0].therapy_line_id == "2606094071443-1"
    assert items[0].medicine_barcode == "2800933605048"
    # Without a scanned pack, the lot stays the synthetic ΕΟΦ-strip placeholder.
    assert items[0].dispense_mode == 0
    assert items[0].lot_number == "000000000000"


def test_dispense_items_with_scanned_pack_carry_real_qr():
    """A supplied HMVS pack turns the line into dispense_mode=1 with real GS1
    data — the real ΕΟΦ/QR serial replaces the placeholder ΗΔΥΚΑ rejects."""
    from app.routers.prescriptions import _rx_to_dispense_items
    from app.schemas.prescriptions import DispensePack
    from app.services.cda import build_dispense_cda

    rx = _parsed().to_rx_dict(status_mapper=_map_pharmapi_status)
    pack = DispensePack(
        gtin="05210330200000", serial="SCP2GR:ABCDEFGHIJKLM", batch="SCB1GR", expiry="320101"
    )
    items = _rx_to_dispense_items(rx, [pack])
    assert len(items) == 1
    it = items[0]
    assert it.therapy_line_id == "2606094071443-1"  # still the real therapy line
    assert it.dispense_mode == 1  # HMVS QR
    assert it.lot_number == "SCP2GR:ABCDEFGHIJKLM"  # serial is the lot
    assert it.qr_product_code == "05210330200000"
    assert it.qr_batch_no == "SCB1GR"
    assert it.qr_expiry == "320101"
    # And the result must still satisfy the CDA builder (dispense_mode=1 requires
    # qr_* — a missing one would raise).
    cda = build_dispense_cda(barcode="2606094071443", pharmacy_unit_id=70014, items=items)
    assert b"SCP2GR:ABCDEFGHIJKLM" in cda
