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

from app.constants import AdrSeverity, AlertStatus, CheckType  # noqa: E402
from app.db.models.patient_condition import PatientCondition  # noqa: E402
from app.db.models.safety_rule import SafetyRule  # noqa: E402
from app.services.patients import (  # noqa: E402
    create_condition,
    deactivate_condition,
)
from app.services.safety_engine import evaluate_safety  # noqa: E402

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
