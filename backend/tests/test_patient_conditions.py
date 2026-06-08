"""Safety-engine integration for patient conditions.

Proves the round-trip the feature depends on: a condition created through the
conditions service is picked up by the rule engine on the next evaluation, and
soft-deleting it makes the engine stop flagging. Drug: metformin (A10BA02) +
condition RENAL_SEVERE -> the seeded METFORMIN_RENAL_CONTRAINDICATION shape.

The suite has no live DB, so a lightweight fake AsyncSession records added rows
and serves them back to the conditions() query — enough for the
create -> read -> evaluate path. Env vars are set before importing app modules
because get_settings is lru_cached and several modules read settings at import.
"""

import asyncio
import base64
import os
import uuid
from datetime import UTC, datetime

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

from unittest.mock import patch  # noqa: E402

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy.exc import IntegrityError  # noqa: E402
from sqlalchemy.sql.elements import BindParameter  # noqa: E402

from app.constants import AdrSeverity, AlertStatus, CheckType  # noqa: E402
from app.db.models.patient_condition import PatientCondition  # noqa: E402
from app.db.models.safety_rule import SafetyRule  # noqa: E402
from app.db.session import get_session  # noqa: E402
from app.deps import get_current_user  # noqa: E402
from app.services.patients import (  # noqa: E402
    create_condition,
    deactivate_condition,
)
from app.services.safety_engine import evaluate_safety  # noqa: E402
from main import app  # noqa: E402

PHARMACY_ID = uuid.uuid4()
PHARMACIST_ID = uuid.uuid4()
AMKA = "99999999999"  # absent from MOCK_INTOLERANCES, so only condition rules can fire


class _FakeScalarResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows

    def one_or_none(self):
        return self._rows[0] if self._rows else None


class _FakeConditionSession:
    """Records added rows; serves PatientCondition queries from memory.

    Only the conditions() SELECT reaches scalars() in this test path:
    evaluate_safety is called with rules= (skips the SafetyRule load) and a
    contraindication-only rule set means no rx_history round-trip.
    """

    def __init__(self):
        self.rows: list = []

    def add(self, obj):
        self.rows.append(obj)

    async def commit(self):
        pass

    async def flush(self):
        pass

    async def refresh(self, obj):
        # Mirror the server-side id default the ORM would populate on insert.
        if getattr(obj, "id", None) is None:
            obj.id = uuid.uuid4()

    async def scalars(self, _stmt):
        rows = [
            r
            for r in self.rows
            if isinstance(r, PatientCondition)
            and r.amka == AMKA
            and r.pharmacy_id == PHARMACY_ID
            and r.active
        ]
        return _FakeScalarResult(rows)


def _renal_rule() -> SafetyRule:
    return SafetyRule(
        rule_code="METFORMIN_RENAL_CONTRAINDICATION",
        check_type=CheckType.CONTRAINDICATIONS,
        trigger_atc="A10BA02",
        trigger_condition_code="RENAL_SEVERE",
        conflicting_atc=None,
        severity=AdrSeverity.SEVERE,
        message_en="Metformin is contraindicated in severe renal impairment.",
        details_en=None,
        recommended_action_en=None,
        active=True,
    )


def _metformin_rx() -> dict:
    return {
        "rxId": "RX-TEST-RENAL",
        "patient": {"id": AMKA, "amka": AMKA},
        "medication": {"atcCode": "A10BA02"},
    }


async def _create_renal(session: _FakeConditionSession) -> PatientCondition:
    return await create_condition(
        session,
        amka=AMKA,
        condition_code="RENAL_SEVERE",
        name="Severe renal impairment",
        severity="SEVERE",
        notes=None,
        recorded_by=PHARMACIST_ID,
        pharmacy_id=PHARMACY_ID,
    )


def test_created_condition_triggers_contraindication():
    async def _run():
        session = _FakeConditionSession()
        rule, rx = _renal_rule(), _metformin_rx()

        # No condition on file yet -> the contraindication must NOT fire.
        before = await evaluate_safety(session, rx, PHARMACY_ID, rules=[rule])
        assert not any(c.check_type == CheckType.CONTRAINDICATIONS for c in before.checks)

        # Pharmacist records the condition via the same service the router uses.
        created = await _create_renal(session)
        assert created.id is not None
        assert created.active is True

        # Same prescription is now flagged by the engine.
        after = await evaluate_safety(session, rx, PHARMACY_ID, rules=[rule])
        fired = [c for c in after.checks if c.check_type == CheckType.CONTRAINDICATIONS]
        assert len(fired) == 1
        assert fired[0].id == "RX-TEST-RENAL_METFORMIN_RENAL_CONTRAINDICATION"
        assert fired[0].status == AlertStatus.BLOCK

    asyncio.run(_run())


