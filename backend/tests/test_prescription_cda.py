"""Tests for parse_prescription_cda (Άντληση Συνταγής retrieval parser).

Fixture is SYNTHETIC (tests/fixtures/cda/prescription_get_sample.xml) — no real
PHI — but its structure mirrors a live testeps prescription so the parser's
element paths stay honest.
"""

from __future__ import annotations

import base64
import os

# Settings are @lru_cache-d, so every required secret must be set BEFORE the
# first `from app.*` import (matches test_auth_db.py).
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
    # therapyLines carries the real per-line id from the source CDA.
    assert rx["therapyLines"][0]["lineId"] == "2606094071443-1"
    assert rx["therapyLines"][0]["medicineBarcode"] == "2800933605048"


def test_empty_cda_lines_raises_502_in_service(monkeypatch):
    """A 200 from /prescriptions/get/{barcode} whose CDA carries zero medicine
    lines must fail loudly upstream — sending an empty supply CDA downstream
    would produce a schema-invalid request to ΗΔΥΚΑ."""
    import asyncio

    import httpx
    from fastapi import HTTPException

    from app.services import pharmapi

    empty_cda = (
        b'<?xml version="1.0" encoding="UTF-8"?>'
        b'<ClinicalDocument xmlns="urn:hl7-org:v3">'
        b'<id extension="EMPTY-RX" root="1.21"/>'
        b"<component><structuredBody><component><section>"
        b"</section></component></structuredBody></component>"
        b"</ClinicalDocument>"
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=empty_cda)

    transport = httpx.MockTransport(handler)
    real_client = httpx.AsyncClient

    def patched_client(*args, **kwargs):
        kwargs["transport"] = transport
        return real_client(*args, **kwargs)

    monkeypatch.setattr(pharmapi.httpx, "AsyncClient", patched_client)

    try:
        asyncio.run(
            pharmapi.pharmapi_get_prescription(
                barcode="EMPTY-RX", pharmacy_id=70014, doctor_ip="1.1.1.1"
            )
        )
    except HTTPException as exc:
        assert exc.status_code == 502
        assert "no medicine lines" in exc.detail
    else:
        raise AssertionError("expected HTTPException 502 for empty-lines CDA")
