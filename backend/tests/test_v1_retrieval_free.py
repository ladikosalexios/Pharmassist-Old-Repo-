"""Tier-0 / retrieval-free /v1 tests — TIER0-RETRIEVAL-FREE.md T0-1, T0-2, T0-3.

DB-less (CI-runnable): the REAL get_api_context runs against in-memory ORM
tenants via a fake session (same pattern as test_v1_auth), so the credential
branch, the tenant stamping and the gates are exercised end to end. The few
DB-reading services behind the upstream-free routes are monkeypatched at the
router seam; the safety engine itself runs for real on injected rules.

What is pinned:
  * T0-1 — a location with no ΗΔΥΚΑ credentials resolves (no 500), reaches the
    upstream-free routes, never touches the AES decrypt, stays attributed in
    the /v1 access log, refreshes last_used_at and is rate limited per key.
  * T0-2 — every retrieval route answers 409 `retrieval_unavailable` for it
    (credentialed tenants unaffected), and the guarded-route inventory is
    asserted exactly. Two nets catch a route that reaches ΗΔΥΚΑ unguarded: a
    source scan of each handler (a direct ctx.pharmapi / pharmapi_* call), and
    a live-mode run of every upstream-free route with outbound HTTP blocked,
    which also sees indirect calls — the B2C helpers fall back to the legacy
    B2C credentials when handed no context.
  * T0-3 — the clinical_only entitlement matrix, incl. the unset-tier fallback,
    and retrieval's own Core tier gate for a credentialed clinical_only tenant.
  * The OpenAPI contract documents every 409 and every tier gate's 403.
"""

import base64
import inspect
import logging
import os
import re
import time

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
from datetime import UTC, datetime  # noqa: E402
from types import SimpleNamespace  # noqa: E402

import httpx  # noqa: E402
import pytest  # noqa: E402
from fastapi.routing import APIRoute  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.constants import AdrSeverity, CheckType  # noqa: E402
from app.crypto import encrypt_credential  # noqa: E402
from app.db.models.api_key import ApiKey  # noqa: E402
from app.db.models.customer import Customer  # noqa: E402
from app.db.models.location import Location  # noqa: E402
from app.db.models.safety_rule import SafetyRule  # noqa: E402
from app.db.session import get_session  # noqa: E402
from app.routers import v1 as v1_package  # noqa: E402
from app.routers.v1 import adr_reports as v1_adr_reports  # noqa: E402
from app.routers.v1 import deps as v1_deps  # noqa: E402
from app.routers.v1 import drugs as v1_drugs  # noqa: E402
from app.routers.v1 import patients as v1_patients  # noqa: E402
from app.routers.v1 import prescriptions as v1_prescriptions  # noqa: E402
from app.routers.v1 import safety as v1_safety  # noqa: E402
from app.routers.v1 import safety_explain as v1_safety_explain  # noqa: E402
from app.routers.v1.deps import TIER_ORDER, require_retrieval  # noqa: E402
from app.services import b2b_adr, b2b_conditions, pharmapi, safety_explanations  # noqa: E402
from app.services.api_keys import generate_api_key, hash_api_key  # noqa: E402
from app.services.v1_mock import MOCK_V1_PRESCRIPTIONS  # noqa: E402
from app.utils.ratelimit import v1_api_key_limiter  # noqa: E402
from main import create_app  # noqa: E402

AMKA = "15031962456"  # mock fixture patient (demographics, intolerances, history)
RX_ID = MOCK_V1_PRESCRIPTIONS[0]["rxId"]


# ── In-memory tenants ────────────────────────────────────────────────────────


def _tenant(
    name: str, *, tier: str | None, credentialed: bool, env: str = "test"
) -> tuple[str, ApiKey]:
    raw_key = generate_api_key(env)
    customer = Customer(id=uuid.uuid4(), name=f"{name} SA", active=True, tier=tier)
    location = Location(
        id=uuid.uuid4(),
        customer_id=customer.id,
        name=f"{name} Store",
        pharmapi_unit_id=70466 if credentialed else None,
        pharmapi_username=encrypt_credential(f"{name}-user") if credentialed else None,
        pharmapi_password=encrypt_credential(f"{name}-pass") if credentialed else None,
        is_eopyy=credentialed,
        active=True,
    )
    key = ApiKey(
        id=uuid.uuid4(),
        location_id=location.id,
        key_hash=hash_api_key(raw_key),
        label="test",
        active=True,
        last_used_at=None,
    )
    location.customer = customer
    key.location = location
    return raw_key, key


