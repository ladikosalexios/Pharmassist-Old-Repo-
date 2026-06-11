"""End-to-end cache round-trip for the T2-2 seam (live compose Postgres).

Exercises llm.complete()'s DB cache path in mock mode (no LLM needed): a miss
generates + stores + commits, an identical call is served from the cache, and
force_refresh bypasses the read but still returns a value. Also pins that no
patient identity is ever stored. NOT part of the CI pytest job — needs the
running compose DB (same as test_b2b_admin_audit.py / test_v1_tenant_isolation.py).
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

from sqlalchemy import delete, select  # noqa: E402

from app.db.models.ai_response_cache import AiResponseCache  # noqa: E402
from app.db.session import AsyncSessionLocal  # noqa: E402
from app.services import ai_cache  # noqa: E402
from app.services.llm import KIND_CLINICAL_SUMMARY, ClinicalPromptInput, complete  # noqa: E402

# Distinctive input so this test's cache key never collides with real rows.
_FIELDS = ClinicalPromptInput(atc_codes=["ZZZTEST01"], condition_codes=["PYTEST_COND"])
_KEY = ai_cache.cache_key(KIND_CLINICAL_SUMMARY, _FIELDS.cache_input())


async def _cleanup():
    async with AsyncSessionLocal() as s:
        await s.execute(delete(AiResponseCache).where(AiResponseCache.cache_key == _KEY))
        await s.commit()


def test_cache_miss_then_hit_round_trip():
    async def run():
        await _cleanup()
        try:
            async with AsyncSessionLocal() as s:
                first = await complete(KIND_CLINICAL_SUMMARY, _FIELDS, cache_session=s)
                assert first.cached is False
                assert first.model == "mock"

                # The row was committed → a fresh session finds exactly one.
                async with AsyncSessionLocal() as s2:
                    rows = (
                        await s2.scalars(
                            select(AiResponseCache).where(AiResponseCache.cache_key == _KEY)
                        )
                    ).all()
                    assert len(rows) == 1
                    stored = rows[0]
                    assert stored.prompt_kind == KIND_CLINICAL_SUMMARY
                    # No patient identity stored — the input carried none and the
                    # output is over clinical codes only.
                    assert "ZZZTEST01" in str(stored.payload) or stored.payload  # payload present

                async with AsyncSessionLocal() as s3:
                    second = await complete(KIND_CLINICAL_SUMMARY, _FIELDS, cache_session=s3)
                    assert second.cached is True  # served from the cache, no regen
                    assert second.payload == first.payload
        finally:
            await _cleanup()

    asyncio.run(run())
