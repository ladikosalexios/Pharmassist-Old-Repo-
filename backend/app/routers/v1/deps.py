"""X-API-Key dependency for the B2B /v1 surface (BC-3).

Parallel to deps.get_current_user (B2C cookie auth) — the two never mix.
Resolves the key hash to customer + location, decrypts the location's ΗΔΥΚΑ
credentials in-memory, and hands routers an ApiContext carrying the ready-
to-use PharmapiContext. All auth failure modes return one indistinguishable
401 (no oracle for key-exists/revoked/inactive).

ΗΔΥΚΑ credentials are OPTIONAL per location (TIER0-RETRIEVAL-FREE.md T0-1):
a location provisioned without them resolves with ``pharmapi=None`` and still
reaches every upstream-free route (drugs, safety, conditions, the Tier-2
routes). Routes that call ΗΔΥΚΑ take ``Depends(require_retrieval)``, which
answers 409 ``retrieval_unavailable`` for such a location (T0-2 / D-21).
Retrieval is orthogonal to tier: any tier can be bought without credentials.
"""

import math
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import Depends, Header, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.crypto import decrypt_credential
from app.db.session import get_session
from app.services.api_keys import resolve_api_key
from app.services.pharmapi import PharmapiContext
from app.utils.ratelimit import parse_rate_limit, v1_api_key_limiter

from .errors import V1Error

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
    tier: str
    location_id: UUID
    location_name: str
    api_key_id: UUID
    is_eopyy: bool
    # None when the location was provisioned without ΗΔΥΚΑ credentials (T0-1).
    # Only routes behind require_retrieval may dereference it.
    pharmapi: PharmapiContext | None


# Entitlement tiers in ascending order of privilege (T2-1 / D-14). The gate is
# ORDINAL, not exact-match: a higher tier passes every lower tier's gate, so a
# `platform` customer reaches every `clinical` route. `clinical_only` (D-20,
# TIER0-RETRIEVAL-FREE.md T0-3) is the base: safety engine + drug catalogue
# reads only — no formulary, no Tier-2. Mirrored by the ck_customers_tier
# constraint (customer model + migration e5b1c9d47a20).
TIER_ORDER = ("clinical_only", "core", "clinical", "platform")


def _tier_rank(tier: str) -> int:
    """Ordinal rank of a tier; an unknown value fails safe to the base tier (0)
    so a bad row can only ever lose access, never silently gain it."""
    try:
        return TIER_ORDER.index(tier)
    except ValueError:
        return 0


def require_tier(minimum: str):
    """Dependency factory gating a /v1 route behind a minimum entitlement tier.

    Use as ``ctx: ApiContext = Depends(require_tier("clinical"))`` — it resolves
    the full ApiContext (so the route gets the context for free) and 403s with
    the stable ``tier_required`` envelope code when the customer's tier ranks
    below ``minimum``. Mirrors patients._require_eopyy's envelope-403 pattern.
    """
    # Intentionally `.index` (not the fail-safe _tier_rank): a typo'd minimum in
    # a `Depends(require_tier("clinicla"))` decorator raises ValueError at import
    # time and crashes the worker on boot, rather than silently under-gating a
    # route at request time. The asymmetry with _tier_rank is deliberate.
    min_rank = TIER_ORDER.index(minimum)

    async def _require_tier(ctx: ApiContext = Depends(get_api_context)) -> ApiContext:
        if _tier_rank(ctx.tier) < min_rank:
            raise V1Error(
                "tier_required",
                403,
                f"This endpoint requires the '{minimum}' tier or higher — this "
                f"account is on '{ctx.tier}'. Contact sales to upgrade.",
            )
        return ctx

    return _require_tier


async def get_api_context(
    request: Request,
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    db: AsyncSession = Depends(get_session),
) -> ApiContext:
    if not x_api_key:
        raise _unauthorized()

    resolved = await resolve_api_key(db, x_api_key)
    if resolved is None:
        raise _unauthorized()
    key_row, location, customer = resolved

    # Tenant attribution for the /v1 access log (FT-6) — stamped immediately
    # after the key resolves so even a 429 below is attributed to its tenant.
    request.state.v1_api_key_id = key_row.id
    request.state.v1_location_id = location.id
    request.state.v1_customer_id = customer.id

    # Per-key rate limit (FT-1) — after auth (only resolved active keys touch a
    # counter; an unauthenticated spray 401s above), before the AES decrypt and
    # the last_used_at write so a throttled burst sheds load early.
    settings = get_settings()
    retry_after = v1_api_key_limiter.hit(key_row.id, *parse_rate_limit(settings.v1_rate_limit))
    if retry_after is not None:
        raise V1Error(
            "rate_limited",
            429,
            f"Rate limit exceeded — {settings.v1_rate_limit} per API key",
            headers={"Retry-After": str(math.ceil(retry_after))},
        )

    # ΗΔΥΚΑ credentials are optional (T0-1): a location provisioned without
    # them gets pharmapi=None, and only require_retrieval routes refuse it (409).
    # The decrypt stays INSIDE this branch so an uncredentialed tenant never
    # touches the AES path. The ck_locations_pharmapi_credentials constraint
    # keeps username/password both-or-neither, so there is no half state here.
    pharmapi_ctx: PharmapiContext | None = None
    if location.pharmapi_username and location.pharmapi_password:
        pharmapi_ctx = PharmapiContext(
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
        # Covers a not-yet-migrated/unset row defensively — the gate then treats
        # it as the least-privileged tier rather than crashing on a None. Must be
        # TIER_ORDER[0], not "core": once clinical_only sits below core, a "core"
        # default would hand an unset row a paid upgrade (T0-3 trap 2).
        tier=customer.tier or TIER_ORDER[0],
        location_id=location.id,
        location_name=location.name,
        api_key_id=key_row.id,
        is_eopyy=location.is_eopyy,
        pharmapi=pharmapi_ctx,
    )


# OpenAPI `responses=` entry for every route behind require_retrieval, so the
# published contract (docs/b2b-core/openapi-v1.json) lists the 409 alongside
# the 200 rather than leaving it to API.md alone.
RETRIEVAL_UNAVAILABLE_RESPONSE = {
    409: {
        "description": (
            "`retrieval_unavailable` — this location has no ΗΔΥΚΑ credentials, so "
            "patient/prescription retrieval is not available. Upstream-free routes "
            "(drugs, safety, conditions) keep working."
        )
    }
}


async def require_retrieval(ctx: ApiContext = Depends(get_api_context)) -> ApiContext:
    """Dependency gating a /v1 route on the location having ΗΔΥΚΑ credentials.

    Use as ``ctx: ApiContext = Depends(require_retrieval)`` on every route that
    calls upstream — it resolves the full ApiContext (so the route gets the
    context for free, with ``ctx.pharmapi`` guaranteed non-None) and raises the
    stable ``retrieval_unavailable`` envelope when the location was provisioned
    without credentials. 409, not 403 (D-21): 403 is ``tier_required``'s
    entitlement denial, whereas this is a provisioning state the tenant can fix.
    Mirrors require_tier's envelope pattern. Enforced in mock mode too, so a
    sandbox run shows the integrator exactly what live will answer.
    """
    if ctx.pharmapi is None:
        raise V1Error(
            "retrieval_unavailable",
            409,
            "This location has no ΗΔΥΚΑ credentials, so patient and prescription "
            "retrieval is unavailable. Drug catalogue and safety-check routes still "
            "work. To enable retrieval, supply this location's ΗΔΥΚΑ credentials "
            "through PharmAssist onboarding.",
        )
    return ctx
