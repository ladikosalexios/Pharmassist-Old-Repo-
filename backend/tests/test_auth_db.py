"""Smoke tests for cookie-based auth (ADR-003).

Exercises POST /auth/login, GET /auth/me, POST /auth/logout end-to-end with
a fake AsyncSession injected via ``dependency_overrides``. PHARMAPI_MOCK=true
skips the live ΗΔΥΚΑ call; bcrypt still runs against a real hash.

Env vars are written before importing the app because ``get_settings`` is
``@lru_cache``-d and ``services/security.py`` / ``services/pharmapi.py`` /
``db/session.py`` all read settings at module import time.
"""

import base64
import os
import uuid
from datetime import UTC, datetime

# Must be set before any `from app.*` / `from main import` line below.
os.environ["ENV"] = "test"
os.environ["PHARMAPI_MOCK"] = "true"
os.environ["COOKIE_SECURE"] = "false"
os.environ["CREDENTIAL_ENCRYPTION_KEY"] = base64.b64encode(b"\x01" * 32).decode()
os.environ.setdefault("SECRET_KEY", "test-secret-key-do-not-use-in-prod")
os.environ.setdefault("PHARMAPI_USERNAME", "test-pharmapi-user")
os.environ.setdefault("PHARMAPI_PASSWORD", "test-pharmapi-pass")
os.environ.setdefault("PHARMAPI_API_KEY", "test-pharmapi-key")
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+asyncpg://pharmassist:pharmassist_dev@localhost:5432/pharmassist_test",
)

import bcrypt  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy.sql.elements import BindParameter  # noqa: E402

from app.crypto import encrypt_credential  # noqa: E402
from app.db.models.pharmacist import Pharmacist  # noqa: E402
from app.db.models.pharmacist_pharmacy import PharmacistPharmacy  # noqa: E402
from app.db.models.pharmacy import Pharmacy  # noqa: E402
from app.db.session import get_session  # noqa: E402
from main import app  # noqa: E402

PHARMACIST_ID = uuid.uuid4()
PHARMACY_ID = uuid.uuid4()
EMAIL = "alex@example.com"
PASSWORD = "hunter2"


class _FakePharmacist:
    id = PHARMACIST_ID
    email = EMAIL
    full_name = "Alex Pharmacist"
    role = "pharmacist"
    eof_licence_no = "EOF-12345"  # deps.get_current_user reads this for /auth/me
    password_hash = bcrypt.hashpw(PASSWORD.encode(), bcrypt.gensalt(rounds=4)).decode()
    active = True
    last_login_at = None  # login handler writes to this; test_login asserts it.

    async def get_default_pharmacy_link(self, session):
        # Mirrors the real Pharmacist.get_default_pharmacy_link contract — the
        # session arg is unused here because the fake link is canned.
        return _ROWS[PharmacistPharmacy]


class _FakePharmacy:
    id = PHARMACY_ID
    name = "Test Pharmacy"


_PHARMACY = _FakePharmacy()


class _FakeLink:
    pharmacist_id = PHARMACIST_ID
    pharmacy_id = PHARMACY_ID
    pharmapi_username = encrypt_credential("mockuser")
    pharmapi_password = encrypt_credential("mockpass")
    is_default = True
    # Eager-loaded `.pharmacy` relationship that login now reads off the link
    # directly (Pharmacist.get_default_pharmacy_link uses selectinload).
    pharmacy = _PHARMACY


_ROWS = {
    Pharmacist: _FakePharmacist(),
    PharmacistPharmacy: _FakeLink(),
    Pharmacy: _PHARMACY,
}


def _bind_value_for(stmt, column_key: str):
    """Pull the bind-parameter value for `<entity>.<column_key> == ?` out of a
    select's WHERE clause. Returns None if no such equality is present.

    Needed so the fake session can answer Pharmacist-by-email lookups
    realistically — without it, unknown-email tests can't be distinguished
    from valid ones."""
    where = stmt.whereclause
    if where is None:
        return None
    clauses = list(where.clauses) if hasattr(where, "clauses") else [where]
    for c in clauses:
        left = getattr(c, "left", None)
        right = getattr(c, "right", None)
        if getattr(left, "key", None) == column_key and isinstance(right, BindParameter):
            return right.value
    return None


