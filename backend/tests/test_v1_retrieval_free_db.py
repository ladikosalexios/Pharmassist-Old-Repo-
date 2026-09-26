"""Retrieval-free /v1 end to end on real Postgres (TIER0-RETRIEVAL-FREE.md T0-1…T0-4).

The acceptance run for a location provisioned WITHOUT ΗΔΥΚΑ credentials, with
no dependency overrides: the migrated schema (nullable unit id, credential
check constraint, clinical_only tier), the real auth path, the seeded drug
catalogue + safety rules, and the real safety engine. Two tenants, both with
no credentials: a `core` customer (an external integrator with no ΗΔΥΚΑ
account — the Second Opinion shape) and a `clinical_only` customer.

Requires the compose Postgres migrated to head and seeded (safety rules + drug
catalogue), same as test_v1_tenant_isolation.py. NOT part of the CI pytest job.
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

AMKA = "77777777778"
WARFARIN = "3661001"  # seeded: B01AA03
KEY_CORE = generate_api_key("test")
KEY_T0 = generate_api_key("test")


def _run_sql(statements: list[tuple[str, dict]]):
    """Throwaway engine in its own loop (see test_v1_tenant_isolation.py)."""

    async def _go():
        eng = create_async_engine(os.environ["DATABASE_URL"])
        try:
            async with eng.begin() as conn:
                for sql, params in statements:
                    await conn.execute(text(sql), params)
        finally:
            await eng.dispose()

    asyncio.run(_go())


def _cleanup_sql():
    return [
        (
            "DELETE FROM b2b_patient_conditions WHERE location_id IN "
            "(SELECT id FROM locations WHERE name LIKE 'PYTEST-T0-%')",
            {},
        ),
        (
            "DELETE FROM api_keys WHERE location_id IN "
            "(SELECT id FROM locations WHERE name LIKE 'PYTEST-T0-%')",
            {},
        ),
        ("DELETE FROM locations WHERE name LIKE 'PYTEST-T0-%'", {}),
        ("DELETE FROM customers WHERE name LIKE 'PYTEST-T0-%'", {}),
    ]


@pytest.fixture(scope="module", autouse=True)
def tenants():
    _run_sql(_cleanup_sql())  # in case a prior run died mid-way
    statements: list[tuple[str, dict]] = []
    for label, tier, raw_key in (("CORE", "core", KEY_CORE), ("T0", "clinical_only", KEY_T0)):
        statements += [
            (
                "INSERT INTO customers (name, active, tier) VALUES (:n, true, :t)",
                {"n": f"PYTEST-T0-{label} SA", "t": tier},
            ),
            (
                # No pharmapi_unit_id / username / password at all (T0-4).
                """
                INSERT INTO locations (customer_id, name, is_eopyy, active)
                SELECT id, :loc, false, true FROM customers WHERE name = :cust
                """,
                {"loc": f"PYTEST-T0-{label} Store", "cust": f"PYTEST-T0-{label} SA"},
            ),
            (
                """
                INSERT INTO api_keys (location_id, key_hash, label, active)
                SELECT id, :h, 'pytest', true FROM locations WHERE name = :loc
                """,
                {"h": hash_api_key(raw_key), "loc": f"PYTEST-T0-{label} Store"},
            ),
        ]
    _run_sql(statements)
    yield
    _run_sql(_cleanup_sql())


app = create_app()


@pytest.fixture(scope="module")
def client():
    # Discard pool connections bound to a previous module's loop without
    # closing them (same pattern as test_v1_tenant_isolation.py).
    from app.db.session import engine

    asyncio.run(engine.dispose(close=False))
    with TestClient(app) as c:
        yield c


def _h(key: str) -> dict:
    return {"X-API-Key": key}


# ── T0-1: resolves, reaches the upstream-free routes ─────────────────────────


def test_status_resolves_without_credentials(client):
    r = client.get("/v1/status", headers=_h(KEY_CORE))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["customer"]["tier"] == "core"
    assert body["location"]["retrievalAvailable"] is False
    assert body["pharmapiConnected"] is False


def test_safety_check_with_recorded_condition_fires_without_credentials(client):
    created = client.post(
        f"/v1/patients/{AMKA}/conditions",
        headers=_h(KEY_CORE),
        json={"conditionCode": "pregnancy", "name": "Pregnancy (20w)"},
    )
    assert created.status_code == 201, created.text
    body = {"patient": {"amka": AMKA}, "medications": [{"barcode": WARFARIN}]}
    r = client.post("/v1/safety/check", headers=_h(KEY_CORE), json=body)
    assert r.status_code == 200, r.text
    result = r.json()
    assert result["conditionsConsidered"] == 1
    assert result["results"][0]["atcCode"] == "B01AA03"
    assert any("WARFARIN_PREGNANCY" in c["id"] for c in result["results"][0]["checks"]), result


def test_drug_search_and_alternatives_without_credentials(client):
    r = client.get("/v1/drugs", headers=_h(KEY_CORE), params={"barcode": WARFARIN})
    assert r.status_code == 200, r.text
    assert [d["barcode"] for d in r.json()["items"]] == [WARFARIN]
    r = client.get(f"/v1/drugs/{WARFARIN}/alternatives", headers=_h(KEY_CORE))
    assert r.status_code == 200, r.text
    assert r.json()["sourceAtc"] == "B01AA03"


# ── T0-2: retrieval routes are a clean 409, never a 500 ──────────────────────


@pytest.mark.parametrize(
    "url",
    [
        f"/v1/patients/{AMKA}",
        f"/v1/patients/{AMKA}/insurances",
        f"/v1/patients/{AMKA}/intolerances?patientConsent=true",
        f"/v1/patients/{AMKA}/medicine-history?patientConsent=true",
        "/v1/prescriptions",
        "/v1/prescriptions/1262602210000100",
    ],
)
def test_retrieval_routes_answer_409_retrieval_unavailable(client, url):
    r = client.get(url, headers=_h(KEY_CORE))
    assert r.status_code == 409, r.text
    assert r.json()["error"]["code"] == "retrieval_unavailable"


# ── T0-3: the clinical_only tenant ───────────────────────────────────────────


def test_clinical_only_tenant_gets_safety_and_catalogue_only(client):
    status = client.get("/v1/status", headers=_h(KEY_T0))
    assert status.status_code == 200, status.text
    assert status.json()["customer"]["tier"] == "clinical_only"
    body = {"medications": [{"barcode": WARFARIN}, {"atc": "B01AC06"}]}
    assert client.post("/v1/safety/check", headers=_h(KEY_T0), json=body).status_code == 200
    assert client.get("/v1/drugs?q=warf", headers=_h(KEY_T0)).status_code == 200
    for url in (f"/v1/drugs/{WARFARIN}/alternatives", "/v1/adr-reports"):
        r = client.get(url, headers=_h(KEY_T0))
        assert r.status_code == 403, (url, r.text)
        assert r.json()["error"]["code"] == "tier_required"
    r = client.get(f"/v1/patients/{AMKA}", headers=_h(KEY_T0))
    assert r.status_code == 409, r.text
    assert r.json()["error"]["code"] == "retrieval_unavailable"


# ── T0-3 / T0-4: schema guards (migration e5b1c9d47a20) ──────────────────────


def _insert_location(unit, username, password):
    _run_sql(
        [
            (
                """
                INSERT INTO locations
                    (customer_id, name, pharmapi_unit_id, pharmapi_username,
                     pharmapi_password, is_eopyy, active)
                SELECT id, 'PYTEST-T0-BAD Store', :unit, :u, :p, false, true
                FROM customers WHERE name = 'PYTEST-T0-CORE SA'
                """,
                {"unit": unit, "u": username, "p": password},
            )
        ]
    )


@pytest.mark.parametrize(
    ("unit", "with_user", "with_pass"),
    [
        (70001, True, False),  # username without password
        (70001, False, True),  # password without username
        (None, True, True),  # credentials without a unit id
    ],
)
def test_half_provisioned_location_rejected_by_check_constraint(unit, with_user, with_pass):
    user = encrypt_credential("half-user") if with_user else None
    password = encrypt_credential("half-pass") if with_pass else None
    with pytest.raises(Exception) as exc:
        _insert_location(unit, user, password)
    assert "ck_locations_pharmapi_credentials" in str(exc.value)


def test_fully_credentialed_location_still_accepted():
    _insert_location(70001, encrypt_credential("full-user"), encrypt_credential("full-pass"))
    _run_sql([("DELETE FROM locations WHERE name = 'PYTEST-T0-BAD Store'", {})])


def test_clinical_only_admitted_but_unknown_tier_still_rejected():
    # The fixture already inserted a clinical_only customer; an unknown tier is
    # still refused by the widened ck_customers_tier.
    with pytest.raises(Exception) as exc:
        _run_sql(
            [
                (
                    "INSERT INTO customers (name, active, tier) "
                    "VALUES ('PYTEST-T0-BADTIER SA', true, 'bronze')",
                    {},
                )
            ]
        )
    assert "ck_customers_tier" in str(exc.value)
