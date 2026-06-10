"""B2B API-key minting, hashing, and resolution (BC-3 / D-4 / FT-13).

Keys are ``pa_<env>_<token_urlsafe(32)>`` — ~256 bits of entropy — shown
exactly once at mint (scripts/b2b_admin.py) and stored ONLY as a sha256 hex
digest. High-entropy random keys make a fast deterministic hash safe here;
bcrypt is for low-entropy passwords and is too slow per-request. The raw key
must never be logged or persisted.

The ``pa_test_`` / ``pa_live_`` prefix is ENFORCED, not cosmetic (FT-13): a
key only resolves on a deployment whose mode matches its env label. The
sandbox IS the mock-mode stack (PHARMAPI_MOCK=true ⇒ accepts ``pa_test_``
only); a live deployment accepts ``pa_live_`` only. So a sandbox key pasted
into a production integration — or the reverse — fails with the same
indistinguishable 401 as any bad key, instead of silently working against
the wrong upstream.
"""

import hashlib
import secrets

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.db.models.api_key import ApiKey
from app.db.models.customer import Customer
from app.db.models.location import Location
from app.utils.environment import is_mock_pharmapi


def generate_api_key(env_label: str = "live") -> str:
    """Mint a new raw API key. Caller shows it once and stores only the hash."""
    return f"pa_{env_label}_{secrets.token_urlsafe(32)}"


def hash_api_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode()).hexdigest()


def key_env_label(raw_key: str) -> str | None:
    """``pa_test_…`` → 'test', ``pa_live_…`` → 'live', anything else → None."""
    if raw_key.startswith("pa_test_"):
        return "test"
    if raw_key.startswith("pa_live_"):
        return "live"
    return None


def deployment_env_label() -> str:
    """Which key environment THIS deployment accepts (FT-13).

    Mock mode is the sandbox; live mode is production. Re-read per call, same
    as is_mock_pharmapi itself.
    """
    return "test" if is_mock_pharmapi() else "live"


async def resolve_api_key(
    session: AsyncSession, raw_key: str
) -> tuple[ApiKey, Location, Customer] | None:
    """Env-match → hash → lookup → active checks. Returns None for ANY failure
    mode (env-mismatched, unknown, revoked key, inactive location, inactive
    customer) so the caller can return one indistinguishable 401."""
    if key_env_label(raw_key) != deployment_env_label():
        return None
    row = (
        await session.scalars(
            select(ApiKey)
            .options(joinedload(ApiKey.location).joinedload(Location.customer))
            .where(ApiKey.key_hash == hash_api_key(raw_key))
        )
    ).one_or_none()
    if row is None or not row.active:
        return None
    location = row.location
    if location is None or not location.active:
        return None
    customer = location.customer
    if customer is None or not customer.active:
        return None
    return row, location, customer
