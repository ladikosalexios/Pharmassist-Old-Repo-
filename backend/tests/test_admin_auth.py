"""Smoke tests for staff (admin-portal) auth — /admin/login, /admin/me, /admin/logout.

Mirrors tests/test_auth_db.py: a fake AsyncSession is injected via
dependency_overrides. Env vars are written before importing the app because
get_settings is @lru_cache-d.
"""

import base64
import os
import uuid

# Must be set before any `from app.*` / `from main import` line below.
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
import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy.sql.elements import BindParameter  # noqa: E402

from app.db.models.invitation import Invitation  # noqa: E402
from app.db.models.pharmacy import Pharmacy  # noqa: E402
from app.db.models.staff_user import StaffUser  # noqa: E402
from app.db.session import get_session  # noqa: E402
from app.services.security import create_jwt  # noqa: E402
from main import app  # noqa: E402

STAFF_ID = uuid.uuid4()
EMAIL = "staff@pharmassist.gr"
PASSWORD = "staffpass1"


class _FakeStaff:
    id = STAFF_ID
    email = EMAIL
    full_name = "Test Staff"
    role = "admin"
    password_hash = bcrypt.hashpw(PASSWORD.encode(), bcrypt.gensalt(rounds=4)).decode()
    active = True
    last_login_at = None


_STAFF = _FakeStaff()


def _bind_value_for(stmt, column_key: str):
    """Pull the bind value for `<entity>.<column_key> == ?` out of a WHERE clause."""
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
    def __init__(self, value):
        self._value = value

    def one_or_none(self):
        return self._value


class _FakeAsyncSession:
    """Resolves StaffUser by email (login) or id (get_by_id); writes are captured
    in-memory so the onboarding endpoint can run. Returns None for an
    unrecognised email/id so wrong-account tests are real."""

    def __init__(self):
        self._pending: list = []

    def _resolve(self, stmt):
        if stmt.column_descriptions[0]["entity"] is not StaffUser:
            return None
        if _bind_value_for(stmt, "email") not in (None, EMAIL):
            return None
        queried_id = _bind_value_for(stmt, "id")
        if queried_id is not None and str(queried_id) != str(STAFF_ID):
            return None
        return _STAFF

    async def scalar(self, stmt):
        return self._resolve(stmt)

    async def scalars(self, stmt):
        return _FakeScalarResult(self._resolve(stmt))

    def add(self, obj):
        self._pending.append(obj)

    async def flush(self):
        # Mimic server-side id assignment so the endpoint can reference new rows.
        for obj in self._pending:
            if isinstance(obj, (Pharmacy, Invitation)) and getattr(obj, "id", None) is None:
                obj.id = uuid.uuid4()

    async def refresh(self, obj):
        pass

    async def commit(self):
        pass


async def _fake_get_session():
    yield _FakeAsyncSession()


@pytest.fixture(autouse=True)
def _override_session():
    """Point get_session at the staff fake for each test, then restore it — so
    this file's override never collides with tests/test_auth_db.py's."""
    previous = app.dependency_overrides.get(get_session)
    app.dependency_overrides[get_session] = _fake_get_session
    yield
    if previous is None:
        app.dependency_overrides.pop(get_session, None)
    else:
        app.dependency_overrides[get_session] = previous


def test_staff_login_sets_cookie():
    client = TestClient(app)
    r = client.post("/admin/login", json={"email": EMAIL, "password": PASSWORD})
    assert r.status_code == 200, r.text
    assert "pharmassist_admin_session" in r.cookies
    body = r.json()
    # JWT must never leak into the response body.
    assert "access_token" not in body and "token" not in body
    assert body["staff_id"] == str(STAFF_ID)
    assert body["role"] == "admin"


def test_staff_login_wrong_password_returns_401():
    client = TestClient(app)
    r = client.post("/admin/login", json={"email": EMAIL, "password": "not-the-password"})
    assert r.status_code == 401
    assert r.json() == {"detail": "Invalid credentials"}
    assert "pharmassist_admin_session" not in r.cookies


def test_staff_login_unknown_email_returns_same_401():
    client = TestClient(app)
    r = client.post("/admin/login", json={"email": "nobody@pharmassist.gr", "password": PASSWORD})
    assert r.status_code == 401
    assert r.json() == {"detail": "Invalid credentials"}


def test_admin_me_requires_cookie():
    client = TestClient(app)
    assert client.get("/admin/me").status_code == 401


def test_admin_me_with_cookie_returns_staff():
    client = TestClient(app)
    login = client.post("/admin/login", json={"email": EMAIL, "password": PASSWORD})
    assert login.status_code == 200
    r = client.get("/admin/me")
    assert r.status_code == 200
    assert r.json()["email"] == EMAIL


def test_pharmacist_token_rejected_on_admin():
    """A pharmacist-shaped JWT (no typ=staff) must not satisfy get_current_staff."""
    token = create_jwt(
        {"sub": str(uuid.uuid4()), "pharmacy_id": str(uuid.uuid4()), "email": "p@example.gr"}
    )
    client = TestClient(app)
    client.cookies.set("pharmassist_admin_session", token)
    assert client.get("/admin/me").status_code == 401


def test_staff_logout_clears_cookie():
    client = TestClient(app)
    client.post("/admin/login", json={"email": EMAIL, "password": PASSWORD})
    assert "pharmassist_admin_session" in client.cookies
    assert client.post("/admin/logout").status_code == 200
    assert "pharmassist_admin_session" not in client.cookies


def test_onboard_requires_staff_cookie():
    """POST /admin/invitations is staff-gated — no cookie, no onboarding."""
    client = TestClient(app)
    r = client.post(
        "/admin/invitations",
        json={
            "pharmacist_email": "x@pharmassist.gr",
            "pharmacy": {"name": "X", "pharmapi_unit_id": 1},
        },
    )
    assert r.status_code == 401


def test_onboard_creates_pharmacy_and_invitation():
    """POST /admin/invitations onboards a new pharmacy + its first pharmacist."""
    client = TestClient(app)
    client.post("/admin/login", json={"email": EMAIL, "password": PASSWORD})
    r = client.post(
        "/admin/invitations",
        json={
            "pharmacist_email": "new-pharmacist@pharmassist.gr",
            "pharmacy": {"name": "Onboarded Pharmacy", "pharmapi_unit_id": 4242},
        },
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["email"] == "new-pharmacist@pharmassist.gr"
    assert body["invite_url"].startswith("/accept-invite?token=")