# The Second Opinion shape: a paying Core customer with no ΗΔΥΚΑ credentials.
KEY_CORE_NOCREDS, _ROW_CORE_NOCREDS = _tenant("CoreNoCreds", tier="core", credentialed=False)
KEY_CORE_CREDS, _ROW_CORE_CREDS = _tenant("CoreCreds", tier="core", credentialed=True)
KEY_T0, _ROW_T0 = _tenant("ClinicalOnly", tier="clinical_only", credentialed=False)
KEY_CLIN_NOCREDS, _ROW_CLIN_NOCREDS = _tenant("ClinNoCreds", tier="clinical", credentialed=False)
KEY_UNSET_TIER, _ROW_UNSET_TIER = _tenant("UnsetTier", tier=None, credentialed=False)
# A clinical_only customer whose location HAS credentials: retrieval is Core
# scope (D-20), so its own tier gate must refuse it.
KEY_T0_CREDS, _ROW_T0_CREDS = _tenant("ClinicalOnlyCreds", tier="clinical_only", credentialed=True)
# Top tier, no credentials: passes every tier gate, so each upstream-free
# handler body really runs in the live-mode no-outbound test. A pa_live_ key,
# since a live-mode stack only resolves those (FT-13).
KEY_TOP_NOCREDS, _ROW_TOP_NOCREDS = _tenant(
    "TopNoCreds", tier=TIER_ORDER[-1], credentialed=False, env="live"
)
# Used only by the 429 test, so no other test's hits count against it.
KEY_RATE_NOCREDS, _ROW_RATE_NOCREDS = _tenant("RateNoCreds", tier="core", credentialed=False)
# Rows ck_locations_pharmapi_credentials forbids (a blank username; credentials
# with no unit id) — get_api_context must still treat both as uncredentialed.
KEY_BLANK_USER, _ROW_BLANK_USER = _tenant("BlankUser", tier="core", credentialed=True)
_ROW_BLANK_USER.location.pharmapi_username = ""
KEY_NO_UNIT, _ROW_NO_UNIT = _tenant("NoUnit", tier="core", credentialed=True)
_ROW_NO_UNIT.location.pharmapi_unit_id = None

_ROWS_BY_HASH = {
    row.key_hash: row
    for row in (
        _ROW_CORE_NOCREDS,
        _ROW_CORE_CREDS,
        _ROW_T0,
        _ROW_CLIN_NOCREDS,
        _ROW_UNSET_TIER,
        _ROW_T0_CREDS,
        _ROW_TOP_NOCREDS,
        _ROW_RATE_NOCREDS,
        _ROW_BLANK_USER,
        _ROW_NO_UNIT,
    )
}


class _FakeScalarResult:
    def __init__(self, row):
        self._row = row

    def one_or_none(self):
        return self._row


class _FakeSession:
    async def scalars(self, stmt):
        params = stmt.compile().params
        key_hash = next((v for k, v in params.items() if k.startswith("key_hash")), None)
        return _FakeScalarResult(_ROWS_BY_HASH.get(key_hash))

    async def commit(self):
        pass


async def _fake_get_session():
    yield _FakeSession()


app = create_app()
app.dependency_overrides[get_session] = _fake_get_session
client = TestClient(app, raise_server_exceptions=False)


def _h(key: str) -> dict:
    return {"X-API-Key": key}


# ── Upstream-free route seams (the routes' own DB reads) ─────────────────────


def _rules() -> list[SafetyRule]:
    return [
        SafetyRule(
            rule_code="WARFARIN_ASPIRIN_BLEED",
            check_type=CheckType.INTERACTIONS,
            trigger_atc="B01AA03",
            conflicting_atc="B01AC06",
            severity=AdrSeverity.MODERATE,
            message_en="Bleeding risk",
            details_en="d",
            recommended_action_en="review",
            active=True,
        ),
        SafetyRule(
            rule_code="WARFARIN_PREGNANCY",
            check_type=CheckType.CONTRAINDICATIONS,
            trigger_atc="B01AA03",
            trigger_condition_code="PREGNANCY",
            severity=AdrSeverity.SEVERE,
            message_en="Teratogenic risk",
            details_en="d",
            recommended_action_en="block",
            active=True,
        ),
    ]


