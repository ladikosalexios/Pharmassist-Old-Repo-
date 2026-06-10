"""FT-1 — per-API-key rate limiting on the /v1 surface.

Unit level: the spec parser and the fixed-window roll. Endpoint level: the
REAL get_api_context runs (fake DB session, test_v1_auth pattern) with the
limit tightened via a scoped monkeypatch of deps' get_settings — no env or
lru_cache mutation, so no leakage into other test modules. Asserts the 429
envelope + Retry-After, per-key isolation, and that the B2C login limiter
wiring is untouched (pytest passthrough as before).
"""

import base64
import os

os.environ.setdefault("ENV", "test")
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

import uuid  # noqa: E402

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import app.routers.v1.deps as v1_deps  # noqa: E402
from app.config import _validated_v1_rate_limit, get_settings  # noqa: E402
from app.crypto import encrypt_credential  # noqa: E402
from app.db.models.api_key import ApiKey  # noqa: E402
from app.db.models.customer import Customer  # noqa: E402
from app.db.models.location import Location  # noqa: E402
from app.db.session import get_session  # noqa: E402
from app.services.api_keys import generate_api_key, hash_api_key  # noqa: E402
from app.utils.ratelimit import (  # noqa: E402
    FixedWindowLimiter,
    parse_rate_limit,
    v1_api_key_limiter,
)
from main import create_app  # noqa: E402

# ── Unit: spec parser ────────────────────────────────────────────────────────


def test_parse_rate_limit_specs():
    assert parse_rate_limit("120/minute") == (120, 60.0)
    assert parse_rate_limit("3/second") == (3, 1.0)
    assert parse_rate_limit("1000/hour") == (1000, 3600.0)


@pytest.mark.parametrize("bad", ["120", "abc/minute", "0/minute", "-5/minute", "10/fortnight"])
def test_parse_rate_limit_rejects_malformed(bad):
    with pytest.raises(ValueError):
        parse_rate_limit(bad)


def test_boot_validation_raises_runtime_error():
    with pytest.raises(RuntimeError, match="V1_RATE_LIMIT"):
        _validated_v1_rate_limit("10/fortnight")


# ── Unit: fixed window ───────────────────────────────────────────────────────


def test_window_counts_and_rolls(monkeypatch):
    clock = {"t": 1000.0}
    monkeypatch.setattr("app.utils.ratelimit.time.monotonic", lambda: clock["t"])
    limiter = FixedWindowLimiter()

    assert limiter.hit("k", 2, 60.0) is None
    assert limiter.hit("k", 2, 60.0) is None
    retry = limiter.hit("k", 2, 60.0)
    assert retry is not None and 0 < retry <= 60.0
    # Other keys are independent even while "k" is throttled.
    assert limiter.hit("other", 2, 60.0) is None
    # Window rolls → counter resets.
    clock["t"] += 61.0
    assert limiter.hit("k", 2, 60.0) is None


# ── Endpoint: real get_api_context with a tight limit ────────────────────────

RAW_KEY_A = generate_api_key("test")
RAW_KEY_B = generate_api_key("test")


def _tenant(name: str, raw_key: str) -> ApiKey:
    customer = Customer(id=uuid.uuid4(), name=f"{name} SA", active=True)
    location = Location(
        id=uuid.uuid4(),
        customer_id=customer.id,
        name=f"{name} Store",
        pharmapi_unit_id=70466,
        pharmapi_username=encrypt_credential(f"{name}-user"),
        pharmapi_password=encrypt_credential(f"{name}-pass"),
        is_eopyy=True,
        active=True,
    )
    key = ApiKey(
        id=uuid.uuid4(),
        location_id=location.id,
        key_hash=hash_api_key(raw_key),
        label="test",
        active=True,
        last_used_at=None,
    )
    location.customer = customer
    key.location = location
    return key


_ROWS_BY_HASH = {
    hash_api_key(RAW_KEY_A): _tenant("Alpha", RAW_KEY_A),
    hash_api_key(RAW_KEY_B): _tenant("Beta", RAW_KEY_B),
}


class _FakeScalarResult:
    def __init__(self, row):
        self._row = row

    def one_or_none(self):
        return self._row


class _FakeSession:
    async def scalars(self, stmt):
        params = stmt.compile().params
        key_hash = next((v for k, v in params.items() if k.startswith("key_hash")), None)
        return _FakeScalarResult(_ROWS_BY_HASH.get(key_hash))

    async def commit(self):
        pass


async def _fake_get_session():
    yield _FakeSession()


app = create_app()
app.dependency_overrides[get_session] = _fake_get_session
client = TestClient(app)


@pytest.fixture(autouse=True)
def _tight_limit(monkeypatch):
    """3/minute for the endpoint tests, scoped per test: deps reads settings
    per request, so patching the name it imported is enough — no env mutation,
    no get_settings.cache_clear() side effects on other modules."""
    tight = get_settings().model_copy(update={"v1_rate_limit": "3/minute"})
    monkeypatch.setattr(v1_deps, "get_settings", lambda: tight)
    v1_api_key_limiter.reset()
    yield
    v1_api_key_limiter.reset()


def test_429_envelope_after_limit_with_retry_after():
    for _ in range(3):
        assert client.get("/v1/status", headers={"X-API-Key": RAW_KEY_A}).status_code == 200
    r = client.get("/v1/status", headers={"X-API-Key": RAW_KEY_A})
    assert r.status_code == 429, r.text
    body = r.json()
    assert set(body) == {"error"}
    assert body["error"]["code"] == "rate_limited"
    assert body["error"]["request_id"] == r.headers["x-request-id"]
    assert "3/minute" in body["error"]["message"]
    retry_after = int(r.headers["retry-after"])
    assert 1 <= retry_after <= 60


def test_keys_are_isolated_one_tenants_burst_never_throttles_another():
    for _ in range(4):
        client.get("/v1/status", headers={"X-API-Key": RAW_KEY_A})
    # Alpha is now throttled; Beta must be untouched.
    assert client.get("/v1/status", headers={"X-API-Key": RAW_KEY_A}).status_code == 429
    assert client.get("/v1/status", headers={"X-API-Key": RAW_KEY_B}).status_code == 200


def test_unauthenticated_requests_never_touch_counters():
    for _ in range(10):
        assert client.get("/v1/status", headers={"X-API-Key": "pa_test_bogus"}).status_code == 401
    # The spray above must not have consumed Alpha's budget.
    assert client.get("/v1/status", headers={"X-API-Key": RAW_KEY_A}).status_code == 200


def test_b2c_login_limiter_unchanged_under_pytest():
    # FT-1 must not disturb the existing slowapi wiring: under pytest the
    # login decorator stays a passthrough exactly as before.
    from app.observability import auth_login_rate_limit

    def marker():  # pragma: no cover - identity check only
        pass

    assert auth_login_rate_limit()(marker) is marker
