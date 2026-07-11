"""ATC-normalization resolver + its two safety-engine wirings.

Covers ``services/substance_resolver`` (substance/name/brand → ATC, unambiguous-
only, most-confident-first) and the two ``evaluate_safety`` paths it revives in
LIVE mode:

  §1 co-medication interactions from Pharmapi history ``commercialName``
  §2 intolerance contraindications from Pharmapi ``activeSubstance``

No live DB / no live Pharmapi: the resolver's three catalog passes are
monkeypatched to canned maps (the SQL is thin and driver-covered), and the
engine's upstream fetches (``patient_intolerances``, ``rx_history``) return
live-shaped fixtures. So these pin the *wiring and precedence* — the part that
carries logic — the same way test_patient_conditions pins the condition path.
Env vars are set before importing app modules (get_settings is lru_cached).
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

import app.services.safety_engine as engine  # noqa: E402
import app.services.substance_resolver as resolver  # noqa: E402
from app.constants import AdrSeverity, AlertStatus, CheckType  # noqa: E402
from app.db.models.safety_rule import SafetyRule  # noqa: E402
from app.services.substance_resolver import DrugHint, ResolvedAtc, resolve_atcs  # noqa: E402

AMKA = "12345678901"


# ── resolver: unambiguity + pass precedence ────────────────────────────────────


def test_pick_unambiguous_keeps_agreeing_drops_conflicting():
    got = resolver._pick_unambiguous(
        [
            ("WARF", "B01AA03"),
            ("WARF", "B01AA03"),  # same substance, two brands → kept
            ("AMBIG", "N02BE01"),
            ("AMBIG", "M01AE01"),  # two distinct ATCs → dropped, not guessed
            ("NOATC", ""),  # blank ATC → ignored
        ]
    )
    assert got == {"WARF": "B01AA03"}


def test_resolve_atcs_precedence_and_alignment(monkeypatch):
    async def _run():
        async def fake_code(_session, _codes):
            return {"C1": "A10BA02"}

        async def fake_inn(_session, _names):
            return {"amoxicillin": "J01CA04"}

        async def fake_brand(_session, _brands):
            return {"Salospir": "B01AC06"}

        monkeypatch.setattr(resolver, "_by_substance_code", fake_code)
        monkeypatch.setattr(resolver, "_by_inn_name", fake_inn)
        monkeypatch.setattr(resolver, "_by_commercial_name", fake_brand)

        hints = [
            DrugHint(substance_code="C1"),
            DrugHint(substance_name="Amoxicillin"),
            DrugHint(commercial_name="Salospir"),
            DrugHint(substance_name="Unobtainium"),  # resolves to nothing
        ]
        out = await resolve_atcs(None, hints)

        assert [r.atc_code if r else None for r in out] == [
            "A10BA02",
            "J01CA04",
            "B01AC06",
            None,
        ]
        assert [r.method if r else None for r in out] == [
            "substance_code",
            "inn_name",
            "commercial_name",
            None,
        ]
        assert out[2].confidence == "low"  # brand match is low-confidence

    asyncio.run(_run())


# ── engine §2: live intolerance → contraindication ─────────────────────────────


def test_live_intolerance_contraindication_fires(monkeypatch):
    async def _run():
        monkeypatch.setattr(engine, "is_mock_pharmapi", lambda: False)

        async def fake_intol(_amka):
            return [{"activeSubstance": "Amoxicillin"}]

        async def fake_resolve(_session, _hints):
            return [ResolvedAtc("J01CA04", "inn_name", "high")]

        monkeypatch.setattr(engine, "patient_intolerances", fake_intol)
        monkeypatch.setattr(engine, "resolve_atcs", fake_resolve)

        rx = {
            "rxId": "RX1",
            "patient": {"id": AMKA, "amka": AMKA},
            "medication": {"atcCode": "J01CA01"},  # same J01C class as the intolerance
        }
        payload = await engine.evaluate_safety(None, rx, uuid.uuid4(), rules=[])
        contra = [c for c in payload.checks if c.check_type == CheckType.CONTRAINDICATIONS]
        assert contra, "a recorded live intolerance should raise a contraindication"
        # Going live must not be weaker than the mock: a recorded allergy to the
        # dispensed drug's class defaults to SEVERE → BLOCK, not a soft REVIEW.
        assert contra[0].status == AlertStatus.BLOCK

    asyncio.run(_run())


def test_explicit_empty_intolerances_skips_live_fetch(monkeypatch):
    """The dashboard fix: intolerances=[] must NOT trigger a per-rx ΗΔΥΚΑ fetch,
    even in live mode — otherwise a 100-prescription dashboard fires 100 calls."""

    async def _run():
        monkeypatch.setattr(engine, "is_mock_pharmapi", lambda: False)

        async def boom(_amka):
            raise AssertionError("patient_intolerances must not be called when intolerances=[]")

        monkeypatch.setattr(engine, "patient_intolerances", boom)

        rx = {
            "rxId": "RX1",
            "patient": {"id": AMKA, "amka": AMKA},
            "medication": {"atcCode": "J01CA01"},
        }
        payload = await engine.evaluate_safety(None, rx, uuid.uuid4(), rules=[], intolerances=[])
        assert all(c.check_type != CheckType.CONTRAINDICATIONS for c in payload.checks)

    asyncio.run(_run())


# ── engine §1: live history brand → co-medication interaction ──────────────────


def test_live_history_interaction_via_brand(monkeypatch):
    async def _run():
        monkeypatch.setattr(engine, "is_mock_pharmapi", lambda: False)

        async def fake_history(_pid):
            return [{"rxId": "OTHER-BARCODE", "drugName": "Aspirin"}]

        async def fake_resolve(_session, _hints):
            return [ResolvedAtc("B01AC06", "commercial_name", "low")]  # aspirin

        async def fake_intol(_amka):
            return []  # keep §2 quiet

        monkeypatch.setattr(engine, "rx_history", fake_history)
        monkeypatch.setattr(engine, "resolve_atcs", fake_resolve)
        monkeypatch.setattr(engine, "patient_intolerances", fake_intol)

        rule = SafetyRule(
            rule_code="WARFARIN_ASPIRIN_BLEED",
            check_type=CheckType.INTERACTIONS,
            trigger_atc="B01AA03",  # warfarin — the newly dispensed drug
            conflicting_atc="B01AC06",  # aspirin — resolved from history brand
            trigger_condition_code=None,
            severity=AdrSeverity.SEVERE,
            message_en="Bleeding risk.",
            details_en=None,
            recommended_action_en=None,
            active=True,
        )
        rx = {
            "rxId": "RX-NEW",
            "patient": {"id": AMKA, "amka": AMKA},
            "medication": {"atcCode": "B01AA03"},
        }
        payload = await engine.evaluate_safety(None, rx, uuid.uuid4(), rules=[rule])
        assert any(c.check_type == CheckType.INTERACTIONS for c in payload.checks)

    asyncio.run(_run())