@pytest.fixture(autouse=True)
def _upstream_free_seams(monkeypatch):
    """Stand in for the DB reads behind drugs / safety / conditions. Nothing
    here is ΗΔΥΚΑ — these are the local tables those routes legitimately use."""

    async def _rules_loader(_session):
        return _rules()

    async def _atcs(_session, _barcodes):
        return {}

    async def _conditions(_session, _location_id, _amka):
        # The engine only reads .condition_code off a condition row.
        return [SimpleNamespace(condition_code="PREGNANCY")]

    async def _no_conditions(_session, _location_id, _amka):
        return []

    async def _search(_session, **_kw):
        return {"items": [], "total": 0, "page": 0, "size": 50, "last_page": True}

    async def _alternatives(_session, **_kw):
        return {"source": None, "source_atc": "B01AA03", "alternatives": [], "data_caveats": []}

    monkeypatch.setattr(v1_safety, "load_active_safety_rules", _rules_loader)
    monkeypatch.setattr(v1_safety, "atc_codes_for_barcodes", _atcs)
    monkeypatch.setattr(v1_safety, "list_conditions", _conditions)
    monkeypatch.setattr(b2b_conditions, "list_conditions", _no_conditions)
    monkeypatch.setattr(v1_drugs, "search_catalog", _search)
    monkeypatch.setattr(v1_drugs, "formulary_alternatives", _alternatives)


_SAFETY_BODY = {
    "patient": {"amka": AMKA},
    "medications": [{"atc": "B01AA03"}, {"atc": "B01AC06"}],
}


def _assert_envelope(r, status: int, code: str) -> dict:
    assert r.status_code == status, r.text
    body = r.json()
    assert set(body) == {"error"}
    assert set(body["error"]) >= {"code", "message", "request_id"}
    assert body["error"]["code"] == code
    assert body["error"]["request_id"] == r.headers["x-request-id"]
    return body["error"]


# ── T0-1: optional credentials in the /v1 context ────────────────────────────


def test_credentialless_location_resolves_on_status_not_500():
    r = client.get("/v1/status", headers=_h(KEY_CORE_NOCREDS))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["customer"]["tier"] == "core"
    assert body["location"]["name"] == "CoreNoCreds Store"
    assert body["location"]["retrievalAvailable"] is False
    assert body["pharmapiConnected"] is False


def test_credentialed_location_status_reports_retrieval_available():
    r = client.get("/v1/status", headers=_h(KEY_CORE_CREDS))
    assert r.status_code == 200, r.text
    assert r.json()["location"]["retrievalAvailable"] is True


def test_credentialless_safety_check_runs_the_engine():
    r = client.post("/v1/safety/check", headers=_h(KEY_CORE_NOCREDS), json=_SAFETY_BODY)
    assert r.status_code == 200, r.text
    body = r.json()
    ids = {c["id"] for result in body["results"] for c in result["checks"]}
    # Drug-drug (caller-supplied co-medication) AND condition-based (conditions
    # recorded at this location) findings both fire with no ΗΔΥΚΑ at all.
    assert any("WARFARIN_ASPIRIN_BLEED" in i for i in ids), body
    assert any("WARFARIN_PREGNANCY" in i for i in ids), body
    assert body["conditionsConsidered"] == 1
    assert body["status"] == "block"


def test_credentialless_drug_search_and_alternatives():
    r = client.get("/v1/drugs?q=warfarin", headers=_h(KEY_CORE_NOCREDS))
    assert r.status_code == 200, r.text
    assert r.json()["total"] == 0
    r = client.get("/v1/drugs/3661001/alternatives", headers=_h(KEY_CORE_NOCREDS))
    assert r.status_code == 200, r.text
    assert r.json()["sourceAtc"] == "B01AA03"


def test_credentialless_conditions_crud_is_not_gated():
    # Conditions are DB-only and are how a caller feeds contraindication
    # screening into /v1/safety/check — they must work without credentials.
    r = client.get(f"/v1/patients/{AMKA}/conditions", headers=_h(KEY_CORE_NOCREDS))
    assert r.status_code == 200, r.text


def _boom(_ciphertext):
    raise AssertionError("decrypt_credential reached")


def test_credentialless_path_never_reaches_the_aes_decrypt(monkeypatch):
    monkeypatch.setattr(v1_deps, "decrypt_credential", _boom)
    assert client.get("/v1/status", headers=_h(KEY_CORE_NOCREDS)).status_code == 200
    r = client.post("/v1/safety/check", headers=_h(KEY_CORE_NOCREDS), json=_SAFETY_BODY)
    assert r.status_code == 200, r.text
    # Positive control: the same patch DOES fire on the credentialed path (→ 500),
    # so the 200s above prove the branch, not a dead monkeypatch target.
    assert client.get("/v1/status", headers=_h(KEY_CORE_CREDS)).status_code == 500


