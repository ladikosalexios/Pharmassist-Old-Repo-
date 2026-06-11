"""End-to-end audit-trail test for the b2b_admin CLI (live compose Postgres).

Drives every state-changing command through one event loop against the dev DB
and asserts that each appended exactly one b2b_admin_audit row with the right
action / target / before→after — and, critically, that no row leaks a secret
(the ΗΔΥΚΑ password/username or the raw minted key). NOT part of the CI pytest
job — needs the running compose stack, same as test_v1_tenant_isolation.py.
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

import argparse  # noqa: E402
import asyncio  # noqa: E402
import json  # noqa: E402

import pytest  # noqa: E402
from sqlalchemy import select, text  # noqa: E402
from sqlalchemy.ext.asyncio import create_async_engine  # noqa: E402

from app.db.models.api_key import ApiKey  # noqa: E402
from app.db.models.b2b_admin_audit import B2bAdminAudit  # noqa: E402
from app.db.models.customer import Customer  # noqa: E402
from app.db.models.location import Location  # noqa: E402
from app.db.session import AsyncSessionLocal  # noqa: E402
from scripts.b2b_admin import (  # noqa: E402
    create_customer,
    create_location,
    mint_key,
    revoke_key,
    rotate_key,
    set_tier,
)

ACTOR = "PYTEST-AUDIT-OP"
CUST = "PYTEST-AUDIT SA"
LOC = "PYTEST-AUDIT Store"
# Distinctive secrets so a leak into any audit row is unambiguous.
SECRET_PW = "demo-secret-pw-DO-NOT-LOG"
SECRET_USER = "audit-secret-user-DO-NOT-LOG"


def _ns(**kw) -> argparse.Namespace:
    return argparse.Namespace(**kw)


def _cleanup_sql():
    return [
        ("DELETE FROM b2b_admin_audit WHERE actor = :a", {"a": ACTOR}),
        (
            "DELETE FROM api_keys WHERE location_id IN "
            "(SELECT id FROM locations WHERE name LIKE 'PYTEST-AUDIT%')",
            {},
        ),
        ("DELETE FROM locations WHERE name LIKE 'PYTEST-AUDIT%'", {}),
        ("DELETE FROM customers WHERE name LIKE 'PYTEST-AUDIT%'", {}),
    ]


def _run_sql(statements):
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
def clean():
    _run_sql(_cleanup_sql())  # in case a prior run died mid-way
    yield
    _run_sql(_cleanup_sql())


async def _drive_lifecycle():
    """Run all six commands in one loop, then return the audit rows + the ids."""
    from app.db.session import engine

    # The global pool may hold connections from another module's loop — discard
    # them WITHOUT force-closing (close=False: closing needs their original
    # loop), same pattern as test_v1_tenant_isolation's client fixture.
    await engine.dispose(close=False)

    await create_customer(_ns(actor=ACTOR, name=CUST, email="ops@audit.example", tier="clinical"))
    async with AsyncSessionLocal() as db:
        cid = (await db.scalars(select(Customer).where(Customer.name == CUST))).one().id

    await set_tier(_ns(actor=ACTOR, customer_id=cid, tier="core"))

    await create_location(
        _ns(
            actor=ACTOR,
            customer_id=cid,
            name=LOC,
            address=None,
            pharmapi_unit_id=70077,
            pharmapi_username=SECRET_USER,
            pharmapi_password=SECRET_PW,
            eopyy=True,
            verify=False,
        )
    )
    async with AsyncSessionLocal() as db:
        lid = (await db.scalars(select(Location).where(Location.name == LOC))).one().id

    await mint_key(_ns(actor=ACTOR, location_id=lid, label="audit-pos", env="test"))
    async with AsyncSessionLocal() as db:
        kid = (await db.scalars(select(ApiKey).where(ApiKey.location_id == lid))).all()[0].id

    await rotate_key(_ns(actor=ACTOR, key_id=kid, label=None))
    await revoke_key(_ns(actor=ACTOR, key_id=kid))

    async with AsyncSessionLocal() as db:
        rows = (
            await db.scalars(
                select(B2bAdminAudit).where(B2bAdminAudit.actor == ACTOR).order_by(B2bAdminAudit.id)
            )
        ).all()
        return (
            [
                {
                    "action": r.action,
                    "target_type": r.target_type,
                    "target_id": r.target_id,
                    "details": r.details,
                }
                for r in rows
            ],
            str(cid),
            str(lid),
            str(kid),
        )


@pytest.fixture(scope="module")
def lifecycle():
    result = asyncio.run(_drive_lifecycle())
    # The driver's loop is now closed; drop the connections it left in the global
    # pool so a later DB-backed module (e.g. test_endpoints_integration) gets
    # fresh ones for ITS loop instead of inheriting dead-loop connections.
    from app.db.session import engine

    asyncio.run(engine.dispose(close=False))
    return result


def test_every_mutation_appended_one_row_in_order(lifecycle):
    rows, _cid, _lid, _kid = lifecycle
    assert [r["action"] for r in rows] == [
        "CREATE_CUSTOMER",
        "SET_TIER",
        "CREATE_LOCATION",
        "MINT_KEY",
        "ROTATE_KEY",
        "REVOKE_KEY",
    ]
    assert all(r["target_id"] for r in rows)  # every row identifies its target


def test_actor_and_targets_recorded(lifecycle):
    rows, cid, lid, kid = lifecycle
    by_action = {r["action"]: r for r in rows}
    assert by_action["CREATE_CUSTOMER"]["target_id"] == cid
    assert by_action["CREATE_CUSTOMER"]["target_type"] == "CUSTOMER"
    assert by_action["CREATE_LOCATION"]["target_id"] == lid
    assert by_action["CREATE_LOCATION"]["details"]["customerId"] == cid
    assert by_action["MINT_KEY"]["target_id"] == kid
    assert by_action["REVOKE_KEY"]["target_id"] == kid


def test_tier_change_records_before_and_after(lifecycle):
    rows, _cid, _lid, _kid = lifecycle
    by_action = {r["action"]: r for r in rows}
    assert by_action["CREATE_CUSTOMER"]["details"]["tier"] == "clinical"
    assert by_action["SET_TIER"]["details"]["tier"] == {"from": "clinical", "to": "core"}


def test_no_audit_row_leaks_a_secret(lifecycle):
    rows, _cid, _lid, _kid = lifecycle
    for r in rows:
        blob = json.dumps(r["details"] or {})
        assert SECRET_PW not in blob, r
        assert SECRET_USER not in blob, r
        assert "pa_test_" not in blob and "pa_live_" not in blob, r  # no raw key


def test_credential_and_key_rows_only_carry_safe_keys(lifecycle):
    rows, _cid, _lid, _kid = lifecycle
    by_action = {r["action"]: r for r in rows}
    assert set(by_action["CREATE_LOCATION"]["details"]) == {
        "customerId",
        "name",
        "pharmapiUnitId",
        "eopyy",
    }
    assert set(by_action["MINT_KEY"]["details"]) == {"locationId", "label", "env"}
