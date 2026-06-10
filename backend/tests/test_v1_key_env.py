"""FT-13 — pa_test_/pa_live_ key semantics are enforced, not cosmetic.

A key resolves only on a deployment whose mode matches its env prefix:
mock-mode stack (the sandbox) accepts pa_test_ only, live-mode accepts
pa_live_ only. Mismatches fail with the same indistinguishable 401 as any
bad key. /v1/status never calls upstream, so the live-mode cases are safe
to exercise by flipping PHARMAPI_MOCK per test (re-read per call).
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

from fastapi.testclient import TestClient  # noqa: E402

from app.crypto import encrypt_credential  # noqa: E402
from app.db.models.api_key import ApiKey  # noqa: E402
from app.db.models.customer import Customer  # noqa: E402
from app.db.models.location import Location  # noqa: E402
from app.db.session import get_session  # noqa: E402
from app.services.api_keys import (  # noqa: E402
    deployment_env_label,
    generate_api_key,
    hash_api_key,
    key_env_label,
)
from main import create_app  # noqa: E402

# ── Unit: label helpers ──────────────────────────────────────────────────────


def test_key_env_label_parses_both_prefixes():
    assert key_env_label(generate_api_key("test")) == "test"
    assert key_env_label(generate_api_key("live")) == "live"
    assert key_env_label("sk_something_else") is None
    assert key_env_label("") is None


def test_deployment_env_label_follows_mock_mode(monkeypatch):
    monkeypatch.setenv("PHARMAPI_MOCK", "true")
    assert deployment_env_label() == "test"
    monkeypatch.setenv("PHARMAPI_MOCK", "false")
    assert deployment_env_label() == "live"


# ── Endpoint: env-mismatched keys 401 indistinguishably ──────────────────────

RAW_TEST_KEY = generate_api_key("test")
RAW_LIVE_KEY = generate_api_key("live")


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
    hash_api_key(RAW_TEST_KEY): _tenant("Sandbox", RAW_TEST_KEY),
    hash_api_key(RAW_LIVE_KEY): _tenant("Prod", RAW_LIVE_KEY),
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


def _status(key: str) -> int:
    return client.get("/v1/status", headers={"X-API-Key": key}).status_code


def test_mock_stack_accepts_test_key_rejects_live_key(monkeypatch):
    monkeypatch.setenv("PHARMAPI_MOCK", "true")
    assert _status(RAW_TEST_KEY) == 200
    assert _status(RAW_LIVE_KEY) == 401  # valid row, wrong environment


def test_live_stack_accepts_live_key_rejects_test_key(monkeypatch):
    monkeypatch.setenv("PHARMAPI_MOCK", "false")  # /v1/status makes no upstream call
    assert _status(RAW_LIVE_KEY) == 200
    assert _status(RAW_TEST_KEY) == 401


def test_env_mismatch_401_is_indistinguishable_from_bad_key(monkeypatch):
    monkeypatch.setenv("PHARMAPI_MOCK", "true")
    mismatch = client.get("/v1/status", headers={"X-API-Key": RAW_LIVE_KEY}).json()
    bogus = client.get("/v1/status", headers={"X-API-Key": "pa_test_bogus"}).json()
    mismatch["error"].pop("request_id")
    bogus["error"].pop("request_id")
    assert mismatch == bogus  # no oracle for "right key, wrong environment"


def test_unknown_prefix_is_rejected(monkeypatch):
    monkeypatch.setenv("PHARMAPI_MOCK", "true")
    assert _status("sk_live_someone_elses_key_format") == 401


def test_mint_default_follows_stack_mode(monkeypatch):
    from scripts.b2b_admin import _default_env_label

    monkeypatch.setenv("PHARMAPI_MOCK", "true")
    assert _default_env_label() == "test"
    monkeypatch.setenv("PHARMAPI_MOCK", "false")
    assert _default_env_label() == "live"