@pytest.mark.parametrize("key", [KEY_BLANK_USER, KEY_NO_UNIT], ids=["blank-username", "no-unit"])
def test_constraint_violating_credentials_resolve_as_uncredentialed(monkeypatch, key):
    # ck_locations_pharmapi_credentials forbids both rows, but get_api_context
    # must not lean on it: neither decrypts nor reaches retrieval. A unit-less
    # context would make get_pharmacy_id borrow the B2C session's pharmacy id.
    monkeypatch.setattr(v1_deps, "decrypt_credential", _boom)
    r = client.get("/v1/status", headers=_h(key))
    assert r.status_code == 200, r.text
    assert r.json()["location"]["retrievalAvailable"] is False
    _assert_envelope(
        client.get(f"/v1/patients/{AMKA}", headers=_h(key)), 409, "retrieval_unavailable"
    )


def test_credentialless_request_refreshes_last_used_at(monkeypatch):
    monkeypatch.setattr(_ROW_CORE_NOCREDS, "last_used_at", None)
    assert client.get("/v1/status", headers=_h(KEY_CORE_NOCREDS)).status_code == 200
    assert _ROW_CORE_NOCREDS.last_used_at is not None


def test_credentialless_key_is_rate_limited(monkeypatch):
    # FT-1's per-key limit runs before (and regardless of) the credential
    # branch. Tightened per test exactly as test_v1_rate_limit.py does — deps
    # reads settings per request — on a key no other test uses, and the
    # limiter is cleared afterwards so no counter outlives the test.
    tight = get_settings().model_copy(update={"v1_rate_limit": "1/minute"})
    monkeypatch.setattr(v1_deps, "get_settings", lambda: tight)
    try:
        assert client.get("/v1/status", headers=_h(KEY_RATE_NOCREDS)).status_code == 200
        r = client.get("/v1/status", headers=_h(KEY_RATE_NOCREDS))
        error = _assert_envelope(r, 429, "rate_limited")
        assert "1/minute" in error["message"]
        assert 1 <= int(r.headers["retry-after"]) <= 60
    finally:
        v1_api_key_limiter.reset()


def test_credentialless_request_is_tenant_attributed_in_access_log(caplog):
    caplog.set_level(logging.INFO, logger="v1.access")
    r = client.post("/v1/safety/check", headers=_h(KEY_CORE_NOCREDS), json=_SAFETY_BODY)
    assert r.status_code == 200, r.text
    (rec,) = [rec for rec in caplog.records if rec.name == "v1.access"]
    location = _ROW_CORE_NOCREDS.location
    assert rec.api_key_id == str(_ROW_CORE_NOCREDS.id)
    assert rec.location_id == str(location.id)
    assert rec.customer_id == str(location.customer.id)
    assert rec.status == 200


# ── T0-2: require_retrieval ──────────────────────────────────────────────────

# (method, concrete URL) for every guarded route — the mock fixtures make each
# return 200 for a credentialed tenant.
RETRIEVAL_CALLS = [
    ("GET", f"/v1/patients/{AMKA}"),
    ("GET", f"/v1/patients/{AMKA}/insurances"),
    ("GET", f"/v1/patients/{AMKA}/intolerances?patientConsent=true"),
    ("GET", f"/v1/patients/{AMKA}/medicine-history?patientConsent=true"),
    ("GET", "/v1/prescriptions?status=pending"),
    ("GET", f"/v1/prescriptions/{RX_ID}"),
]


@pytest.mark.parametrize(("method", "url"), RETRIEVAL_CALLS)
def test_credentialless_retrieval_route_is_409_envelope(method, url):
    r = client.request(method, url, headers=_h(KEY_CORE_NOCREDS))
    error = _assert_envelope(r, 409, "retrieval_unavailable")
    assert "ΗΔΥΚΑ credentials" in error["message"]
    assert AMKA not in error["message"]  # PHI rule: the envelope never echoes the patient


@pytest.mark.parametrize(("method", "url"), RETRIEVAL_CALLS)
def test_credentialed_retrieval_route_unaffected(method, url):
    r = client.request(method, url, headers=_h(KEY_CORE_CREDS))
    assert r.status_code == 200, r.text


