"""FT-3/FT-4 — catalogue sync status rows, failure surfacing, coverage report.

DB-less: AsyncSessionLocal is monkeypatched with an in-memory store so the
REAL run_sync bookkeeping runs end to end (running → success/error, counters,
finished_at) without Postgres; the admin endpoints are exercised through
dependency overrides. Mock parity: the success-path test runs the real
_sync_drug_catalog loop under PHARMAPI_MOCK=true.
"""

import asyncio
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
from datetime import UTC, datetime  # noqa: E402
from types import SimpleNamespace  # noqa: E402

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import app.services.drug_catalog as drug_catalog  # noqa: E402
from app.db.models.catalog_sync_run import CatalogSyncRun  # noqa: E402
from app.db.session import get_session  # noqa: E402
from app.deps import get_current_user  # noqa: E402
from main import create_app  # noqa: E402

# ── In-memory stand-in for AsyncSessionLocal ─────────────────────────────────


class _FakeSession:
    def __init__(self, store: list):
        self._store = store

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    def add(self, obj):
        self._store.append(obj)

    async def commit(self):
        pass

    async def refresh(self, obj):
        if obj.id is None:
            obj.id = uuid.uuid4()
        if obj.started_at is None:
            obj.started_at = datetime.now(UTC)

    async def get(self, model, obj_id):
        assert model is CatalogSyncRun
        return next((r for r in self._store if r.id == obj_id), None)


@pytest.fixture()
def run_store(monkeypatch):
    store: list[CatalogSyncRun] = []
    monkeypatch.setattr(drug_catalog, "AsyncSessionLocal", lambda: _FakeSession(store))
    return store


# ── run_sync bookkeeping ─────────────────────────────────────────────────────


def test_full_sync_in_mock_mode_records_success_row(run_store):
    # Real _sync_drug_catalog under PHARMAPI_MOCK=true: masterdata returns an
    # empty page, the loop exits cleanly, and the run row records the outcome.
    asyncio.run(drug_catalog.run_sync(None, triggered_by="test-suite"))
    (run,) = run_store
    assert run.mode == "full"
    assert run.since is None
    assert run.status == "success"
    assert (run.fetched, run.upserted, run.skipped) == (0, 0, 0)
    assert run.finished_at is not None
    assert run.triggered_by == "test-suite"


def test_incremental_sync_records_counts(run_store, monkeypatch):
    async def fake_sync(db, since=None, page_size=500):
        return {"fetched": 5, "upserted": 4, "skipped": 1}

    monkeypatch.setattr(drug_catalog, "_sync_drug_catalog", fake_sync)
    asyncio.run(drug_catalog.run_sync("2026-06-01", triggered_by="cron"))
    (run,) = run_store
    assert run.mode == "incremental"
    assert run.since == "2026-06-01"
    assert run.status == "success"
    assert (run.fetched, run.upserted, run.skipped) == (5, 4, 1)


def test_failed_sync_records_error_and_never_raises(run_store, monkeypatch):
    async def exploding_sync(db, since=None, page_size=500):
        raise RuntimeError("upstream exploded")

    monkeypatch.setattr(drug_catalog, "_sync_drug_catalog", exploding_sync)
    # Must not raise — run_sync is a BackgroundTasks/cron callee.
    asyncio.run(drug_catalog.run_sync(None))
    (run,) = run_store
    assert run.status == "error"
    assert "upstream exploded" in run.error
    assert run.finished_at is not None


# ── Admin endpoints ──────────────────────────────────────────────────────────

_ADMIN = {"pharmacist_id": str(uuid.uuid4()), "email": "admin@x.gr", "role": "admin"}
_PHARMACIST = {"pharmacist_id": str(uuid.uuid4()), "email": "ph@x.gr", "role": "pharmacist"}

_STATUS_RUN = CatalogSyncRun(
    id=uuid.uuid4(),
    mode="full",
    since=None,
    status="success",
    started_at=datetime.now(UTC),
    finished_at=datetime.now(UTC),
    fetched=100,
    upserted=99,
    skipped=1,
    error=None,
    triggered_by="cron",
)

_COVERAGE_ROW = SimpleNamespace(
    total_active=20,
    with_coverage=18,
    with_price=17,
    with_participation=16,
    with_form=20,
    with_substance=20,
)


class _FakeStatusResult:
    def all(self):
        return [_STATUS_RUN]

    def one(self):
        return _COVERAGE_ROW


class _FakeStatusSession:
    async def scalars(self, stmt):
        return _FakeStatusResult()

    async def execute(self, stmt):
        return _FakeStatusResult()


async def _fake_get_session():
    yield _FakeStatusSession()


CURRENT_USER = {"user": _ADMIN}

app = create_app()
app.dependency_overrides[get_session] = _fake_get_session
app.dependency_overrides[get_current_user] = lambda: CURRENT_USER["user"]
client = TestClient(app)


def test_status_endpoint_returns_runs_and_coverage():
    CURRENT_USER["user"] = _ADMIN
    r = client.get("/admin/sync-drug-catalog/status")
    assert r.status_code == 200, r.text
    body = r.json()
    (run,) = body["runs"]
    assert run["status"] == "success"
    assert run["fetched"] == 100
    assert run["triggered_by"] == "cron"
    assert body["coverage"]["total_active"] == 20
    assert body["coverage"]["with_coverage"] == 18


def test_status_endpoint_requires_admin():
    CURRENT_USER["user"] = _PHARMACIST
    r = client.get("/admin/sync-drug-catalog/status")
    assert r.status_code == 403


def test_trigger_passes_admin_identity_to_run(monkeypatch):
    CURRENT_USER["user"] = _ADMIN
    calls = []

    async def fake_run_sync(since, triggered_by=None):
        calls.append((since, triggered_by))

    # Patch the name the router resolved at import time.
    import app.routers.admin as admin_router

    monkeypatch.setattr(admin_router, "run_sync", fake_run_sync)
    r = client.post("/admin/sync-drug-catalog", json={})
    assert r.status_code == 202, r.text
    assert calls == [(None, "admin:admin@x.gr")]
