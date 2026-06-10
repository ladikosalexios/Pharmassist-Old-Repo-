"""BC-3 auth tests — X-API-Key resolution + the indistinguishable-401 contract.

DB-less: a fake session resolves the key-hash lookup against in-memory ORM
rows (relationships hand-wired), so the REAL get_api_context dependency runs
end to end — hashing, active checks, credential decryption — without
Postgres. Endpoint tests drive an isolated create_app() instance (never the
shared main.app singleton, which test_auth_db mutates).
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
from app.services.api_keys import generate_api_key, hash_api_key  # noqa: E402
from main import create_app  # noqa: E402

# ── In-memory tenant fixtures ────────────────────────────────────────────────

RAW_KEY_OK = generate_api_key("test")
RAW_KEY_REVOKED = generate_api_key("test")
RAW_KEY_LOC_INACTIVE = generate_api_key("test")
RAW_KEY_CUST_INACTIVE = generate_api_key("test")


def _tenant(name: str, *, key_active=True, loc_active=True, cust_active=True, raw_key: str = ""):
    customer = Customer(id=uuid.uuid4(), name=f"{name} SA", active=cust_active)
    location = Location(
        id=uuid.uuid4(),
        customer_id=customer.id,
        name=f"{name} Store",
        pharmapi_unit_id=70466,
        pharmapi_username=encrypt_credential(f"{name}-user"),
        pharmapi_password=encrypt_credential(f"{name}-pass"),
        is_eopyy=True,
        active=loc_active,
    )
    key = ApiKey(
        id=uuid.uuid4(),
        location_id=location.id,
        key_hash=hash_api_key(raw_key),
        label="test",
        active=key_active,
        last_used_at=None,
    )
    # Hand-wire the relationships resolve_api_key traverses via joinedload.
    location.customer = customer
    key.location = location
    return key


_ROWS_BY_HASH = {
    hash_api_key(RAW_KEY_OK): _tenant("Alpha", raw_key=RAW_KEY_OK),
    hash_api_key(RAW_KEY_REVOKED): _tenant("Revoked", key_active=False, raw_key=RAW_KEY_REVOKED),
    hash_api_key(RAW_KEY_LOC_INACTIVE): _tenant(
        "LocOff", loc_active=False, raw_key=RAW_KEY_LOC_INACTIVE
    ),
    hash_api_key(RAW_KEY_CUST_INACTIVE): _tenant(
        "CustOff", cust_active=False, raw_key=RAW_KEY_CUST_INACTIVE
    ),
}


def _bind_value(stmt):
    """Extract the literal bound to the first WHERE criterion (key_hash == ?)."""
    for crit in stmt._where_criteria:
        return crit.right.value
    return None


class _FakeScalarResult:
    def __init__(self, row):
        self._row = row

    def one_or_none(self):
        return self._row


class _FakeSession:
    async def scalars(self, stmt):
        return _FakeScalarResult(_ROWS_BY_HASH.get(_bind_value(stmt)))

    async def commit(self):
        pass


async def _fake_get_session():
    yield _FakeSession()


app = create_app()
app.dependency_overrides[get_session] = _fake_get_session
client = TestClient(app)


def _assert_uniform_401(response):
    assert response.status_code == 401, response.text
    body = response.json()
    assert set(body) == {"error"}
    assert set(body["error"]) == {"code", "message", "request_id"}
    assert body["error"]["code"] == "unauthorized"
    assert body["error"]["message"] == "Invalid or missing API key"
    assert body["error"]["request_id"]
    assert response.headers["x-request-id"] == body["error"]["request_id"]


# ── Key material unit tests (D-4) ────────────────────────────────────────────


def test_generated_keys_are_prefixed_and_unique():
    assert RAW_KEY_OK.startswith("pa_test_")
    assert RAW_KEY_OK != RAW_KEY_REVOKED
    assert len(RAW_KEY_OK) > 40  # 32 bytes of entropy, urlsafe-encoded


def test_hash_is_sha256_hex_and_deterministic():
    assert hash_api_key(RAW_KEY_OK) == hash_api_key(RAW_KEY_OK)
    assert len(hash_api_key(RAW_KEY_OK)) == 64
    int(hash_api_key(RAW_KEY_OK), 16)  # valid hex


# ── The indistinguishable-401 contract ───────────────────────────────────────


def test_missing_key_is_401():
    _assert_uniform_401(client.get("/v1/status"))


def test_unknown_key_is_401():
    _assert_uniform_401(client.get("/v1/status", headers={"X-API-Key": "pa_test_nope"}))


def test_revoked_key_is_401():
    _assert_uniform_401(client.get("/v1/status", headers={"X-API-Key": RAW_KEY_REVOKED}))


def test_inactive_location_is_401():
    _assert_uniform_401(client.get("/v1/status", headers={"X-API-Key": RAW_KEY_LOC_INACTIVE}))


def test_inactive_customer_is_401():
    _assert_uniform_401(client.get("/v1/status", headers={"X-API-Key": RAW_KEY_CUST_INACTIVE}))


def test_all_failure_modes_share_one_body():
    bodies = set()
    for headers in ({}, {"X-API-Key": "bogus"}, {"X-API-Key": RAW_KEY_REVOKED}):
        body = client.get("/v1/status", headers=headers).json()
        body["error"].pop("request_id")
        bodies.add(str(body))
    assert len(bodies) == 1  # no oracle: unknown == revoked == missing


# ── Valid key resolves the full context ──────────────────────────────────────


def test_valid_key_resolves_tenant_context():
    r = client.get("/v1/status", headers={"X-API-Key": RAW_KEY_OK})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["customer"]["name"] == "Alpha SA"
    assert body["location"]["name"] == "Alpha Store"
    assert body["location"]["isEopyy"] is True
    assert body["mockMode"] is True
    assert r.headers["x-request-id"]