# Exact inventory of /v1 routes behind require_retrieval. Everything else under
# /v1 is upstream-free BY AUDIT (TIER0-RETRIEVAL-FREE.md §1) and must stay
# reachable without credentials. Adding a route here is a contract change.
EXPECTED_RETRIEVAL_ROUTES = {
    ("GET", "/v1/patients/{patient_key}"),
    ("GET", "/v1/patients/{patient_key}/insurances"),
    ("GET", "/v1/patients/{patient_key}/intolerances"),
    ("GET", "/v1/patients/{patient_key}/medicine-history"),
    ("GET", "/v1/prescriptions"),
    ("GET", "/v1/prescriptions/{barcode}"),
}
EXPECTED_UPSTREAM_FREE_ROUTES = {
    ("GET", "/v1/status"),
    ("GET", "/v1/drugs"),
    ("GET", "/v1/drugs/{barcode}/alternatives"),
    ("POST", "/v1/safety/check"),
    ("POST", "/v1/safety/explain"),
    ("GET", "/v1/patients/{patient_key}/conditions"),
    ("POST", "/v1/patients/{patient_key}/conditions"),
    ("PATCH", "/v1/patients/{patient_key}/conditions/{condition_id}"),
    ("DELETE", "/v1/patients/{patient_key}/conditions/{condition_id}"),
    ("GET", "/v1/adr-reports"),
    ("POST", "/v1/adr-reports"),
    ("GET", "/v1/adr-reports/{report_id}"),
    ("POST", "/v1/adr-reports/{report_id}/transition"),
}

# Any of these in a handler body means it talks to ΗΔΥΚΑ.
_UPSTREAM_MARKERS = re.compile(r"ctx\.pharmapi\b|\bpharmapi_\w+\(")


def _depends_on(dependant, fn) -> bool:
    return any(d.call is fn or _depends_on(d, fn) for d in dependant.dependencies)


def _v1_routes() -> list[tuple[str, str, APIRoute]]:
    """Every /v1 (method, full path, APIRoute), read from the routers themselves.

    Deliberately NOT app.routes: newer FastAPI wraps included routers lazily
    (private _IncludedRouter), so the flattened APIRoutes aren't there. Each
    router's own APIRoutes are stable across versions; completeness is then
    cross-checked against the public OpenAPI path list below.
    """
    routers = (
        v1_package.router,
        v1_patients.router,
        v1_prescriptions.router,
        v1_drugs.router,
        v1_safety.router,
        v1_safety_explain.router,
        v1_adr_reports.router,
    )
    found: dict[tuple[str, str], APIRoute] = {}
    for router in routers:
        for route in router.routes:
            if not isinstance(route, APIRoute):
                continue
            path = route.path if route.path.startswith("/v1") else f"/v1{route.path}"
            for method in route.methods:
                found[(method, path)] = route
    return [(method, path, route) for (method, path), route in found.items()]


def test_route_walk_covers_the_whole_published_v1_surface():
    # A new /v1 router module must be added to _v1_routes, or the inventory
    # below would silently skip its routes.
    published = {
        (method.upper(), path)
        for path, item in app.openapi()["paths"].items()
        if path.startswith("/v1")
        for method in item
    }
    assert {(m, p) for m, p, _ in _v1_routes()} == published


def test_retrieval_guard_inventory_is_exact():
    guarded = {(m, p) for m, p, r in _v1_routes() if _depends_on(r.dependant, require_retrieval)}
    unguarded = {(m, p) for m, p, _ in _v1_routes()} - guarded
    assert guarded == EXPECTED_RETRIEVAL_ROUTES
    assert unguarded == EXPECTED_UPSTREAM_FREE_ROUTES


def test_every_route_that_calls_upstream_carries_the_guard():
    # Net 1 of the loud failure T0-2 asks for: a handler whose OWN source reads
    # ctx.pharmapi or calls a pharmapi_* service must be behind require_retrieval.
    # A source scan only — it cannot see an indirect call (a service or the
    # safety engine fetching ΗΔΥΚΑ with ctx=None, i.e. on the legacy B2C
    # credentials); the live-mode no-outbound test below is the net for that.
    # /v1/status is the one deliberate reader — it handles None itself.
    for method, path, route in _v1_routes():
        source = inspect.getsource(route.endpoint)
        if not _UPSTREAM_MARKERS.search(source):
            continue
        if (method, path) == ("GET", "/v1/status"):
            assert "ctx.pharmapi is not None" in source
            continue
        assert _depends_on(route.dependant, require_retrieval), (
            f"{method} {path} calls ΗΔΥΚΑ but is not behind require_retrieval"
        )


def test_guarded_routes_document_the_409_in_openapi():
    paths = app.openapi()["paths"]
    for method, path in EXPECTED_RETRIEVAL_ROUTES:
        responses = paths[path][method.lower()]["responses"]
        assert "409" in responses, (method, path)
        assert "retrieval_unavailable" in responses["409"]["description"]


