"""Tenant-isolation integration tests for /v1 (live compose Postgres).

Runs the REAL auth path end to end — no dependency overrides: two tenants
are inserted into the dev DB, each with its own API key, and every assertion
is "location A's key cannot see/touch location B's data". Requires the
running compose stack with a seeded DB (safety rules + drug catalog), same
as tests/test_endpoints_integration.py. NOT part of the CI pytest job.
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
    "postgresql+asyncpg://pharmassist:pharmassist_dev@localhost:5432/pharmassist",
)

import asyncio  # noqa: E402

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import create_async_engine  # noqa: E402

from app.crypto import encrypt_credential  # noqa: E402
from app.services.api_keys import generate_api_key, hash_api_key  # noqa: E402
from main import create_app  # noqa: E402

AMKA = "77777777777"
KEY_A = generate_api_key("test")
KEY_B = generate_api_key("test")

# Shared across ordered tests in this module.
STATE: dict = {}


def _run_sql(statements: list[tuple[str, dict]]):
    """Throwaway engine in its own loop (see test_endpoints_integration.py)."""

    async def _go():
        eng = create_async_engine(os.environ["DATABASE_URL"])
        try:
            async with eng.begin() as conn:
                for sql, params in statements:
                    await conn.execute(text(sql), params)
        finally:
            await eng.dispose()

    asyncio.run(_go())


@pytest.fixture(scope="module", autouse=True)
def tenants():
    _run_sql(
        [
            (
                "INSERT INTO customers (name, active) VALUES "
                "('PYTEST-B2B-A SA', true), ('PYTEST-B2B-B SA', true)",
                {},
            ),
            (
                """
                INSERT INTO locations
                    (customer_id, name, pharmapi_unit_id, pharmapi_username,
                     pharmapi_password, is_eopyy, active)
                SELECT id, 'PYTEST-B2B-A Store', 70001, :u, :p, true, true
                FROM customers WHERE name = 'PYTEST-B2B-A SA'
                """,
                {"u": encrypt_credential("a-user"), "p": encrypt_credential("a-pass")},
            ),
            (
                """
                INSERT INTO locations
                    (customer_id, name, pharmapi_unit_id, pharmapi_username,
                     pharmapi_password, is_eopyy, active)
                SELECT id, 'PYTEST-B2B-B Store', 70002, :u, :p, true, true
                FROM customers WHERE name = 'PYTEST-B2B-B SA'
                """,
                {"u": encrypt_credential("b-user"), "p": encrypt_credential("b-pass")},
            ),
            (
                """
                INSERT INTO api_keys (location_id, key_hash, label, active)
                SELECT id, :h, 'pytest', true
                FROM locations WHERE name = 'PYTEST-B2B-A Store'
                """,
                {"h": hash_api_key(KEY_A)},
            ),
            (
                """
                INSERT INTO api_keys (location_id, key_hash, label, active)
                SELECT id, :h, 'pytest', true
                FROM locations WHERE name = 'PYTEST-B2B-B Store'
                """,
                {"h": hash_api_key(KEY_B)},
            ),
        ]
    )
    yield
    _run_sql(
        [
            (
                "DELETE FROM b2b_patient_conditions WHERE location_id IN "
                "(SELECT id FROM locations WHERE name LIKE 'PYTEST-B2B-%')",
                {},
            ),
            (
                "DELETE FROM api_keys WHERE location_id IN "
                "(SELECT id FROM locations WHERE name LIKE 'PYTEST-B2B-%')",
                {},
            ),
            ("DELETE FROM locations WHERE name LIKE 'PYTEST-B2B-%'", {}),
            ("DELETE FROM customers WHERE name LIKE 'PYTEST-B2B-%'", {}),
        ]
    )


app = create_app()


@pytest.fixture(scope="module")
def client():
    # The global async engine may hold pool connections bound to a PREVIOUS
    # module's event loop (test_endpoints_integration runs its own module-
    # scoped client). Discard the pool without closing those connections
    # (close=False — closing would need their original loop) so this module's
    # loop gets fresh ones.
    from app.db.session import engine

    asyncio.run(engine.dispose(close=False))
    with TestClient(app) as c:
        yield c


def _h(key: str) -> dict:
    return {"X-API-Key": key}


def test_each_key_resolves_its_own_location(client):
    a = client.get("/v1/status", headers=_h(KEY_A)).json()
    b = client.get("/v1/status", headers=_h(KEY_B)).json()
    assert a["location"]["name"] == "PYTEST-B2B-A Store"
    assert b["location"]["name"] == "PYTEST-B2B-B Store"


def test_a_records_condition(client):
    r = client.post(
        f"/v1/patients/{AMKA}/conditions",
        headers=_h(KEY_A),
        json={"conditionCode": "PREGNANCY", "name": "Pregnancy (12w)", "severity": "MODERATE"},
    )
    assert r.status_code == 201, r.text
    STATE["a_condition_id"] = r.json()["id"]


def test_b_cannot_see_a_condition(client):
    r = client.get(f"/v1/patients/{AMKA}/conditions", headers=_h(KEY_B))
    assert r.status_code == 200
    assert r.json() == []


def test_b_recording_same_condition_does_not_collide_or_leak(client):
    # On the B2C table this would 409 (global unique index) and leak that
    # another tenant recorded it — per-location keying makes it a clean 201.
    r = client.post(
        f"/v1/patients/{AMKA}/conditions",
        headers=_h(KEY_B),
        json={"conditionCode": "G6PD", "name": "G6PD deficiency"},
    )
    assert r.status_code == 201, r.text
    STATE["b_condition_id"] = r.json()["id"]


def test_b_cannot_touch_a_condition_by_id(client):
    r = client.patch(
        f"/v1/patients/{AMKA}/conditions/{STATE['a_condition_id']}",
        headers=_h(KEY_B),
        json={"notes": "hijack attempt"},
    )
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "not_found"
    r = client.delete(
        f"/v1/patients/{AMKA}/conditions/{STATE['a_condition_id']}", headers=_h(KEY_B)
    )
    assert r.status_code == 404


def test_safety_check_sees_only_own_location_conditions(client):
    # Warfarin (seeded barcode 3661001, B01AA03) + A's PREGNANCY → blocks at A...
    # (seeded rule code: WARFARIN_PREGNANCY_CONTRAINDICATION — match by substring)
    body = {"patient": {"amka": AMKA}, "medications": [{"barcode": "3661001"}]}
    a = client.post("/v1/safety/check", headers=_h(KEY_A), json=body).json()
    assert a["conditionsConsidered"] == 1
    assert any("WARFARIN_PREGNANCY" in c["id"] for r in a["results"] for c in r["checks"]), a
    # ...but NOT at B, whose only condition is G6PD (no warfarin+G6PD rule).
    b = client.post("/v1/safety/check", headers=_h(KEY_B), json=body).json()
    assert b["conditionsConsidered"] == 1
    assert not any("WARFARIN_PREGNANCY" in c["id"] for r in b["results"] for c in r["checks"]), b


def test_duplicate_condition_409_is_scoped_to_one_location(client):
    r = client.post(
        f"/v1/patients/{AMKA}/conditions",
        headers=_h(KEY_A),
        json={"conditionCode": "PREGNANCY", "name": "Pregnancy (12w)"},
    )
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "conflict"
