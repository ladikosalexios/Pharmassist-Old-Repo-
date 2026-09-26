"""Tier-entitlement gate tests for /v1 (T2-1, mock mode, DB-less).

The ordinal `require_tier()` gate is the only thing standing between a Core key
and Tier-2 revenue, so it gets pinned hard: the rank helper, the gate matrix
across two minimum-tier probes (core / clinical / platform keys), the stable
`tier_required` 403 envelope, and the tier echo on GET /v1/status.

DB-less like test_v1_contracts: get_api_context is dependency-overridden with a
synthetic ApiContext whose tier the individual test controls, and two throwaway
probe routes (gated at `clinical` and `platform`) exercise the gate without
needing a real Tier-2 route to exist yet.
"""

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

import pytest  # noqa: E402
from fastapi import Depends  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.db.session import get_session  # noqa: E402
from app.routers.v1.deps import (  # noqa: E402
    TIER_ORDER,
    ApiContext,
    _tier_rank,
    get_api_context,
    require_tier,
)
from app.services.pharmapi import PharmapiContext  # noqa: E402
from main import create_app  # noqa: E402


def _ctx(tier: str) -> ApiContext:
    location_id = uuid.uuid4()
    return ApiContext(
        customer_id=uuid.uuid4(),
        customer_name="Tier SA",
        tier=tier,
        location_id=location_id,
        location_name="Tier Store",
        api_key_id=uuid.uuid4(),
        is_eopyy=True,
        pharmapi=PharmapiContext(
            username="cu",
            password="cp",
            api_key="ck",
            base_url="https://unused.example.test",
            pharmacy_unit_id=70466,
            session_key=f"location:{location_id}",
        ),
    )


# Mutable holder so each test swaps the tier without rebuilding the app.
CURRENT = {"ctx": _ctx("core")}


async def _fake_get_session():
    yield None  # the probe routes never touch the DB


app = create_app()
app.dependency_overrides[get_api_context] = lambda: CURRENT["ctx"]
app.dependency_overrides[get_session] = _fake_get_session


# Throwaway probes: no real Tier-2 route exists at T2-1, so mount one gate per
# minimum tier and assert the matrix against them. Each echoes the resolved tier
# so we also confirm require_tier hands the route a usable ApiContext.
@app.get("/v1/_probe/core")
async def _probe_core(ctx: ApiContext = Depends(require_tier("core"))):
    return {"tier": ctx.tier}


@app.get("/v1/_probe/clinical")
async def _probe_clinical(ctx: ApiContext = Depends(require_tier("clinical"))):
    return {"tier": ctx.tier}


@app.get("/v1/_probe/platform")
async def _probe_platform(ctx: ApiContext = Depends(require_tier("platform"))):
    return {"tier": ctx.tier}


client = TestClient(app)


def _get(path: str, tier: str):
    CURRENT["ctx"] = _ctx(tier)
    try:
        return client.get(path)
    finally:
        CURRENT["ctx"] = _ctx("core")


# ── Ordinal rank helper (pure) ───────────────────────────────────────────────


def test_tier_order_is_ascending_privilege():
    # clinical_only (D-20, TIER0-RETRIEVAL-FREE.md T0-3) is the new base, below core.
    assert TIER_ORDER == ("clinical_only", "core", "clinical", "platform")


def test_tier_rank_is_strictly_increasing():
    assert (
        _tier_rank("clinical_only")
        < _tier_rank("core")
        < _tier_rank("clinical")
        < _tier_rank("platform")
    )


def test_unknown_tier_ranks_as_base_failsafe():
    # A typo'd or future-unknown tier loses access (ranks as the least-privileged
    # base tier), never gains it — the gate fails safe. T0-3 trap 1: after the
    # clinical_only insert, rank 0 is clinical_only, NOT core, and an unknown
    # value must stay strictly below every paid tier.
    assert _tier_rank("enterprise") == _tier_rank("clinical_only") == 0
    assert _tier_rank("") == 0
    assert _tier_rank("enterprise") < _tier_rank("core")


def test_base_tier_is_least_privileged():
    # get_api_context's unset-row fallback reads TIER_ORDER[0] (T0-3 trap 2); pin
    # that it is the tier no gate can be below.
    assert TIER_ORDER[0] == "clinical_only"
    assert all(_tier_rank(TIER_ORDER[0]) <= _tier_rank(t) for t in TIER_ORDER)


# ── The core gate (formulary substitution) ───────────────────────────────────


def test_clinical_only_key_403s_tier_required_on_core_route():
    r = _get("/v1/_probe/core", "clinical_only")
    assert r.status_code == 403, r.text
    assert r.json()["error"]["code"] == "tier_required"
    assert "core" in r.json()["error"]["message"]


@pytest.mark.parametrize("tier", ["core", "clinical", "platform"])
def test_core_and_above_pass_core_route(tier):
    r = _get("/v1/_probe/core", tier)
    assert r.status_code == 200, r.text
    assert r.json() == {"tier": tier}


# ── The clinical gate matrix (the commercial story) ──────────────────────────


def test_core_key_403s_tier_required_on_clinical_route():
    r = _get("/v1/_probe/clinical", "core")
    assert r.status_code == 403, r.text
    body = r.json()
    assert set(body) == {"error"}
    assert set(body["error"]) == {"code", "message", "request_id"}
    assert body["error"]["code"] == "tier_required"
    assert body["error"]["request_id"] == r.headers["x-request-id"]
    # PHI rule: the message names tiers only, never patient identifiers.
    assert "clinical" in body["error"]["message"]


def test_clinical_key_passes_clinical_route():
    r = _get("/v1/_probe/clinical", "clinical")
    assert r.status_code == 200, r.text
    assert r.json() == {"tier": "clinical"}


def test_platform_key_also_passes_clinical_route_ordinal():
    # The load-bearing ordinal assertion: platform >= clinical, so a platform
    # customer reaches every clinical route without an explicit grant.
    r = _get("/v1/_probe/clinical", "platform")
    assert r.status_code == 200, r.text
    assert r.json() == {"tier": "platform"}


# ── The platform gate (only platform passes) ─────────────────────────────────


@pytest.mark.parametrize("tier", ["clinical_only", "core", "clinical"])
def test_sub_platform_keys_403_on_platform_route(tier):
    r = _get("/v1/_probe/platform", tier)
    assert r.status_code == 403, r.text
    assert r.json()["error"]["code"] == "tier_required"


def test_platform_key_passes_platform_route():
    r = _get("/v1/_probe/platform", "platform")
    assert r.status_code == 200, r.text
    assert r.json() == {"tier": "platform"}


# ── Tier visible on /v1/status ───────────────────────────────────────────────


@pytest.mark.parametrize("tier", ["clinical_only", "core", "clinical", "platform"])
def test_status_echoes_tier(tier):
    r = _get("/v1/status", tier)
    assert r.status_code == 200, r.text
    assert r.json()["customer"]["tier"] == tier