# Exact inventory of tier-gated /v1 routes → the minimum tier each enforces.
# Retrieval is Core scope (D-20), enforced inside require_retrieval.
EXPECTED_TIER_GATES = {
    **dict.fromkeys(EXPECTED_RETRIEVAL_ROUTES, "core"),
    ("GET", "/v1/drugs/{barcode}/alternatives"): "core",
    ("POST", "/v1/safety/explain"): "clinical",
    ("GET", "/v1/adr-reports"): "clinical",
    ("POST", "/v1/adr-reports"): "clinical",
    ("GET", "/v1/adr-reports/{report_id}"): "clinical",
    ("POST", "/v1/adr-reports/{report_id}/transition"): "clinical",
}


def _tier_minimum(dependant) -> str | None:
    """The minimum tier a route's dependency tree enforces (None if ungated),
    read from the gates themselves: require_retrieval's RETRIEVAL_MIN_TIER, or
    the `minimum` a require_tier(...) closure captured."""
    for d in dependant.dependencies:
        if d.call is require_retrieval:
            return v1_deps.RETRIEVAL_MIN_TIER
        if getattr(d.call, "__qualname__", "") == "require_tier.<locals>._require_tier":
            return inspect.getclosurevars(d.call).nonlocals["minimum"]
        if (minimum := _tier_minimum(d)) is not None:
            return minimum
    return None


def test_tier_gated_routes_document_their_403_in_openapi():
    # Every gate the code enforces is in the published contract with the tier it
    # needs, and no ungated route advertises a tier_required 403 — so the spec's
    # 403 and the route's require_tier(...) can't drift apart.
    paths = app.openapi()["paths"]
    gates = {(m, p): _tier_minimum(r.dependant) for m, p, r in _v1_routes()}
    assert {k: v for k, v in gates.items() if v is not None} == EXPECTED_TIER_GATES
    for (method, path), minimum in gates.items():
        documented = paths[path][method.lower()]["responses"].get("403", {})
        if minimum is None:
            assert "tier_required" not in documented.get("description", ""), (method, path)
            continue
        assert "tier_required" in documented["description"], (method, path)
        assert f"`{minimum}`" in documented["description"], (method, path)


def test_eopyy_gated_routes_document_their_second_403_in_openapi():
    # Intolerances and medicine history also 403 with `forbidden` (609) for a
    # non-ΕΟΠΥΥ location; the spec must say so on exactly those two routes.
    paths = app.openapi()["paths"]
    eopyy_gated = {
        "/v1/patients/{patient_key}/intolerances",
        "/v1/patients/{patient_key}/medicine-history",
    }
    for _method, path in EXPECTED_RETRIEVAL_ROUTES:
        description = paths[path]["get"]["responses"]["403"]["description"]
        assert "tier_required" in description, path
        assert ("`forbidden`" in description and "609" in description) == (path in eopyy_gated), (
            path
        )


# ── T0-2: no outbound call at all from an upstream-free route (live mode) ────

# One concrete call per EXPECTED_UPSTREAM_FREE_ROUTES entry (pinned equal below).
_CONDITION_ID = uuid.UUID(int=1)
_REPORT_ID = uuid.UUID(int=2)
UPSTREAM_FREE_CALLS = {
    ("GET", "/v1/status"): ("/v1/status", None),
    ("GET", "/v1/drugs"): ("/v1/drugs?q=warfarin", None),
    ("GET", "/v1/drugs/{barcode}/alternatives"): ("/v1/drugs/3661001/alternatives", None),
    ("POST", "/v1/safety/check"): ("/v1/safety/check", _SAFETY_BODY),
    ("POST", "/v1/safety/explain"): ("/v1/safety/explain", {"ruleCodes": ["WARFARIN_PREGNANCY"]}),
    ("GET", "/v1/patients/{patient_key}/conditions"): (f"/v1/patients/{AMKA}/conditions", None),
    ("POST", "/v1/patients/{patient_key}/conditions"): (
        f"/v1/patients/{AMKA}/conditions",
        {"conditionCode": "pregnancy", "name": "Pregnancy"},
    ),
    ("PATCH", "/v1/patients/{patient_key}/conditions/{condition_id}"): (
        f"/v1/patients/{AMKA}/conditions/{_CONDITION_ID}",
        {"notes": "20w"},
    ),
    ("DELETE", "/v1/patients/{patient_key}/conditions/{condition_id}"): (
        f"/v1/patients/{AMKA}/conditions/{_CONDITION_ID}",
        None,
    ),
    ("GET", "/v1/adr-reports"): ("/v1/adr-reports", None),
    ("POST", "/v1/adr-reports"): ("/v1/adr-reports", {"symptomDescription": "rash"}),
    ("GET", "/v1/adr-reports/{report_id}"): (f"/v1/adr-reports/{_REPORT_ID}", None),
    ("POST", "/v1/adr-reports/{report_id}/transition"): (
        f"/v1/adr-reports/{_REPORT_ID}/transition",
        {},
    ),
}


