"""Cache-hit AC for POST /v1/safety/explain (T2-6) — needs the live compose DB.

The headline ticket AC: a second identical (rule, condition-profile) request makes
ZERO LLM calls and is served from the cache. We prove it in mock mode (no provider
needed) by counting invocations of the registered mock generator — the seam calls
it only on a cache miss, so a flat count across the second call IS "0 LLM calls".

Also drives the full HTTP endpoint against the real DB once (tier gate passes,
200 + shape, cached flips false→true). NOT part of the CI pytest job — it needs
the running compose Postgres, same as test_ai_cache_db.py, and so is named *_db.py
and added to the workflow's --ignore list.
"""

import base64
import os

os.environ.setdefault("ENV", "test")
os.environ.setdefault("LLM_MOCK", "true")
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
import uuid  # noqa: E402

import httpx  # noqa: E402
from sqlalchemy import delete  # noqa: E402

from app.constants import AdrSeverity, CheckType  # noqa: E402
from app.db.models.ai_response_cache import AiResponseCache  # noqa: E402
from app.db.models.safety_rule import SafetyRule  # noqa: E402
from app.db.session import AsyncSessionLocal, get_session  # noqa: E402
from app.routers.v1.deps import ApiContext, get_api_context  # noqa: E402
from app.services import ai_cache, llm  # noqa: E402
from app.services.pharmapi import PharmapiContext  # noqa: E402
from app.services.safety_explanations import (  # noqa: E402
    KIND_SAFETY_EXPLANATION,
    build_input,
    explain_rule,
)
from main import create_app  # noqa: E402

# Distinctive ATC codes so this rule's cache key never collides with a seeded one.
_RULE = SafetyRule(
    rule_code="PYTEST_EXPLAIN_DB_RULE",
    check_type=CheckType.INTERACTIONS,
    trigger_atc="ZZZTEST01",
    conflicting_atc="ZZZTEST02",
    trigger_condition_code=None,
    severity=AdrSeverity.SEVERE,
    message_en="pytest explain message",
    details_en="pytest explain detail",
    recommended_action_en="pytest explain action",
    active=True,
)
_KEY = ai_cache.cache_key(
    KIND_SAFETY_EXPLANATION, build_input(_RULE, []).cache_input(), model="mock"
)


async def _cleanup_cache():
    async with AsyncSessionLocal() as s:
        await s.execute(delete(AiResponseCache).where(AiResponseCache.cache_key == _KEY))
        await s.commit()


def test_second_identical_call_is_cached_zero_llm_calls():
    """Miss generates + commits; an identical call is served from the cache with
    no further mock-generator (≡ LLM) invocation."""

    async def run():
        await _cleanup_cache()
        calls = {"n": 0}
        original_mock = llm._MOCKS[KIND_SAFETY_EXPLANATION]

        def counting_mock(fields):
            calls["n"] += 1
            return original_mock(fields)

        llm._MOCKS[KIND_SAFETY_EXPLANATION] = counting_mock
        try:
            async with AsyncSessionLocal() as s1:
                first = await explain_rule(s1, _RULE, [])
            assert first["cached"] is False
            assert calls["n"] == 1  # generated once on the miss

            async with AsyncSessionLocal() as s2:
                second = await explain_rule(s2, _RULE, [])
            assert second["cached"] is True  # served from the cache
            assert calls["n"] == 1  # ← the AC: zero LLM calls on the 2nd call
            # Same Greek payload both times.
            assert second["rationale"] == first["rationale"]
            assert second["mechanism"] == first["mechanism"]
            assert second["risk_level"] == "Υψηλός"
        finally:
            llm._MOCKS[KIND_SAFETY_EXPLANATION] = original_mock
            await _cleanup_cache()

    asyncio.run(run())


