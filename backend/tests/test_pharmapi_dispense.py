"""Tests for app.services.pharmapi.pharmapi_dispense.

Mock-mode envelope shape parity is the load-bearing assertion: the router
and dispense_log writer in Phase 3 must work identically against the mock
and live branches.

Mirrors test_hmvs.py / test_pharmapi_g14_retry.py — env vars set before app
imports; async coroutines driven via asyncio.run inside sync tests so the
suite stays pytest-asyncio-free.
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

import httpx  # noqa: E402
import pytest  # noqa: E402

from app.services import pharmapi as pharmapi_module  # noqa: E402
from app.services.cda import parse_dispense_response  # noqa: E402


class _StubResponse:
    def __init__(self, status_code: int, text: str, content_type: str = "application/json"):
        self.status_code = status_code
        self.text = text
        self.content = text.encode("utf-8")
        self.headers = {"content-type": content_type}

    def json(self):
        import json as _json

        return _json.loads(self.text)


class _StubClient:
    """Drop-in for httpx.AsyncClient — returns a pre-canned response."""

    def __init__(self, response: _StubResponse):
        self._response = response

    def __call__(self, *_args, **_kwargs):
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return False

    async def post(self, *_args, **_kwargs):
        return self._response


def test_mock_envelope_shape():
    os.environ["PHARMAPI_MOCK"] = "true"
    envelope = asyncio.run(
        pharmapi_module.pharmapi_dispense(
            barcode="2411223344556",
            cda_xml=b"<unused-in-mock/>",
            doctor_ip="10.0.0.1",
        )
    )
    assert set(envelope.keys()) >= {
        "exec_ref",
        "executed_at",
        "status",
        "barcode",
        "response_cda",
    }
    assert envelope["status"] == "EXECUTED"
    assert envelope["barcode"] == "2411223344556"
    assert envelope["exec_ref"].startswith("MOCK-EXEC-")
    # Round-trip parse — the stub CDA must satisfy the same parser the live
    # branch uses, so dispense_log writes are mode-blind.
    parsed = parse_dispense_response(envelope["response_cda"])
    assert parsed.exec_ref == envelope["exec_ref"]
    assert parsed.barcode == envelope["barcode"]


def test_doctor_ip_required():
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as excinfo:
        asyncio.run(
            pharmapi_module.pharmapi_dispense(
                barcode="X",
                cda_xml=b"<x/>",
                doctor_ip="",
            )
        )
    assert excinfo.value.status_code == 500
    assert "X-DOCTOR-IP" in excinfo.value.detail


def test_live_g02_already_executed(monkeypatch):
    """G02 from ΗΔΥΚΑ → 409 'Prescription already executed' (mapped error)."""
    from fastapi import HTTPException

    monkeypatch.setenv("PHARMAPI_MOCK", "false")
    stub = _StubClient(
        _StubResponse(
            409,
            '{"errorCode":"G02","message":"Prescription already executed"}',
        )
    )
    monkeypatch.setattr(httpx, "AsyncClient", stub)

    with pytest.raises(HTTPException) as excinfo:
        asyncio.run(
            pharmapi_module.pharmapi_dispense(
                barcode="2411223344556",
                cda_xml=b"<ClinicalDocument/>",
                doctor_ip="10.0.0.1",
            )
        )
    assert excinfo.value.status_code == 409
    assert "already executed" in excinfo.value.detail.lower()


def test_live_unparseable_response_502s(monkeypatch):
    """200 with garbage body → 502; never persist a success log on this path."""
    from fastapi import HTTPException

    monkeypatch.setenv("PHARMAPI_MOCK", "false")
    # No executionNo in the CDA — parse_dispense_response will raise ValueError.
    stub = _StubClient(_StubResponse(200, "<ClinicalDocument/>", content_type="application/xml"))
    monkeypatch.setattr(httpx, "AsyncClient", stub)

    with pytest.raises(HTTPException) as excinfo:
        asyncio.run(
            pharmapi_module.pharmapi_dispense(
                barcode="X",
                cda_xml=b"<ClinicalDocument/>",
                doctor_ip="10.0.0.1",
            )
        )
    assert excinfo.value.status_code == 502
    assert "unparseable" in excinfo.value.detail.lower()


def test_live_g14_session_expired(monkeypatch):
    """G14 → 401 'session expired'; mirrors the pharmapi_get behaviour."""
    from fastapi import HTTPException

    monkeypatch.setenv("PHARMAPI_MOCK", "false")
    stub = _StubClient(_StubResponse(401, '{"errorCode":"G14","message":"Connection time limit"}'))
    monkeypatch.setattr(httpx, "AsyncClient", stub)

    with pytest.raises(HTTPException) as excinfo:
        asyncio.run(
            pharmapi_module.pharmapi_dispense(
                barcode="X",
                cda_xml=b"<ClinicalDocument/>",
                doctor_ip="10.0.0.1",
            )
        )
    assert excinfo.value.status_code == 401
    assert "G14" in excinfo.value.detail
