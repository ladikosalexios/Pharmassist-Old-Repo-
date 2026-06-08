"""HMVS service tests — OAuth2 token caching, status mapping, mock canned
responses, and the double-supply idempotency guard.

Mirrors tests/test_pharmapi_g14_retry.py: env vars are set before importing app
modules (get_settings is lru_cached and modules snapshot settings at import),
and async coroutines run via asyncio.run inside sync test functions (no
pytest-asyncio dependency).

The HTTP layer is driven by httpx.MockTransport injected through the service's
``_transport_override`` seam — no network, no real ITE sandbox.
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

from app.services import hmvs  # noqa: E402

CID, SECRET = "client-abc", "secret-xyz"


# ── Test scaffolding ──────────────────────────────────────────────────────────


def _make_transport(state: dict) -> httpx.MockTransport:
    """Route token / GET-verify / PATCH-state to canned responses, counting
    how many times the token endpoint is hit (to prove caching)."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/identity/connect/token"):
            state["token_calls"] += 1
            return httpx.Response(
                200,
                json={
                    "access_token": f"tok-{state['token_calls']}",
                    "expires_in": state.get("expires_in", 3600),
                    "token_type": "Bearer",
                },
            )
        if request.method == "GET":
            status, body = state["verify"]
            return httpx.Response(status, json=body)
        if request.method == "PATCH":
            status, body = state["patch"]
            return httpx.Response(status, json=body)
        return httpx.Response(500, json={})

    return httpx.MockTransport(handler)


@pytest.fixture(autouse=True)
def _reset_hmvs(monkeypatch):
    """Fresh token cache + no transport before each test; live mode unless a
    test opts back into mock."""
    hmvs._token_cache.clear()
    hmvs._transport_override = None
    monkeypatch.setenv("HMVS_MOCK", "false")
    yield
    hmvs._token_cache.clear()
    hmvs._transport_override = None


def _install(state: dict) -> None:
    hmvs._transport_override = _make_transport(state)


# ── OAuth2 token caching ──────────────────────────────────────────────────────


def test_token_is_fetched_once_then_cached():
    state = {
        "token_calls": 0,
        "verify": (200, {"operationCode": "OK", "state": "Active"}),
        "patch": (200, {}),
    }
    _install(state)

    asyncio.run(hmvs.verify("G", "S1", "B", "260101", client_id=CID, client_secret=SECRET))
    asyncio.run(hmvs.verify("G", "S2", "B", "260101", client_id=CID, client_secret=SECRET))

    assert state["token_calls"] == 1  # second verify reused the cached Bearer token


def test_token_refreshes_after_expiry():
    state = {
        "token_calls": 0,
        "verify": (200, {"operationCode": "OK", "state": "Active"}),
        "patch": (200, {}),
    }
    _install(state)

    asyncio.run(hmvs.verify("G", "S1", "B", "260101", client_id=CID, client_secret=SECRET))
    # Force the cached token past its expiry window.
    hmvs._token_cache[CID]["expires_at_ts"] = 0
    asyncio.run(hmvs.verify("G", "S2", "B", "260101", client_id=CID, client_secret=SECRET))

    assert state["token_calls"] == 2


# ── Status / structure mapping ────────────────────────────────────────────────


def test_verify_200_parses_full_structure():
    state = {
        "token_calls": 0,
        "verify": (
            200,
            {
                "operationCode": "NMVS_OK",
                "state": "Active",
                "nhrn": "GR-0001-0002-0003",
                "isIntermarket": False,
                "information": "Pack verified.",
            },
        ),
        "patch": (200, {}),
    }
    _install(state)

    r = asyncio.run(hmvs.verify("G", "S", "B", "260101", client_id=CID, client_secret=SECRET))

    assert r.ok and r.http_status == 200
    assert r.state == "Active"
    assert r.operation_code == "NMVS_OK"
    assert r.nhrn == "GR-0001-0002-0003"
    assert r.is_intermarket is False
    assert r.information == "Pack verified."


