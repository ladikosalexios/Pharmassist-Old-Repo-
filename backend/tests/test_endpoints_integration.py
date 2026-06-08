"""Integration tests (PHARMAPI_MOCK=true) for read endpoints.

Builds an isolated app via create_app() with get_current_user overridden so
auth is bypassed, then drives the real routers. Session-backed endpoints
(/documentation, /alerts/active) hit the live seeded dev DB the backend
container is wired to; /patients/{id} resolves from the in-memory mock.

These run against the running compose stack (seeded DB + PHARMAPI_MOCK=true).
pytest is not part of CI, so DB availability here is expected.
"""

import base64
import os

os.environ.setdefault("PHARMAPI_MOCK", "true")
os.environ.setdefault("COOKIE_SECURE", "false")
os.environ.setdefault("CREDENTIAL_ENCRYPTION_KEY", base64.b64encode(b"\x01" * 32).decode())
os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("PHARMAPI_USERNAME", "u")
os.environ.setdefault("PHARMAPI_PASSWORD", "p")
os.environ.setdefault("PHARMAPI_API_KEY", "k")
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+asyncpg://pharmassist:pharmassist_dev@localhost:5432/pharmassist",
)

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.deps import get_current_user  # noqa: E402
from main import create_app  # noqa: E402

# Matches a seeded pharmacy so find_pharmacy_by_name resolves for /alerts.
SEEDED_PHARMACY = "ΦΑΡΜΑΚΕΙΟ Fedra"
# A seeded mock patient AMKA (Maria Stavrou) for the /patients lookup.
MOCK_PATIENT_AMKA = "15031962456"


def _fake_current() -> dict:
    return {
        "pharmacist_id": "00000000-0000-0000-0000-000000000000",
        "pharmacy_id": "00000000-0000-0000-0000-000000000000",
        "pharmacy": SEEDED_PHARMACY,
        "email": "test@example.com",
        "name": "Test Pharmacist",
        "eof_licence_no": "EOF-00000",
        "role": "pharmacist",
    }


# Fresh app instance so we don't inherit the fake-session override that
# tests/test_auth_db.py installs on the shared `main.app` singleton.
app = create_app()
app.dependency_overrides[get_current_user] = _fake_current


@pytest.fixture(scope="module")
def client():
    # Context-managed so a single anyio portal / event loop serves every
    # request in the module — the async DB engine's pool binds connections to
    # one loop, avoiding the "Event loop is closed" teardown you get when each
    # bare TestClient call spins (and discards) its own loop.
    with TestClient(app) as c:
        yield c


def test_documentation_returns_items_total_stats(client):
    r = client.get("/documentation")
    assert r.status_code == 200, r.text
    body = r.json()
    assert isinstance(body["items"], list)
    assert isinstance(body["total"], int)
    assert isinstance(body["stats"], dict)


def test_alerts_active_returns_list(client):
    r = client.get("/alerts/active")
    assert r.status_code == 200, r.text
    assert isinstance(r.json(), list)


def test_get_patient_returns_profile(client):
    r = client.get(f"/patients/{MOCK_PATIENT_AMKA}")
    assert r.status_code == 200, r.text
    body = r.json()
    assert isinstance(body, dict)
    assert body.get("amka") == MOCK_PATIENT_AMKA


@pytest.mark.skip(
    reason="GET /pharmapi/errors ships with T8 (PR #73); not on main yet — "
    "add this assertion when that branch merges."
)
def test_pharmapi_errors_returns_list(client):
    r = client.get("/pharmapi/errors")
    assert r.status_code == 200, r.text
    assert isinstance(r.json(), list)


# ── POST /side-effects (ADR create) ───────────────────────────────────────────


def test_create_side_effect_mock_appears_in_get(client):
    """Mock mode: a created report is appended to the in-memory list GET serves."""
    payload = {
        "patientName": "Test Patient Mock",
        "drugName": "Ibuprofen 400 mg",
        "severity": "MODERATE",
        "symptom": "Stomach pain and nausea after dosing.",
        "onset": "2 hours after first dose",
        "causality": "Possible",
    }
    r = client.post("/side-effects", json=payload)
    assert r.status_code == 201, r.text
    created = r.json()
    assert created["status"] == "PENDING_REVIEW"
    assert created["patientName"] == "Test Patient Mock"
    assert created["causality"] == "Possible"
    assert created["reportedAt"]  # now (UTC), non-empty
    new_id = created["id"]

    listing = client.get("/side-effects")
    assert listing.status_code == 200, listing.text
    ids = [item["id"] for item in listing.json()["items"]]
    assert new_id in ids


def test_create_side_effect_live_persists(client):
    """Live mode (PHARMAPI_MOCK=false): the report is written to adr_reports.

    Reuses the module ``client`` (single event loop — the module DB engine's
    pool binds connections to it; a second TestClient context would fail with
    "attached to a different loop"). Needs a seeded pharmacist + pharmacy for
    the FK columns; skips if the dev DB has neither.
    """
    import asyncio

    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    from app.deps import get_current_user

    async def _ids() -> tuple[str, str] | None:
        # Throwaway engine fully created + disposed inside this loop, so it
        # never touches the module engine the TestClient drives.
        eng = create_async_engine(os.environ["DATABASE_URL"])
        try:
            async with eng.connect() as conn:
                pid = await conn.scalar(text("select id from pharmacists limit 1"))
                yid = await conn.scalar(text("select id from pharmacies limit 1"))
        finally:
            await eng.dispose()
        if pid is None or yid is None:
            return None
        return str(pid), str(yid)

    ids = asyncio.run(_ids())
    if ids is None:
        pytest.skip("No seeded pharmacist/pharmacy — run `python -m scripts.seed` first.")
    pharmacist_id, pharmacy_id = ids

    def _real_current() -> dict:
        return {**_fake_current(), "pharmacist_id": pharmacist_id, "pharmacy_id": pharmacy_id}

    app.dependency_overrides[get_current_user] = _real_current
    os.environ["PHARMAPI_MOCK"] = "false"
    try:
        r = client.post(
            "/side-effects",
            json={
                "patientId": "99999999999",
                "patientName": "Test Patient Live",
                "drugName": "Naproxen 500 mg",
                "severity": "SEVERE",
                "symptom": "Severe epigastric pain, suspected GI bleed.",
                "onset": "6 hours after dose",
                "causality": "Probable",
            },
        )
        assert r.status_code == 201, r.text
        created = r.json()
        assert created["status"] == "PENDING_REVIEW"
        new_id = created["id"]

        listing = client.get("/side-effects")
        assert listing.status_code == 200, listing.text
        match = [i for i in listing.json()["items"] if i["id"] == new_id]
        assert match, "created report not found in live GET"
        assert match[0]["causality"] == "Probable"
    finally:
        os.environ["PHARMAPI_MOCK"] = "true"
        app.dependency_overrides[get_current_user] = _fake_current