@pytest.fixture
def live_outbound(monkeypatch):
    """Live mode with every outbound HTTP request recorded and refused; returns
    the record. Scoped to the test by monkeypatch.

    The legacy (B2C) ΗΔΥΚΑ session is warmed, as it is in production whenever
    a B2C pharmacist is logged in: that is the state in which a ctx=None call
    from a /v1 handler really leaves the building under the B2C pharmacy's
    credentials. Cold, the legacy path 403s inside get_pharmacy_id before any
    request exists, and the leak would go unseen.
    """
    monkeypatch.setenv("PHARMAPI_MOCK", "false")  # is_mock_pharmapi() re-reads env per call
    monkeypatch.setenv("LLM_MOCK", "true")  # the explain route's LLM seam stays canned
    legacy = pharmapi._session_store.get(pharmapi.LEGACY_SESSION_KEY)
    monkeypatch.setitem(legacy, "connected", True)
    monkeypatch.setitem(legacy, "connected_at_ts", time.time())
    monkeypatch.setitem(legacy, "pharmacy_id", 4242)

    outbound: list[str] = []

    def _refuse(_transport, request):
        outbound.append(f"{request.method} {request.url}")
        raise httpx.ConnectError("outbound HTTP blocked by test", request=request)

    async def _refuse_async(transport, request):
        _refuse(transport, request)

    # The TestClient's own transport is a bare BaseTransport, so it is unaffected.
    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", _refuse)
    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", _refuse_async)

    # The routes' remaining local-DB reads (conditions writes, the explain
    # route, ADR's live branch). As with the autouse seams above, none of it is
    # ΗΔΥΚΑ; the explain LLM call itself runs for real, uncached, on LLM_MOCK.
    async def _condition(*_args, **_kwargs):
        now = datetime.now(UTC)
        return SimpleNamespace(
            id=_CONDITION_ID,
            amka=AMKA,
            condition_code="PREGNANCY",
            name="Pregnancy",
            severity=None,
            notes=None,
            active=True,
            created_at=now,
            updated_at=now,
        )

    async def _report(*_args, **_kwargs):
        return {"id": str(_REPORT_ID), "status": "PENDING_REVIEW"}

    async def _reports(*_args, **_kwargs):
        return {"items": [], "page": 0, "size": 20, "total": 0, "totalPages": 1, "lastPage": True}

    async def _rules_by_code(_session, codes):
        return {rule.rule_code: rule for rule in _rules() if rule.rule_code in codes}

    real_explain = safety_explanations.explain_rule

    async def _explain_uncached(_session, rule, condition_codes, **kwargs):
        return await real_explain(None, rule, condition_codes, **kwargs)  # None = no DB cache

    for name in ("get_condition", "create_condition", "update_condition", "deactivate_condition"):
        monkeypatch.setattr(b2b_conditions, name, _condition)
    for name in ("create_report", "get_report", "transition_report"):
        monkeypatch.setattr(b2b_adr, name, _report)
    monkeypatch.setattr(b2b_adr, "list_reports", _reports)
    monkeypatch.setattr(safety_explanations, "load_rules_by_code", _rules_by_code)
    monkeypatch.setattr(safety_explanations, "explain_rule", _explain_uncached)
    return outbound


def test_live_mode_calls_cover_every_upstream_free_route():
    assert set(UPSTREAM_FREE_CALLS) == EXPECTED_UPSTREAM_FREE_ROUTES


@pytest.mark.parametrize(("method", "path"), sorted(EXPECTED_UPSTREAM_FREE_ROUTES))
def test_upstream_free_route_makes_no_outbound_call_in_live_mode(live_outbound, method, path):
    # Net 2: sees what the source scan can't — e.g. dropping the history_atcs /
    # intolerances seams in routers/v1/safety.py, which lets the engine fetch
    # ΗΔΥΚΑ itself under the B2C credentials (positive control below).
    url, body = UPSTREAM_FREE_CALLS[(method, path)]
    r = client.request(method, url, headers=_h(KEY_TOP_NOCREDS), json=body)
    assert 200 <= r.status_code < 300, r.text  # the handler body ran to completion
    assert live_outbound == []


