"""Response-cache primitive for the Tier-2 LLM seam (T2-2).

A thin read/stage surface over the ``ai_response_cache`` table. The seam
(``services/llm.py``) keys into it; feature endpoints (T2-6 caches by rule +
condition profile, etc.) get caching for free by passing a session to
``llm.complete``.

The cache key is a deterministic content hash of the prompt kind + the
*whitelisted* prompt input — never raw PII, because the typed builders in
``services/llm.py`` structurally admit no AMKA/name/address and the digit-token
scrub runs before anything is hashed.
"""

import hashlib
import json

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.ai_response_cache import AiResponseCache


def cache_key(prompt_kind: str, key_input: dict, *, model: str) -> str:
    """Deterministic sha256 over (prompt_kind, canonical-JSON of key_input, model).

    ``sort_keys`` + compact separators make the hash invariant to dict ordering
    and whitespace, so the same logical request always lands the same key (the
    whole point of the cache). ``ensure_ascii=False`` keeps Greek text stable
    across Python versions rather than escaping it inconsistently.

    ``model`` is the generating identity ("mock", or the configured model id) and
    is part of the key on purpose: a model swap auto-invalidates every old entry
    (no stale outputs served under a new model), and a mock-mode row can never be
    served to a live request — a sandbox-warmed cache flipping to live must not
    hand "[MOCK]" text to a customer. By construction the row's ``model`` column
    always matches its key's model; the column exists for retention/cleanup and
    provenance, not as the lookup discriminator.
    """
    canonical = json.dumps(
        {"kind": prompt_kind, "input": key_input, "model": model},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


async def get_cached(session: AsyncSession, key: str) -> AiResponseCache | None:
    """Return the cached row for ``key`` (carrying payload + model), or None."""
    return (
        await session.scalars(select(AiResponseCache).where(AiResponseCache.cache_key == key))
    ).one_or_none()


def stage_cached(
    session: AsyncSession,
    *,
    key: str,
    prompt_kind: str,
    payload: dict,
    model: str | None,
) -> AiResponseCache:
    """Stage a new cache row on the caller's session (the seam commits it).

    Returns the unpersisted row. A concurrent double-miss is handled by the
    UNIQUE(cache_key) constraint at commit time — ``llm.complete`` catches the
    integrity error and re-reads the winner's row.
    """
    row = AiResponseCache(cache_key=key, prompt_kind=prompt_kind, payload=payload, model=model)
    session.add(row)
    return row
