"""Router-level tests for the HMVS auth-failure mapping (F1).

A non-2xx OAuth2 token response previously surfaced as an opaque 500 with no
audit row — the dispense was silently un-attributable. The router now catches
``httpx.HTTPStatusError`` from ``_get_token`` and maps it to **502 "HMVS auth
failed"** + an ``audit_log`` row.

This file uses the same env-vars-first / TestClient-with-overrides pattern as
``test_endpoints_integration.py`` but stays self-contained: ``_resolve_credentials``,
the session dep, and the audit fire-and-forget are all overridden so the test
needs no DB.
"""

import asyncio
import base64
import os
import uuid

os.environ.setdefault("HMVS_MOCK", "true")
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

import httpx  # noqa: E402
import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.db.session import get_session  # noqa: E402
from app.deps import get_current_user  # noqa: E402
from app.routers import hmvs as hmvs_router  # noqa: E402
from app.services import audit as audit_service  # noqa: E402
from app.services import hmvs as hmvs_service  # noqa: E402
from main import create_app  # noqa: E402

PHARMACIST_ID = "00000000-0000-0000-0000-000000000001"
PHARMACY_ID = "00000000-0000-0000-0000-000000000002"


def _fake_current() -> dict:
    return {
        "pharmacist_id": PHARMACIST_ID,
        "pharmacy_id": PHARMACY_ID,
        "pharmacy": "Test Pharmacy",
        "email": "t@example.com",
        "name": "Test",
        "eof_licence_no": "EOF-0",
        "role": "pharmacist",
    }


async def _fake_session():
    """The router only touches the session inside ``_resolve_credentials``, which
    we override below — yielding ``None`` is enough to satisfy the dependency."""
    yield None


@pytest.fixture
def client(monkeypatch):
    """Fresh app with: auth bypassed, DB skipped, mock mode OFF, and the
    audit fire-and-forget made synchronous so the test can inspect the row.

    Switching HMVS_MOCK to false routes ``hmvs.verify`` / ``change_state`` into
    ``_get_token``, where our injected MockTransport returns the failure we want
    to exercise."""
    monkeypatch.setenv("HMVS_MOCK", "false")

    async def _resolve_creds_ok(_db, _pid):
        return "client-abc", "secret-xyz"

    monkeypatch.setattr(hmvs_router, "_resolve_credentials", _resolve_creds_ok)

    # The PATCH route calls change_state_idempotent which would hit the DB for
    # the idempotency lookup *before* reaching _get_token. We replace it with a
    # thin shim that calls change_state directly — the token fetch raises there,
    # which is the path under test. The full idempotency guard has its own
    # coverage in test_hmvs.py.
    async def _direct_change_state(
        _session,
        *,
        pharmacist_id,
        pharmacy_id,
        gtin,
        serial,
        batch,
        expiry,
        target_state,
        client_id,
        client_secret,
    ):
        return await hmvs_service.change_state(
            gtin,
            serial,
            batch,
            expiry,
            target_state=target_state,
            client_id=client_id,
            client_secret=client_secret,
        )

    monkeypatch.setattr(hmvs_service, "change_state_idempotent", _direct_change_state)

    # Make the audit fire-and-forget synchronous + recorded, so the assertion
    # against "wrote an audit row" doesn't race the test process exit.
    captured: list[dict] = []

    def _capture_audit(**kwargs):
        captured.append(kwargs)

    monkeypatch.setattr(hmvs_router, "fire_hmvs_audit", _capture_audit)

    app = create_app()
    app.dependency_overrides[get_current_user] = _fake_current
    app.dependency_overrides[get_session] = _fake_session

    hmvs_service._token_cache.clear()
    hmvs_service._transport_override = None

    with TestClient(app) as c:
        c.captured_audit = captured  # type: ignore[attr-defined]
        yield c

    hmvs_service._token_cache.clear()
    hmvs_service._transport_override = None


def _install_token_failure(status: int = 401) -> None:
    """Make every token request fail with the given status — the verify/PATCH
    branches never run because _get_token raises first."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/identity/connect/token"):
            return httpx.Response(status, json={"error": "invalid_client"})
        return httpx.Response(500, json={})

    hmvs_service._transport_override = httpx.MockTransport(handler)


def test_verify_token_401_returns_502_with_audit(client):
    _install_token_failure(401)

    r = client.get(
        "/pharmapi/hmvs/product/gs1/G/pack/S",
        params={"batch": "B", "expiry": "260101"},
    )

    assert r.status_code == 502
    assert r.json()["detail"] == "HMVS auth failed"

    # Audit row written with the intended action + 502 status (no opaque 500).
    audit_rows = client.captured_audit  # type: ignore[attr-defined]
    assert len(audit_rows) == 1
    row = audit_rows[0]
    assert row["action"] == "HMVS_VERIFIED"
    assert row["pharmapi_status"] == 502
    assert row["resource_id"] == "S"
    assert row["pharmacist_id"] == uuid.UUID(PHARMACIST_ID)


def test_change_state_token_403_returns_502_with_audit(client):
    _install_token_failure(403)

    r = client.patch(
        "/pharmapi/hmvs/product/gs1/G/pack/S",
        params={"batch": "B", "expiry": "260101"},
        json={"state": "Supplied"},
    )

    assert r.status_code == 502
    assert r.json()["detail"] == "HMVS auth failed"

    audit_rows = client.captured_audit  # type: ignore[attr-defined]
    assert len(audit_rows) == 1
    row = audit_rows[0]
    # Supplied → DECOMMISSIONED; Active would map to REACTIVATED.
    assert row["action"] == "HMVS_DECOMMISSIONED"
    assert row["pharmapi_status"] == 502


def test_log_hmvs_action_is_async_safe():
    """Sanity: the audit coroutine itself is awaitable — guards against an
    accidental signature drift breaking fire_hmvs_audit at runtime."""
    coro = audit_service.log_hmvs_action(
        pharmacist_id=uuid.UUID(PHARMACIST_ID),
        pharmacy_id=uuid.UUID(PHARMACY_ID),
        action="HMVS_VERIFIED",
        resource_id="S",
        pharmapi_path="/pharmapi/hmvs/product/gs1/G/pack/S",
        pharmapi_status=502,
    )
    assert asyncio.iscoroutine(coro)
    coro.close()