def test_live_mode_harness_sees_a_legacy_credential_leak(live_outbound, monkeypatch):
    # Positive control: the regression the harness exists for. Without the two
    # seams the engine loads medicine history itself with ctx=None — the B2C
    # pharmacy's identity — for a tenant with no ΗΔΥΚΑ relationship at all.
    real = v1_safety.evaluate_safety

    async def _without_seams(*args, **kwargs):
        kwargs.pop("history_atcs", None)
        kwargs.pop("intolerances", None)
        return await real(*args, **kwargs)

    monkeypatch.setattr(v1_safety, "evaluate_safety", _without_seams)
    client.post("/v1/safety/check", headers=_h(KEY_TOP_NOCREDS), json=_SAFETY_BODY)
    assert any("/medicinehistory/" in call for call in live_outbound), live_outbound


# ── T0-3: the clinical_only entitlement matrix ───────────────────────────────


def test_clinical_only_reaches_safety_and_drug_catalogue():
    status = client.get("/v1/status", headers=_h(KEY_T0))
    assert status.status_code == 200, status.text
    assert status.json()["customer"]["tier"] == "clinical_only"
    r = client.post("/v1/safety/check", headers=_h(KEY_T0), json=_SAFETY_BODY)
    assert r.status_code == 200, r.text
    assert client.get("/v1/drugs?q=warfarin", headers=_h(KEY_T0)).status_code == 200
    # Caller-supplied conditions are part of the tier (D-20: "safety engine with
    # caller-supplied conditions").
    assert client.get(f"/v1/patients/{AMKA}/conditions", headers=_h(KEY_T0)).status_code == 200


@pytest.mark.parametrize(
    ("method", "url", "body", "minimum"),
    [
        # Formulary substitution is Core scope (D-20: "Core minus retrieval
        # minus formulary"; §5).
        ("GET", "/v1/drugs/3661001/alternatives", None, "core"),
        ("GET", "/v1/adr-reports", None, "clinical"),
        ("POST", "/v1/safety/explain", {"ruleCodes": ["WARFARIN_PREGNANCY"]}, "clinical"),
    ],
)
def test_clinical_only_refused_above_its_tier(method, url, body, minimum):
    r = client.request(method, url, headers=_h(KEY_T0), json=body)
    error = _assert_envelope(r, 403, "tier_required")
    assert f"'{minimum}'" in error["message"]


@pytest.mark.parametrize(("method", "url"), RETRIEVAL_CALLS)
def test_clinical_only_refused_retrieval_with_retrieval_unavailable(method, url):
    # No credentials: the credential check runs first, so Tier 0 sees 409 (T0-3).
    _assert_envelope(client.request(method, url, headers=_h(KEY_T0)), 409, "retrieval_unavailable")


@pytest.mark.parametrize(("method", "url"), RETRIEVAL_CALLS)
def test_credentialed_clinical_only_refused_retrieval_with_tier_required(method, url):
    # Credentials alone don't buy retrieval: it is Core scope (D-20), so a
    # clinical_only customer with a credentialed location still gets 403.
    error = _assert_envelope(
        client.request(method, url, headers=_h(KEY_T0_CREDS)), 403, "tier_required"
    )
    assert "'core'" in error["message"]
    assert AMKA not in error["message"]


def test_missing_credentials_are_orthogonal_to_tier():
    # D-20: a Clinical tenant with no credentials keeps its Tier-2 routes; only
    # retrieval answers 409.
    assert client.get("/v1/adr-reports", headers=_h(KEY_CLIN_NOCREDS)).status_code == 200
    _assert_envelope(
        client.get(f"/v1/patients/{AMKA}", headers=_h(KEY_CLIN_NOCREDS)),
        409,
        "retrieval_unavailable",
    )


def test_unset_tier_row_falls_back_to_base_tier_not_core():
    # T0-3 trap 2: an unset tier must never read as the paid `core` tier.
    r = client.get("/v1/status", headers=_h(KEY_UNSET_TIER))
    assert r.status_code == 200, r.text
    assert r.json()["customer"]["tier"] == "clinical_only"
    _assert_envelope(
        client.get("/v1/drugs/3661001/alternatives", headers=_h(KEY_UNSET_TIER)),
        403,
        "tier_required",
    )