def test_soft_deleted_condition_stops_firing():
    async def _run():
        session = _FakeConditionSession()
        rule, rx = _renal_rule(), _metformin_rx()

        created = await _create_renal(session)
        fired = await evaluate_safety(session, rx, PHARMACY_ID, rules=[rule])
        assert any(c.check_type == CheckType.CONTRAINDICATIONS for c in fired.checks)

        # Soft delete -> the engine stops seeing the condition.
        await deactivate_condition(session, created)
        after = await evaluate_safety(session, rx, PHARMACY_ID, rules=[rule])
        assert not any(c.check_type == CheckType.CONTRAINDICATIONS for c in after.checks)

    asyncio.run(_run())


# ── HTTP router-layer tests ───────────────────────────────────────────────────
# TestClient + a fake session that filters PatientCondition rows by the WHERE
# equality binds (always enforcing active=True), plus monkeypatched resolve /
# find_pharmacy_by_name. Covers the validation + multi-tenancy contract the
# service-level tests above don't reach.

ROUTER_AMKA = "11122233344"


class _AllResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows

    def one_or_none(self):
        return self._rows[0] if self._rows else None


def _eq_binds(stmt) -> dict:
    where = stmt.whereclause
    binds: dict = {}
    if where is None:
        return binds
    clauses = list(where.clauses) if hasattr(where, "clauses") else [where]
    for clause in clauses:
        left = getattr(clause, "left", None)
        right = getattr(clause, "right", None)
        key = getattr(left, "key", None)
        if key and isinstance(right, BindParameter):
            binds[key] = right.value
    return binds


class _CrudSession:
    """Serves PatientCondition queries from memory by matching the WHERE
    equality binds; the `active IS TRUE` clause (not a bind) is enforced
    manually. Supports the create/get/update/deactivate service paths."""

    def __init__(self):
        self.rows: list = []

    def add(self, obj):
        self.rows.append(obj)

    async def commit(self):
        pass

    async def flush(self):
        pass

    async def refresh(self, obj):
        # Mirror the server-side defaults the response_model serializer requires.
        if getattr(obj, "id", None) is None:
            obj.id = uuid.uuid4()
        now = datetime.now(UTC)
        if getattr(obj, "created_at", None) is None:
            obj.created_at = now
        obj.updated_at = now

    async def scalars(self, stmt):
        binds = _eq_binds(stmt)
        rows = [
            r
            for r in self.rows
            if isinstance(r, PatientCondition)
            and r.active
            and all(getattr(r, k) == v for k, v in binds.items())
        ]
        return _AllResult(rows)


class _FakePharmacy:
    def __init__(self, pharmacy_id):
        self.id = pharmacy_id


async def _fake_resolve(_patient_id):
    return {"id": ROUTER_AMKA, "amka": ROUTER_AMKA}


def _client(session, pharmacy_id):
    async def _fake_session():
        yield session

    async def _fake_user():
        return {
            "pharmacist_id": str(uuid.uuid4()),
            "pharmacy_id": str(pharmacy_id),
            "pharmacy": "Test Pharmacy",
            "email": "rx@example.gr",
            "full_name": "Rx",
            "eof_licence_no": "EOF-1",
        }

    app.dependency_overrides[get_session] = _fake_session
    app.dependency_overrides[get_current_user] = _fake_user
    return TestClient(app)


def _patched(pharmacy):
    async def _fake_find(_session, _name):
        return pharmacy

    return patch.multiple(
        "app.routers.patients",
        resolve=_fake_resolve,
        find_pharmacy_by_name=_fake_find,
    )


def test_post_missing_field_returns_422():
    pid = uuid.uuid4()
    client = _client(_CrudSession(), pid)
    try:
        with _patched(_FakePharmacy(pid)):
            r = client.post(f"/patients/{ROUTER_AMKA}/conditions", json={"name": "Renal"})
        assert r.status_code == 422, r.text
    finally:
        app.dependency_overrides.clear()


def test_post_blank_name_returns_422():
    pid = uuid.uuid4()
    client = _client(_CrudSession(), pid)
    try:
        with _patched(_FakePharmacy(pid)):
            r = client.post(
                f"/patients/{ROUTER_AMKA}/conditions",
                json={"conditionCode": "RENAL_SEVERE", "name": "   "},
            )
        assert r.status_code == 422, r.text
    finally:
        app.dependency_overrides.clear()


def test_patch_null_name_returns_422():
    pid = uuid.uuid4()
    client = _client(_CrudSession(), pid)
    try:
        with _patched(_FakePharmacy(pid)):
            r = client.patch(
                f"/patients/{ROUTER_AMKA}/conditions/{uuid.uuid4()}",
                json={"name": None},
            )
        assert r.status_code == 422, r.text
    finally:
        app.dependency_overrides.clear()


