# Cache primitive for the Tier-2 LLM seam (T2-2). One row per distinct AI
# request: a deterministic content hash of (prompt_kind + the whitelisted prompt
# input) maps to the model's structured output. A DB table — not an in-process
# dict — because it must survive a uvicorn restart and the single-worker
# constraint (D-8), and because the catalog requires caching by rule + condition
# profile (PharmAssist_Pricing.md:92), which T2-6/T2-10 key into this table.
#
# Read-mostly and append-on-miss: the seam looks up by cache_key, and on a miss
# stages a new row in the caller's session. Rows are not mutated in normal
# operation; T2-12 sets a retention stance over the stored payloads.
#
# PII posture: by construction the cache_key is derived only from whitelisted
# clinical fields (the typed prompt builders in services/llm.py structurally
# admit no AMKA/name/address), and `payload` holds an AI output over those same
# fields — so no patient identity is stored here. The digit-token scrub in the
# seam is the belt-and-braces guard on any free text before it is ever hashed
# or sent.

from sqlalchemy import BigInteger, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base, TimestampMixin


class AiResponseCache(Base, TimestampMixin):
    __tablename__ = "ai_response_cache"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    # sha256 hex of (prompt_kind + canonical-JSON of the prompt input). UNIQUE so
    # a lookup is a single indexed hit and a concurrent double-miss can't insert
    # two rows for the same request (the second insert violates the constraint).
    cache_key: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    # The PromptKind that produced this entry — lets retention / invalidation act
    # per feature (e.g. drop all safety-explanation entries) without parsing keys.
    prompt_kind: Mapped[str] = mapped_column(String, nullable=False)
    # The provider+model that generated `payload` (e.g. "mistral-large-latest" or
    # "mock"). Carried so a model swap is a cache-invalidation lever, not a silent
    # stale-output bug.
    model: Mapped[str | None] = mapped_column(String)
    # The structured AI output, exactly as the consuming endpoint will return it.
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
