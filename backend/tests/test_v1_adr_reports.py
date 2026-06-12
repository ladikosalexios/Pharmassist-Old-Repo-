"""Contract + AC tests for /v1/adr-reports (T2-3).

Covers (in mock mode, DB-less via dependency override):
  - POST /v1/adr-reports → 201 + correct shape
  - GET /v1/adr-reports (each filter: amka, atc, barcode, status, from, to, pagination)
  - GET /v1/adr-reports/{id} — 200 with events key; 404 for unknown id
  - POST /v1/adr-reports/{id}/transition — full chain PENDING_REVIEW→ESCALATED→EOF_REPORTED→CLOSED
  - POST transition on CLOSED → 409 illegal_transition envelope
  - Tier gate: core key → 403 tier_required on every endpoint
  - Mock parity: same field names / shape in both the list and the detail
  - B2C side_effects suite untouched (imported and confirmed green)
  - No Tier-1 module imports b2b_adr (additive-only grep-assert)

Tests run in-process (no DB, no docker) by overriding get_api_context and get_session.
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
from pathlib import Path  # noqa: E402

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.db.session import get_session  # noqa: E402
from app.routers.v1.adr_reports import _MOCK_STORE  # noqa: E402
from app.routers.v1.deps import ApiContext, get_api_context  # noqa: E402
from app.services.pharmapi import PharmapiContext  # noqa: E402
from main import create_app  # noqa: E402


def _ctx(tier: str = "clinical") -> ApiContext:
    location_id = uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")
    return ApiContext(
        customer_id=uuid.uuid4(),
        customer_name="ADR Test SA",
        tier=tier,
        location_id=location_id,
        location_name="ADR Test Store",
        api_key_id=uuid.uuid4(),
        is_eopyy=True,
        pharmapi=PharmapiContext(
            username="u",
            password="p",
            api_key="k",
            base_url="https://unused.example.test",
            pharmacy_unit_id=70001,
            session_key=f"location:{location_id}",
        ),
    )


_CLINICAL_CTX = _ctx("clinical")
_CORE_CTX = _ctx("core")
CURRENT: dict = {"ctx": _CLINICAL_CTX}


async def _fake_get_session():
    yield None


app = create_app()
app.dependency_overrides[get_api_context] = lambda: CURRENT["ctx"]
app.dependency_overrides[get_session] = _fake_get_session
client = TestClient(app)


def _assert_envelope(resp, status: int, code: str):
    assert resp.status_code == status, resp.text
    body = resp.json()
    assert "error" in body
    assert body["error"]["code"] == code
    return body["error"]


_REQUIRED_FIELDS = {
    "id", "locationId", "symptomDescription", "status", "reportedAt", "createdAt",
}


def _assert_report_shape(report: dict) -> None:
    assert _REQUIRED_FIELDS <= set(report), f"missing fields: {_REQUIRED_FIELDS - set(report)}"
    assert report["status"] in {"PENDING_REVIEW", "ESCALATED", "EOF_REPORTED", "CLOSED"}


# ── POST create ───────────────────────────────────────────────────────────────


def test_create_adr_report_201():
    r = client.post(
        "/v1/adr-reports",
        json={
            "symptomDescription": "Rash on torso",
            "severity": "MILD",
            "causality": "Possible",
            "patientAmka": "15031962456",
            "medicineName": "Amoxicillin 500 mg",
            "atcCode": "J01CA04",
        },
    )
    assert r.status_code == 201, r.text
    body = r.json()
    _assert_report_shape(body)
    assert body["status"] == "PENDING_REVIEW"
    assert body["symptomDescription"] == "Rash on torso"
    assert body["severity"] == "MILD"
    assert body["causality"] == "Possible"
    assert body["patientAmka"] == "15031962456"
    assert body["atcCode"] == "J01CA04"


def test_create_adr_report_invalid_severity():
    r = client.post("/v1/adr-reports", json={"symptomDescription": "x", "severity": "EXTREME"})
    _assert_envelope(r, 422, "validation_failed")


def test_create_adr_report_invalid_causality():
    r = client.post(
        "/v1/adr-reports",
        json={"symptomDescription": "x", "causality": "NotAChoice"},
    )
    _assert_envelope(r, 422, "validation_failed")


def test_create_adr_report_missing_symptom():
    r = client.post("/v1/adr-reports", json={"severity": "MILD"})
    _assert_envelope(r, 422, "validation_failed")


# ── GET list — each filter ────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _seed_mock_store():
    """Seed the in-process mock store with location-scoped fixtures for each test."""
    location_id = str(_CLINICAL_CTX.location_id)
    _MOCK_STORE.clear()
    _MOCK_STORE.extend([
        {
            "id": "aaaaaaaa-0001-0001-0001-000000000001",
            "locationId": location_id,
            "patientAmka": "15031962456",
            "patientName": "Maria Stavrou",
            "rxId": None,
            "medicineBarcode": "3661001",
            "medicineName": "Warfarin 5 mg",
            "atcCode": "B01AA03",
            "symptomDescription": "Dark stools",
            "onsetTiming": "8h",
            "severity": "SEVERE",
            "causality": "Probable",
            "status": "PENDING_REVIEW",
            "eofReportRef": None,
            "reportedAt": "2026-06-01T10:00:00+00:00",
            "createdAt": "2026-06-01T10:00:00+00:00",
        },
        {
            "id": "aaaaaaaa-0001-0001-0001-000000000002",
            "locationId": location_id,
            "patientAmka": "08111947033",
            "patientName": "Nikos Papadopoulos",
            "rxId": None,
            "medicineBarcode": "3661002",
            "medicineName": "Aspirin 100 mg",
            "atcCode": "B01AC06",
            "symptomDescription": "Nosebleed",
            "onsetTiming": "48h",
            "severity": "MODERATE",
            "causality": "Possible",
            "status": "ESCALATED",
            "eofReportRef": None,
            "reportedAt": "2026-05-20T14:30:00+00:00",
            "createdAt": "2026-05-20T14:30:00+00:00",
        },
    ])
    yield
    # post-test: restore to canonical two-item fixture
    _MOCK_STORE.clear()
    _MOCK_STORE.extend([
        {
            "id": "aaaaaaaa-0001-0001-0001-000000000001",
            "locationId": location_id,
            "patientAmka": "15031962456",
            "patientName": "Maria Stavrou",
            "rxId": None,
            "medicineBarcode": "3661001",
            "medicineName": "Warfarin 5 mg",
            "atcCode": "B01AA03",
            "symptomDescription": "Dark stools",
            "onsetTiming": "8h",
            "severity": "SEVERE",
            "causality": "Probable",
            "status": "PENDING_REVIEW",
            "eofReportRef": None,
            "reportedAt": "2026-06-01T10:00:00+00:00",
            "createdAt": "2026-06-01T10:00:00+00:00",
        },
        {
            "id": "aaaaaaaa-0001-0001-0001-000000000002",
            "locationId": location_id,
            "patientAmka": "08111947033",
            "patientName": "Nikos Papadopoulos",
            "rxId": None,
            "medicineBarcode": "3661002",
            "medicineName": "Aspirin 100 mg",
            "atcCode": "B01AC06",
            "symptomDescription": "Nosebleed",
            "onsetTiming": "48h",
            "severity": "MODERATE",
            "causality": "Possible",
            "status": "ESCALATED",
            "eofReportRef": None,
            "reportedAt": "2026-05-20T14:30:00+00:00",
            "createdAt": "2026-05-20T14:30:00+00:00",
        },
    ])


def test_list_adr_reports_no_filter():
    r = client.get("/v1/adr-reports")
    assert r.status_code == 200, r.text
    body = r.json()
    assert "items" in body
    assert body["total"] == 2
    assert body["page"] == 0
    for item in body["items"]:
        _assert_report_shape(item)


def test_list_filter_amka():
    r = client.get("/v1/adr-reports?amka=15031962456")
    body = r.json()
    assert body["total"] == 1
    assert body["items"][0]["patientAmka"] == "15031962456"


def test_list_filter_atc():
    r = client.get("/v1/adr-reports?atc=B01AA03")
    body = r.json()
    assert body["total"] == 1
    assert body["items"][0]["atcCode"] == "B01AA03"


def test_list_filter_barcode():
    r = client.get("/v1/adr-reports?barcode=3661002")
    body = r.json()
    assert body["total"] == 1
    assert body["items"][0]["medicineBarcode"] == "3661002"


def test_list_filter_status():
    r = client.get("/v1/adr-reports?status=ESCALATED")
    body = r.json()
    assert body["total"] == 1
    assert body["items"][0]["status"] == "ESCALATED"


def test_list_filter_status_invalid():
    r = client.get("/v1/adr-reports?status=MADE_UP")
    _assert_envelope(r, 422, "validation_failed")


def test_list_filter_from_date():
    r = client.get("/v1/adr-reports?from=2026-06-01")
    body = r.json()
    assert body["total"] == 1
    assert body["items"][0]["reportedAt"] >= "2026-06-01"


def test_list_filter_to_date():
    r = client.get("/v1/adr-reports?to=2026-05-31")
    body = r.json()
    assert body["total"] == 1
    assert body["items"][0]["reportedAt"] <= "2026-05-31T23:59:59"


def test_list_pagination_envelope():
    r = client.get("/v1/adr-reports?page=0&size=1")
    body = r.json()
    assert body["size"] == 1
    assert len(body["items"]) == 1
    assert body["totalPages"] == 2
    assert body["lastPage"] is False


def test_list_pagination_second_page():
    r = client.get("/v1/adr-reports?page=1&size=1")
    body = r.json()
    assert len(body["items"]) == 1
    assert body["lastPage"] is True


# ── GET by id ─────────────────────────────────────────────────────────────────


def test_get_adr_report_200():
    r = client.get("/v1/adr-reports/aaaaaaaa-0001-0001-0001-000000000001")
    assert r.status_code == 200, r.text
    body = r.json()
    _assert_report_shape(body)
    assert "events" in body  # detail includes events
    assert body["id"] == "aaaaaaaa-0001-0001-0001-000000000001"


def test_get_adr_report_404():
    r = client.get(f"/v1/adr-reports/{uuid.uuid4()}")
    _assert_envelope(r, 404, "not_found")


# ── POST transition — state machine ──────────────────────────────────────────


def test_transition_pending_to_escalated():
    r = client.post(
        "/v1/adr-reports/aaaaaaaa-0001-0001-0001-000000000001/transition",
        json={},
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "ESCALATED"


def test_transition_escalated_to_eof_reported():
    r = client.post(
        "/v1/adr-reports/aaaaaaaa-0001-0001-0001-000000000002/transition",
        json={"notes": "escalating"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "EOF_REPORTED"


def test_transition_full_chain_to_closed():
    """Drive PENDING_REVIEW → ESCALATED → EOF_REPORTED → CLOSED in sequence."""
    # item 1 is PENDING_REVIEW after seed
    rid = "aaaaaaaa-0001-0001-0001-000000000001"
    statuses = ["ESCALATED", "EOF_REPORTED", "CLOSED"]
    for expected in statuses:
        r = client.post(f"/v1/adr-reports/{rid}/transition", json={})
        assert r.status_code == 200, r.text
        assert r.json()["status"] == expected, f"expected {expected}, got {r.json()['status']}"


def test_transition_from_closed_is_409():
    """Transition from CLOSED returns 409 illegal_transition."""
    rid = "aaaaaaaa-0001-0001-0001-000000000001"
    # Drive to CLOSED first
    for _ in range(3):
        client.post(f"/v1/adr-reports/{rid}/transition", json={})
    r = client.post(f"/v1/adr-reports/{rid}/transition", json={})
    _assert_envelope(r, 409, "illegal_transition")


def test_transition_unknown_report_404():
    r = client.post(f"/v1/adr-reports/{uuid.uuid4()}/transition", json={})
    _assert_envelope(r, 404, "not_found")


# ── Tier gate ─────────────────────────────────────────────────────────────────


@pytest.fixture
def core_client():
    """Temporarily use a core-tier context."""
    original = CURRENT["ctx"]
    CURRENT["ctx"] = _CORE_CTX
    yield client
    CURRENT["ctx"] = original


def test_create_gated_for_core(core_client):
    r = core_client.post("/v1/adr-reports", json={"symptomDescription": "x"})
    _assert_envelope(r, 403, "tier_required")


def test_list_gated_for_core(core_client):
    r = core_client.get("/v1/adr-reports")
    _assert_envelope(r, 403, "tier_required")


def test_get_gated_for_core(core_client):
    r = core_client.get("/v1/adr-reports/aaaaaaaa-0001-0001-0001-000000000001")
    _assert_envelope(r, 403, "tier_required")


def test_transition_gated_for_core(core_client):
    r = core_client.post(
        "/v1/adr-reports/aaaaaaaa-0001-0001-0001-000000000001/transition", json={}
    )
    _assert_envelope(r, 403, "tier_required")


# ── Tenant isolation (mock mode) ──────────────────────────────────────────────


def test_tenant_cannot_read_other_tenant_report():
    """A report created by clinical_ctx is invisible to a different location_id."""
    other_ctx = ApiContext(
        customer_id=uuid.uuid4(),
        customer_name="Other SA",
        tier="clinical",
        location_id=uuid.UUID("dddddddd-dddd-dddd-dddd-dddddddddddd"),  # different location
        location_name="Other Store",
        api_key_id=uuid.uuid4(),
        is_eopyy=True,
        pharmapi=PharmapiContext(
            username="u",
            password="p",
            api_key="k",
            base_url="https://unused.example.test",
            pharmacy_unit_id=70002,
            session_key="location:dddddddd-dddd-dddd-dddd-dddddddddddd",
        ),
    )

    original = CURRENT["ctx"]
    CURRENT["ctx"] = other_ctx
    try:
        # Trying to GET a report that belongs to _CLINICAL_CTX's location
        r = client.get("/v1/adr-reports/aaaaaaaa-0001-0001-0001-000000000001")
        _assert_envelope(r, 404, "not_found")
        # List returns 0 items (no reports for other location)
        r2 = client.get("/v1/adr-reports")
        assert r2.json()["total"] == 0
        # Transition returns 404
        r3 = client.post(
            "/v1/adr-reports/aaaaaaaa-0001-0001-0001-000000000001/transition", json={}
        )
        _assert_envelope(r3, 404, "not_found")
    finally:
        CURRENT["ctx"] = original


# ── Mock parity ───────────────────────────────────────────────────────────────


def test_mock_list_and_detail_same_field_names():
    """List items and GET detail must expose identical field names (parity)."""
    list_item = client.get("/v1/adr-reports").json()["items"][0]
    detail = client.get(f"/v1/adr-reports/{list_item['id']}").json()
    # Detail has an extra 'events' key — everything else must match
    list_keys = set(list_item.keys())
    detail_keys = set(detail.keys()) - {"events"}
    assert list_keys == detail_keys, f"parity gap: {list_keys.symmetric_difference(detail_keys)}"


def test_create_response_shape_matches_list_shape():
    r = client.post(
        "/v1/adr-reports",
        json={"symptomDescription": "Rash", "severity": "MILD"},
    )
    assert r.status_code == 201
    created = r.json()
    list_item = client.get("/v1/adr-reports").json()["items"][0]
    list_keys = set(list_item.keys())
    created_keys = set(created.keys())
    assert list_keys == created_keys, f"parity gap: {list_keys.symmetric_difference(created_keys)}"


# ── B2C side_effects suite untouched ─────────────────────────────────────────


def test_b2c_side_effects_module_imports_cleanly():
    """B2C side_effects router must remain importable — we never touched it."""
    import importlib

    mod = importlib.import_module("app.routers.side_effects")
    assert hasattr(mod, "router")


# ── Additive-only: no Tier-1 module imports the new seam ─────────────────────


_SEAM_FILES = {"services/b2b_adr.py", "db/models/b2b_adr_report.py", "db/models/b2b_adr_event.py"}

_TIER1_MODULES = [
    "routers/prescriptions.py",
    "routers/side_effects.py",
    "routers/documentation.py",
    "routers/safety_checks.py",
    "routers/patients.py",
    "routers/auth.py",
    "services/safety_engine.py",
    "services/pharmapi.py",
    "services/side_effects.py",
]

_IMPORT_PATTERNS = ["b2b_adr", "B2bAdrReport", "B2bAdrEvent"]


def test_no_tier1_module_imports_b2b_adr():
    """Tier-1 deterministic modules must not import the new B2B ADR seam."""
    app_root = Path(__file__).parent.parent / "app"
    violations: list[str] = []
    for rel in _TIER1_MODULES:
        path = app_root / rel
        if not path.exists():
            continue
        text = path.read_text()
        for pattern in _IMPORT_PATTERNS:
            if pattern in text:
                violations.append(f"{rel}: found '{pattern}'")
    assert not violations, f"Tier-1 modules import the B2B ADR seam: {violations}"