class _FakeScalarResult:
    """Minimal stand-in for SQLAlchemy's ``ScalarResult`` — only the methods
    ``Base.get_by_id`` reaches for."""

    def __init__(self, value):
        self._value = value

    def one_or_none(self):
        return self._value


class _FakeAsyncSession:
    """Stand-in for ``AsyncSession``. Resolves rows by entity, and for
    Pharmacist queries also matches the email in the WHERE clause so wrong-
    email tests get a real None back. ``commit`` is a no-op — the login
    handler calls it after stamping ``last_login_at``. Sufficient for the
    login + /me + logout smoke paths; not a general SQLAlchemy mock."""

    def _resolve(self, stmt):
        entity = stmt.column_descriptions[0]["entity"]
        if entity is Pharmacist:
            queried_email = _bind_value_for(stmt, "email")
            if queried_email is not None and queried_email != EMAIL:
                return None
        return _ROWS.get(entity)

    async def scalar(self, stmt):
        return self._resolve(stmt)

    async def scalars(self, stmt):
        # `Base.get_by_id` uses `session.scalars(stmt).one_or_none()`; wrap.
        return _FakeScalarResult(self._resolve(stmt))

    async def commit(self):
        pass


async def _fake_get_session():
    yield _FakeAsyncSession()


app.dependency_overrides[get_session] = _fake_get_session


def test_login_sets_cookie():
    before = datetime.now(UTC)
    client = TestClient(app)
    r = client.post("/auth/login", json={"email": EMAIL, "password": PASSWORD})
    assert r.status_code == 200, r.text
    assert "pharmassist_session" in r.cookies
    body = r.json()
    # JWT must NOT leak into the response body — ADR-003 hard rule.
    assert "access_token" not in body
    assert "token" not in body
    assert body["pharmacist_id"] == str(PHARMACIST_ID)
    assert body["pharmacy_id"] == str(PHARMACY_ID)
    # last_login_at was written within this request.
    stamped = _ROWS[Pharmacist].last_login_at
    assert stamped is not None and stamped >= before


def test_me_returns_user():
    client = TestClient(app)
    login = client.post("/auth/login", json={"email": EMAIL, "password": PASSWORD})
    assert login.status_code == 200, login.text

    r = client.get("/auth/me")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["email"] == EMAIL
    assert body["pharmacist_id"] == str(PHARMACIST_ID)
    assert body["pharmacy_id"] == str(PHARMACY_ID)


def test_unknown_email_returns_same_401():
    """Unknown email returns the same opaque 401 as a wrong password — no
    account enumeration via status code, response body, or cookie state.
    Implicitly exercises the constant-time bcrypt path (dummy hash). The
    fake session's WHERE-clause inspection makes the email mismatch real."""
    client = TestClient(app)
    r = client.post("/auth/login", json={"email": "nobody@example.com", "password": PASSWORD})
    assert r.status_code == 401, r.text
    assert r.json() == {"detail": "Invalid credentials"}
    assert "pharmassist_session" not in r.cookies


def test_wrong_password_returns_401():
    """Right email + wrong password ⇒ the same 401 body as an unknown email."""
    client = TestClient(app)
    r = client.post("/auth/login", json={"email": EMAIL, "password": "not-the-password"})
    assert r.status_code == 401, r.text
    assert r.json() == {"detail": "Invalid credentials"}
    assert "pharmassist_session" not in r.cookies


def test_logout_clears_cookie():
    client = TestClient(app)
    login = client.post("/auth/login", json={"email": EMAIL, "password": PASSWORD})
    assert login.status_code == 200, login.text
    assert "pharmassist_session" in client.cookies

    r = client.post("/auth/logout")
    assert r.status_code == 200
    # delete_cookie writes a Max-Age=0/Expires=1970 Set-Cookie; httpx evicts.
    assert "pharmassist_session" not in client.cookies
    me = client.get("/auth/me")
    assert me.status_code == 401