def test_distinct_condition_profile_is_a_separate_cache_entry():
    """A different sorted condition-profile keys a different cache entry (so the
    rationale really is per rule + condition profile, not per rule alone)."""
    key_empty = ai_cache.cache_key(
        KIND_SAFETY_EXPLANATION, build_input(_RULE, []).cache_input(), model="mock"
    )
    key_preg = ai_cache.cache_key(
        KIND_SAFETY_EXPLANATION, build_input(_RULE, ["PREGNANCY"]).cache_input(), model="mock"
    )
    assert key_empty != key_preg


# ── Full HTTP round-trip against the real DB ───────────────────────────────────


def _clinical_ctx() -> ApiContext:
    location_id = uuid.uuid4()
    return ApiContext(
        customer_id=uuid.uuid4(),
        customer_name="Explain DB SA",
        tier="clinical",
        location_id=location_id,
        location_name="Explain DB Store",
        api_key_id=uuid.uuid4(),
        is_eopyy=True,
        pharmapi=PharmapiContext(
            username="u",
            password="p",
            api_key="k",
            base_url="https://unused.example.test",
            pharmacy_unit_id=70124,
            session_key=f"location:{location_id}",
        ),
    )


async def _real_get_session():
    async with AsyncSessionLocal() as session:
        yield session


async def _set_rule(present: bool):
    async with AsyncSessionLocal() as s:
        await s.execute(delete(SafetyRule).where(SafetyRule.rule_code == _RULE.rule_code))
        if present:
            s.add(
                SafetyRule(
                    rule_code=_RULE.rule_code,
                    check_type=_RULE.check_type,
                    trigger_atc=_RULE.trigger_atc,
                    conflicting_atc=_RULE.conflicting_atc,
                    severity=_RULE.severity,
                    message_en=_RULE.message_en,
                    details_en=_RULE.details_en,
                    recommended_action_en=_RULE.recommended_action_en,
                    active=True,
                )
            )
        await s.commit()


def test_http_explain_round_trip_and_unknown_rule_422():
    """End-to-end against the real DB: tier gate passes, rules load, 200 + camelCase
    shape, and the cache flips false→true on the 2nd identical POST.

    Everything runs in ONE event loop (httpx.ASGITransport, not the sync
    TestClient) so the app's AsyncSessionLocal connections and this test's setup /
    teardown share a single loop — mixing asyncio.run() with the TestClient's own
    loop corrupts the asyncpg pool. The prior service-level tests left the global
    pool bound to their (now-closed) loops, so we discard it first."""

    async def run():
        from app.db.session import engine

        await engine.dispose(close=False)  # fresh pool for this loop
        await _cleanup_cache()
        await _set_rule(present=True)

        app = create_app()
        app.dependency_overrides[get_api_context] = _clinical_ctx
        app.dependency_overrides[get_session] = _real_get_session
        transport = httpx.ASGITransport(app=app)
        try:
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
                # 1st call → miss → cached false
                r1 = await ac.post("/v1/safety/explain", json={"ruleCodes": [_RULE.rule_code]})
                assert r1.status_code == 200, r1.text
                expl = r1.json()["explanations"]
                assert len(expl) == 1
                e = expl[0]
                assert set(e) == {
                    "ruleCode",
                    "language",
                    "rationale",
                    "mechanism",
                    "riskLevel",
                    "alternatives",
                    "cached",
                }
                assert e["ruleCode"] == _RULE.rule_code
                assert e["language"] == "el"
                assert e["riskLevel"] == "Υψηλός"
                assert e["cached"] is False

                # 2nd identical call → cache hit, zero LLM calls
                r2 = await ac.post("/v1/safety/explain", json={"ruleCodes": [_RULE.rule_code]})
                assert r2.status_code == 200, r2.text
                assert r2.json()["explanations"][0]["cached"] is True

                # Unknown rule code → 422 envelope
                r3 = await ac.post("/v1/safety/explain", json={"ruleCodes": ["NO_SUCH_RULE_XYZ"]})
                assert r3.status_code == 422, r3.text
                assert r3.json()["error"]["code"] == "validation_failed"
        finally:
            await _set_rule(present=False)
            await _cleanup_cache()

    asyncio.run(run())
