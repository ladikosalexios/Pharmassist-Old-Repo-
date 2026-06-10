"""X-API-Key dependency for the B2B /v1 surface (BC-3).

Parallel to deps.get_current_user (B2C cookie auth) — the two never mix.
Resolves the key hash to customer + location, decrypts the location's ΗΔΥΚΑ
credentials in-memory, and hands routers an ApiContext carrying the ready-
to-use PharmapiContext. All auth failure modes return one indistinguishable
401 (no oracle for key-exists/revoked/inactive).
"""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import Depends, Header, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.crypto import decrypt_credential
from app.db.session import get_session
from app.services.api_keys import resolve_api_key
from app.services.pharmapi import PharmapiContext

# Refresh last_used_at at most this often — keeps the per-request write
# amplification bounded without losing usage visibility.
_LAST_USED_REFRESH = timedelta(minutes=5)


def _unauthorized() -> HTTPException:
    # A fresh instance per raise — never a shared module singleton, so nothing
    # added to the exception during handling (e.g. headers) can leak across
    # concurrent requests.
    return HTTPException(status_code=401, detail="Invalid or missing API key")


@dataclass(frozen=True)
class ApiContext:
    """Per-request tenant context resolved from X-API-Key."""

    customer_id: UUID
    customer_name: str
    location_id: UUID
    location_name: str
    api_key_id: UUID
    is_eopyy: bool
    pharmapi: PharmapiContext


async def get_api_context(
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    db: AsyncSession = Depends(get_session),
) -> ApiContext:
    if not x_api_key:
        raise _unauthorized()

    resolved = await resolve_api_key(db, x_api_key)
    if resolved is None:
        raise _unauthorized()
    key_row, location, customer = resolved

    if not location.pharmapi_username or not location.pharmapi_password:
        # Server-side provisioning gap, not a caller error — but don't leak
        # tenant existence details either.
        raise HTTPException(status_code=500, detail="Location is not fully provisioned")

    settings = get_settings()
    ctx = PharmapiContext(
        # Decrypted in-memory for this request only — never logged.
        username=decrypt_credential(location.pharmapi_username),
        password=decrypt_credential(location.pharmapi_password),
        api_key=settings.pharmapi_api_key,
        base_url=settings.pharmapi_base,
        pharmacy_unit_id=location.pharmapi_unit_id,
        session_key=f"location:{location.id}",
    )

    now = datetime.now(UTC)
    if key_row.last_used_at is None or now - key_row.last_used_at > _LAST_USED_REFRESH:
        key_row.last_used_at = now
        await db.commit()

    return ApiContext(
        customer_id=customer.id,
        customer_name=customer.name,
        location_id=location.id,
        location_name=location.name,
        api_key_id=key_row.id,
        is_eopyy=location.is_eopyy,
        pharmapi=ctx,
    )
