"""B2B API-key minting, hashing, and resolution (BC-3 / D-4).

Keys are ``pa_<env>_<token_urlsafe(32)>`` — ~256 bits of entropy — shown
exactly once at mint (scripts/b2b_admin.py) and stored ONLY as a sha256 hex
digest. High-entropy random keys make a fast deterministic hash safe here;
bcrypt is for low-entropy passwords and is too slow per-request. The raw key
must never be logged or persisted.
"""

import hashlib
import secrets

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.db.models.api_key import ApiKey
from app.db.models.customer import Customer
from app.db.models.location import Location


def generate_api_key(env_label: str = "live") -> str:
    """Mint a new raw API key. Caller shows it once and stores only the hash."""
    return f"pa_{env_label}_{secrets.token_urlsafe(32)}"


def hash_api_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode()).hexdigest()


async def resolve_api_key(
    session: AsyncSession, raw_key: str
) -> tuple[ApiKey, Location, Customer] | None:
    """Hash → lookup → active checks. Returns None for ANY failure mode
    (unknown, revoked key, inactive location, inactive customer) so the
    caller can return one indistinguishable 401."""
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
