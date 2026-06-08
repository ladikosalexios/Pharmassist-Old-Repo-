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
from sqlalchemy.exc import IntegrityError  # noqa: E402

from app.services import hmvs  # noqa: E402

CID, SECRET = "client-abc", "secret-xyz"


# ── Test scaffolding ──────────────────────────────────────────────────────────


def _make_transport(state: dict) -> httpx.MockTransport:
    """Route token / GET-verify / PATCH-state to canned responses, counting
    how many times the token endpoint is hit (to prove caching)."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/identity/connect/token"):
            state["token_calls"] += 1
            token_status = state.get("token_status", 200)
            if token_status != 200:
                return httpx.Response(token_status, json={"error": "invalid_client"})
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
            return httpx.Response(status, json=body, headers=state.get("verify_headers", {}))
        if request.method == "PATCH":
            status, body = state["patch"]
            return httpx.Response(status, json=body, headers=state.get("patch_headers", {}))
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


class _FakeNested:
    """Async CM standing in for session.begin_nested() — propagates exceptions
    (so a flush IntegrityError surfaces) instead of suppressing them."""

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_exc):
        return False


class _FakeHmvsSession:
    """In-memory stand-in for the AsyncSession covering the guard's
    load → add → flush → commit path, plus the lost-insert-race branch (flush
    raises IntegrityError, reload returns the concurrent winner's row)."""

    def __init__(self, *, winner=None, raise_on_flush=False):
        self._op = None
        self._winner = winner
        self._raise_on_flush = raise_on_flush
        self._raced = False
        self.commits = 0

    async def scalar(self, _stmt):
        return self._winner if self._raced else self._op

    def add(self, obj):
        self._op = obj

    async def flush(self):
        if self._raise_on_flush:
            self._raced = True
            raise IntegrityError("duplicate idempotency_key", None, Exception("dup"))

    async def execute(self, _stmt):
        return None

    async def commit(self):
        self.commits += 1

    def begin_nested(self):
        return _FakeNested()


class _FakeScalars:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _FakeReplaySession:
    """Serves a fixed list of pending ops to replay_pending and records commits."""

    def __init__(self, rows):
        self._rows = rows
        self.commits = 0

    async def scalars(self, _stmt):
        return _FakeScalars(self._rows)

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


def test_lost_insert_race_returns_concurrent_winner(monkeypatch):
    calls = {"n": 0}

    async def _counting_change_state(*_a, **_k):
        calls["n"] += 1
        return hmvs.HmvsResult(ok=True, http_status=200, state="Supplied")

    monkeypatch.setattr(hmvs, "change_state", _counting_change_state)

    # A concurrent identical PATCH already completed: our flush hits the UNIQUE
    # constraint, and the post-savepoint reload returns the winner's row.
    winner_snapshot = hmvs.HmvsResult(
        ok=True, http_status=200, operation_code="NMVS_OK", state="Supplied"
    ).to_dict()
    winner = hmvs.HmvsOperation(
        idempotency_key="G:S:B:Supplied",
        target_state="Supplied",
        status="completed",
        operation_code="NMVS_OK",
        response_json=winner_snapshot,
    )
    session = _FakeHmvsSession(winner=winner, raise_on_flush=True)

    r = asyncio.run(
        hmvs.change_state_idempotent(
            session,
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
    )

    assert r.ok and r.state == "Supplied"
    assert calls["n"] == 0  # the winner's row short-circuited; we never PATCHed


def test_replay_pending_marks_completed_failed_and_keeps_throttled(monkeypatch):
    op_ok = hmvs.HmvsOperation(
        idempotency_key="G:OK:B:Supplied",
        gtin="G",
        serial="OK",
        batch="B",
        expiry="260101",
        target_state="Supplied",
        status="pending",
        attempts=0,
    )
    op_fail = hmvs.HmvsOperation(
        idempotency_key="G:FAIL:B:Supplied",
        gtin="G",
        serial="FAIL",
        batch="B",
        expiry="260101",
        target_state="Supplied",
        status="pending",
        attempts=0,
    )
    op_throttle = hmvs.HmvsOperation(
        idempotency_key="G:THR:B:Supplied",
        gtin="G",
        serial="THR",
        batch="B",
        expiry="260101",
        target_state="Supplied",
        status="pending",
        attempts=0,
    )

    async def _change_state(_gtin, serial, *_a, **_k):
        if serial == "OK":
            return hmvs.HmvsResult(
                ok=True, http_status=200, operation_code="NMVS_OK", state="Supplied"
            )
        if serial == "THR":
            return hmvs.HmvsResult(ok=False, http_status=429)  # throttled → stays pending
        return hmvs.HmvsResult(ok=False, http_status=404, operation_code="NMVS_NC_PCK_22")

    monkeypatch.setattr(hmvs, "change_state", _change_state)
    session = _FakeReplaySession([op_ok, op_fail, op_throttle])

    completed = asyncio.run(hmvs.replay_pending(session, client_id=CID, client_secret=SECRET))

    assert completed == 1
    assert op_ok.status == "completed"
    assert op_fail.status == "failed"
    assert op_throttle.status == "pending"  # 429 left pending for the next pass


# ── F1: OAuth2 token endpoint failure surfaces as HTTPStatusError ─────────────


def test_token_endpoint_non_200_raises_httpstatuserror():
    """Non-2xx from the IDP (revoked creds, 401, 500…) must raise — the router
    catches HTTPStatusError to map it to 502 ``HMVS auth failed`` plus an audit
    row, instead of letting it surface as an opaque 500."""
    state = {
        "token_calls": 0,
        "token_status": 401,
        "verify": (200, {}),
        "patch": (200, {}),
    }
    _install(state)

    with pytest.raises(httpx.HTTPStatusError):
        asyncio.run(hmvs.verify("G", "S", "B", "260101", client_id=CID, client_secret=SECRET))

    # And the error must not echo the form body (would leak the secret).
    state2 = {
        "token_calls": 0,
        "token_status": 401,
        "verify": (200, {}),
        "patch": (200, {}),
    }
    _install(state2)
    try:
        asyncio.run(hmvs.verify("G", "S", "B", "260101", client_id=CID, client_secret=SECRET))
    except httpx.HTTPStatusError as exc:
        assert SECRET not in str(exc)
        assert "401" in str(exc)


# ── F2: 429 Retry-After is parsed, persisted, and surfaced ────────────────────


def test_retry_after_seconds_parsed_from_delay_header():
    """RFC 7231 delay-seconds form: bare integer string."""
    state = {
        "token_calls": 0,
        "verify": (200, {}),
        "patch": (429, {"operationCode": "NMVS_NC_PCK_03"}),
        "patch_headers": {"Retry-After": "42"},
    }
    _install(state)

    r = asyncio.run(
        hmvs.change_state(
            "G", "S", "B", "260101", target_state="Supplied", client_id=CID, client_secret=SECRET
        )
    )

    assert not r.ok and r.http_status == 429
    assert r.retry_after_seconds == 42


def test_retry_after_seconds_parsed_from_http_date_header():
    """RFC 7231 HTTP-date form: e.g. ``Tue, 09 Jun 2126 12:00:00 GMT``.

    Future date → positive seconds-to-back-off (clamped at zero for past dates)."""
    state = {
        "token_calls": 0,
        "verify": (200, {}),
        "patch": (429, {}),
        # Far enough in the future that the diff stays positive regardless of
        # when the test executes.
        "patch_headers": {"Retry-After": "Tue, 09 Jun 2126 12:00:00 GMT"},
    }
    _install(state)

    r = asyncio.run(
        hmvs.change_state(
            "G", "S", "B", "260101", target_state="Supplied", client_id=CID, client_secret=SECRET
        )
    )

    assert r.http_status == 429
    assert r.retry_after_seconds is not None and r.retry_after_seconds > 0


def test_retry_after_seconds_absent_or_garbage_returns_none():
    """No header → None; garbage header → None (never crash the dispense path)."""
    # No header at all.
    state = {"token_calls": 0, "verify": (200, {}), "patch": (429, {})}
    _install(state)
    r1 = asyncio.run(
        hmvs.change_state(
            "G", "S", "B", "260101", target_state="Supplied", client_id=CID, client_secret=SECRET
        )
    )
    assert r1.http_status == 429 and r1.retry_after_seconds is None

    # Garbage header value.
    state2 = {
        "token_calls": 0,
        "verify": (200, {}),
        "patch": (429, {}),
        "patch_headers": {"Retry-After": "not-a-number-or-date"},
    }
    _install(state2)
    r2 = asyncio.run(
        hmvs.change_state(
            "G", "S", "B", "260101", target_state="Supplied", client_id=CID, client_secret=SECRET
        )
    )
    assert r2.http_status == 429 and r2.retry_after_seconds is None


def test_change_state_idempotent_persists_retry_after_on_throttle(monkeypatch):
    """The 429 path persists the Retry-After hint on the hmvs_operations row so
    the FE can render "retry in N seconds" and a future replay loop honours the
    window instead of hammering through it."""

    async def _throttled_change_state(*_a, **_k):
        return hmvs.HmvsResult(ok=False, http_status=429, retry_after_seconds=17)

    monkeypatch.setattr(hmvs, "change_state", _throttled_change_state)
    session = _FakeHmvsSession()

    r = asyncio.run(
        hmvs.change_state_idempotent(
            session,
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
    )

    assert r.http_status == 429 and r.queued is True
    assert r.retry_after_seconds == 17
    # Persisted on the row for replay_pending + introspection.
    assert session._op.retry_after_seconds == 17
    assert session._op.status == "pending"