@pytest.mark.parametrize("status", [403, 404, 422])
def test_verify_error_statuses_are_not_ok(status):
    state = {
        "token_calls": 0,
        "verify": (status, {"operationCode": "NMVS_NC_PCK_22"}),
        "patch": (200, {}),
    }
    _install(state)

    r = asyncio.run(hmvs.verify("G", "S", "B", "260101", client_id=CID, client_secret=SECRET))

    assert not r.ok
    assert r.http_status == status
    assert r.operation_code == "NMVS_NC_PCK_22"


def test_change_state_200_supply():
    state = {
        "token_calls": 0,
        "verify": (200, {}),
        "patch": (200, {"operationCode": "NMVS_OK", "state": "Supplied", "nhrn": "GR-1"}),
    }
    _install(state)

    r = asyncio.run(
        hmvs.change_state(
            "G", "S", "B", "260101", target_state="Supplied", client_id=CID, client_secret=SECRET
        )
    )

    assert r.ok and r.state == "Supplied" and r.nhrn == "GR-1"


def test_change_state_409_surfaces_current_state():
    state = {
        "token_calls": 0,
        "verify": (200, {}),
        "patch": (409, {"operationCode": "NMVS_NC_PCK_19", "state": "Supplied"}),
    }
    _install(state)

    r = asyncio.run(
        hmvs.change_state(
            "G", "S", "B", "260101", target_state="Supplied", client_id=CID, client_secret=SECRET
        )
    )

    assert not r.ok and r.http_status == 409
    assert r.current_state == "Supplied"


def test_change_state_429_is_not_ok():
    state = {"token_calls": 0, "verify": (200, {}), "patch": (429, {})}
    _install(state)

    r = asyncio.run(
        hmvs.change_state(
            "G", "S", "B", "260101", target_state="Supplied", client_id=CID, client_secret=SECRET
        )
    )

    assert not r.ok and r.http_status == 429


# ── Mock mode (HMVS_MOCK=true) — no transport, no token ────────────────────────


def test_mock_mode_returns_canned_results(monkeypatch):
    monkeypatch.setenv("HMVS_MOCK", "true")
    hmvs._transport_override = None  # prove no network is touched

    ok = asyncio.run(hmvs.verify("G", "SMOKE-1", "B", "260101", client_id="", client_secret=""))
    assert ok.ok and ok.state == "Active" and ok.nhrn

    missing = asyncio.run(
        hmvs.verify("G", "404-PACK", "B", "260101", client_id="", client_secret="")
    )
    assert not missing.ok and missing.http_status == 404

    dup = asyncio.run(
        hmvs.change_state(
            "G", "409-PACK", "B", "260101", target_state="Supplied", client_id="", client_secret=""
        )
    )
    assert not dup.ok and dup.http_status == 409 and dup.current_state == "Supplied"


# ── Idempotency guard (double-supply prevention) ──────────────────────────────


class _FakeHmvsSession:
    """In-memory stand-in for the AsyncSession: stores the single operation in
    play and serves it back. Enough for the guard's load → add → reload path."""

    def __init__(self):
        self._op = None
        self.commits = 0

    async def scalar(self, _stmt):
        return self._op

    def add(self, obj):
        self._op = obj

    async def flush(self):
        pass

    async def rollback(self):
        pass

    async def commit(self):
        self.commits += 1


def test_idempotent_supply_does_not_double_supply(monkeypatch):
    calls = {"n": 0}

    async def _counting_change_state(*_a, **_k):
        calls["n"] += 1
        return hmvs.HmvsResult(
            ok=True, http_status=200, operation_code="NMVS_OK", state="Supplied", nhrn="GR-1"
        )

    monkeypatch.setattr(hmvs, "change_state", _counting_change_state)
    session = _FakeHmvsSession()
    args = dict(
        pharmacist_id=uuid.uuid4(),
        pharmacy_id=uuid.uuid4(),
        gtin="G",
        serial="S",
        batch="B",
        expiry="260101",
        target_state="Supplied",
        client_id=CID,
        client_secret=SECRET,
    )

    r1 = asyncio.run(hmvs.change_state_idempotent(session, **args))
    r2 = asyncio.run(hmvs.change_state_idempotent(session, **args))

    assert r1.ok and r1.state == "Supplied"
    assert r2.ok and r2.state == "Supplied"  # cached, reconstructed from the row
    assert calls["n"] == 1  # the second supply NEVER hit the registry