def test_create_then_get_roundtrip():
    pid = uuid.uuid4()
    session = _CrudSession()
    client = _client(session, pid)
    try:
        with _patched(_FakePharmacy(pid)):
            r = client.post(
                f"/patients/{ROUTER_AMKA}/conditions",
                json={
                    "conditionCode": "RENAL_SEVERE",
                    "name": "  Severe renal  ",
                    "severity": "SEVERE",
                },
            )
            assert r.status_code == 201, r.text
            body = r.json()
            assert body["name"] == "Severe renal"  # server trimmed
            assert body["conditionCode"] == "RENAL_SEVERE"
            assert body["active"] is True
            listing = client.get(f"/patients/{ROUTER_AMKA}/conditions")
            assert listing.status_code == 200
            assert any(c["id"] == body["id"] for c in listing.json())
    finally:
        app.dependency_overrides.clear()


def test_cross_pharmacy_patch_returns_404():
    pharmacy_a = uuid.uuid4()
    pharmacy_b = uuid.uuid4()
    session = _CrudSession()
    # A condition that belongs to pharmacy B.
    other = PatientCondition(
        id=uuid.uuid4(),
        amka=ROUTER_AMKA,
        condition_code="RENAL_SEVERE",
        name="Renal",
        severity="SEVERE",
        notes=None,
        recorded_by=uuid.uuid4(),
        pharmacy_id=pharmacy_b,
        active=True,
    )
    session.add(other)
    # ...requested by a pharmacist signed in at pharmacy A.
    client = _client(session, pharmacy_a)
    try:
        with _patched(_FakePharmacy(pharmacy_a)):
            r = client.patch(
                f"/patients/{ROUTER_AMKA}/conditions/{other.id}",
                json={"name": "hijacked"},
            )
        assert r.status_code == 404, r.text
        assert other.name == "Renal"  # untouched
    finally:
        app.dependency_overrides.clear()


class _UniqueEnforcingSession(_CrudSession):
    """Simulates Postgres's `uq_patient_conditions_amka_condition_active`
    partial unique index: a second add() of an active row with an existing
    (amka, condition_code) defers an IntegrityError to the next commit()."""

    def __init__(self):
        super().__init__()
        self._pending_dup = False

    def add(self, obj):
        if isinstance(obj, PatientCondition) and obj.active:
            for existing in self.rows:
                if (
                    isinstance(existing, PatientCondition)
                    and existing.active
                    and existing.amka == obj.amka
                    and existing.condition_code == obj.condition_code
                ):
                    # Mirror Postgres: the failing INSERT is never persisted.
                    self._pending_dup = True
                    return
        super().add(obj)

    async def commit(self):
        if self._pending_dup:
            self._pending_dup = False
            raise IntegrityError(
                "INSERT INTO patient_conditions ...",
                {},
                Exception(
                    "duplicate key value violates unique constraint "
                    '"uq_patient_conditions_amka_condition_active"'
                ),
            )
        await super().commit()

    async def rollback(self):
        pass


def test_post_duplicate_returns_409():
    pid = uuid.uuid4()
    session = _UniqueEnforcingSession()
    client = _client(session, pid)
    try:
        with _patched(_FakePharmacy(pid)):
            body = {
                "conditionCode": "E11.9",
                "name": "Type 2 Diabetes Mellitus",
                "severity": "MODERATE",
            }
            first = client.post(f"/patients/{ROUTER_AMKA}/conditions", json=body)
            assert first.status_code == 201, first.text

            second = client.post(f"/patients/{ROUTER_AMKA}/conditions", json=body)
            assert second.status_code == 409, second.text
            assert "already recorded" in second.json()["detail"].lower()

            # GET still shows exactly one active row — the duplicate was rolled back.
            listing = client.get(f"/patients/{ROUTER_AMKA}/conditions")
            assert listing.status_code == 200
            rows = [c for c in listing.json() if c["conditionCode"] == "E11.9"]
            assert len(rows) == 1
    finally:
        app.dependency_overrides.clear()


def test_delete_then_patch_returns_404():
    pid = uuid.uuid4()
    session = _CrudSession()
    client = _client(session, pid)
    try:
        with _patched(_FakePharmacy(pid)):
            created = client.post(
                f"/patients/{ROUTER_AMKA}/conditions",
                json={"conditionCode": "RENAL_SEVERE", "name": "Renal"},
            ).json()
            assert (
                client.request(
                    "DELETE", f"/patients/{ROUTER_AMKA}/conditions/{created['id']}"
                ).status_code
                == 200
            )
            # Deleted (active=false) -> no longer addressable.
            again = client.patch(
                f"/patients/{ROUTER_AMKA}/conditions/{created['id']}",
                json={"name": "x"},
            )
            assert again.status_code == 404, again.text
    finally:
        app.dependency_overrides.clear()
