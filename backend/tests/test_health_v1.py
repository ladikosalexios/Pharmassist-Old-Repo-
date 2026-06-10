"""FT-8 (partial) — the unauthenticated /health/v1 B2B liveness probe.

DB-less: get_session is overridden with a fake that can be flipped between
"DB reachable" and "DB down", so the three signals (db reachable, last FT-4
sync age, app version) and the 200/503 split are asserted without Postgres.
The legacy /health probe must keep its exact pilot-box shape — asserted too.
"""

import base64
import os
from datetime import UTC, datetime, timedelta

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

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.db.session import get_session  # noqa: E402
from main import create_app  # noqa: E402


class _FakeSyncRun:
    def __init__(self, finished_at):
        self.finished_at = finished_at


class _FakeSession:
    """DB up: SELECT 1 succeeds, scalar() returns the configured last sync."""

    def __init__(self, last_sync=None):
        self._last_sync = last_sync

    async def execute(self, stmt):
        return None

    async def scalar(self, stmt):
        return self._last_sync


class _DeadSession:
    """DB down: every query raises, as a real connection failure would."""

    async def execute(self, stmt):
        raise RuntimeError("connection refused")

    async def scalar(self, stmt):
        raise RuntimeError("connection refused")


app = create_app()
client = TestClient(app)


def _override(session):
    async def _gen():
        yield session

    app.dependency_overrides[get_session] = _gen


@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    app.dependency_overrides.pop(get_session, None)


def test_legacy_health_shape_unchanged():
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert set(body) == {"status", "pharmapi_session_valid", "pharmapi_api_key_set", "timestamp"}


def test_health_v1_reports_three_signals_when_db_up():
    recent = datetime.now(UTC) - timedelta(hours=2)
    _override(_FakeSession(last_sync=_FakeSyncRun(recent)))
    r = client.get("/health/v1")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "ok"
    assert body["db"]["reachable"] is True
    assert body["version"]  # app version present
    assert body["lastCatalogSync"]["ageSeconds"] is not None
    assert body["lastCatalogSync"]["stale"] is False


def test_health_v1_marks_old_sync_stale_but_stays_ok():
    old = datetime.now(UTC) - timedelta(hours=72)
    _override(_FakeSession(last_sync=_FakeSyncRun(old)))
    r = client.get("/health/v1")
    assert r.status_code == 200
    assert r.json()["lastCatalogSync"]["stale"] is True  # >48h


def test_health_v1_no_sync_yet_is_stale():
    _override(_FakeSession(last_sync=None))
    body = client.get("/health/v1").json()
    assert body["lastCatalogSync"]["at"] is None
    assert body["lastCatalogSync"]["stale"] is True


def test_health_v1_returns_503_when_db_unreachable():
    _override(_DeadSession())
    r = client.get("/health/v1")
    assert r.status_code == 503
    body = r.json()
    assert body["status"] == "degraded"
    assert body["db"]["reachable"] is False
    assert body["version"]  # version still reported on a degraded probe


def test_health_v1_is_unauthenticated():
    # No X-API-Key, no session cookie — must still answer (keyless by design).
    _override(_FakeSession(last_sync=None))
    assert client.get("/health/v1").status_code == 200
