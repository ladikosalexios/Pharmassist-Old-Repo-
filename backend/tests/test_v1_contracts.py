"""Contract tests for the /v1 Core surface (mock mode, DB-less).

get_api_context is dependency-overridden with a synthetic ApiContext, so
these pin the partner-facing contract: response field names (camelCase),
the error envelope shape on every failure class, the consent and ΕΟΠΥΥ
gates, and the no-silent-degrade rule on dispensed searches. Mock parity is
the point — PHARMAPI_MOCK=true must serve the same shapes live mode does.
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

from fastapi.testclient import TestClient  # noqa: E402

from app.db.session import get_session  # noqa: E402
from app.routers.v1.deps import ApiContext, get_api_context  # noqa: E402
from app.services.pharmapi import PharmapiContext  # noqa: E402
from main import create_app  # noqa: E402

AMKA = "15031962456"
EKAA = "DE801234567890123456"


def _ctx(is_eopyy: bool = True) -> ApiContext:
    location_id = uuid.uuid4()
    return ApiContext(
        customer_id=uuid.uuid4(),
        customer_name="Contract SA",
        location_id=location_id,
        location_name="Contract Store",
        api_key_id=uuid.uuid4(),
        is_eopyy=is_eopyy,
        pharmapi=PharmapiContext(
            username="cu",
            password="cp",
            api_key="ck",
            base_url="https://unused.example.test",
            pharmacy_unit_id=70466,
            session_key=f"location:{location_id}",
        ),
    )


# Mutable holder so individual tests can swap the eopyy flag without
# rebuilding the app.
CURRENT = {"ctx": _ctx(is_eopyy=True)}


async def _fake_get_session():
    yield None  # mock-mode endpoints under test never touch the DB


app = create_app()
app.dependency_overrides[get_api_context] = lambda: CURRENT["ctx"]
app.dependency_overrides[get_session] = _fake_get_session
client = TestClient(app)


def _assert_envelope(response, status: int, code: str):
    assert response.status_code == status, response.text
    body = response.json()
    assert set(body) == {"error"}
    assert set(body["error"]) >= {"code", "message", "request_id"}
    assert body["error"]["code"] == code
    assert body["error"]["request_id"] == response.headers["x-request-id"]
    return body["error"]


# ── Patients ─────────────────────────────────────────────────────────────────


def test_patient_lookup_by_amka_camelcase_contract():
    r = client.get(f"/v1/patients/{AMKA}")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["amka"] == AMKA
    assert {"firstName", "lastName", "dateOfBirth", "age", "sex"} <= set(body)
    assert "first_name" not in body  # camelCase on the wire


def test_patient_lookup_by_ekaa():
    r = client.get(f"/v1/patients/{EKAA}")
    assert r.status_code == 200, r.text
    assert r.json()["ekaa"] == EKAA
    assert r.json()["amka"] is None


def test_patient_key_validation_envelope():
    _assert_envelope(client.get("/v1/patients/not%20a%20key!"), 422, "validation_failed")


def test_unknown_patient_404_envelope():
    _assert_envelope(client.get("/v1/patients/99999999999"), 404, "not_found")


def test_insurances_shape():
    r = client.get(f"/v1/patients/{AMKA}/insurances")
    assert r.status_code == 200, r.text
    items = r.json()
    assert items and items[0]["socialInsurance"]["shortName"] == "ΕΟΠΥΥ"
    assert "lastActive" in items[0]


def test_intolerances_require_consent():
    err = _assert_envelope(client.get(f"/v1/patients/{AMKA}/intolerances"), 422, "consent_required")
    assert "consent" in err["message"].lower()


def test_intolerances_with_consent():
    r = client.get(f"/v1/patients/{AMKA}/intolerances?patientConsent=true")
    assert r.status_code == 200, r.text
    assert r.json()[0]["activeSubstance"] == "AMOXICILLIN"


def test_intolerances_blocked_for_non_eopyy_location():
    CURRENT["ctx"] = _ctx(is_eopyy=False)
    try:
        err = _assert_envelope(
            client.get(f"/v1/patients/{AMKA}/intolerances?patientConsent=true"),
            403,
            "forbidden",
        )
        assert "609" in err["message"]
    finally:
        CURRENT["ctx"] = _ctx(is_eopyy=True)


def test_medicine_history_envelope_shape():
    r = client.get(f"/v1/patients/{AMKA}/medicine-history?patientConsent=true")
    assert r.status_code == 200, r.text
    body = r.json()
    assert {"items", "page", "totalPages", "lastPage", "totalEntries", "blocked"} == set(body)
    assert body["blocked"] is False
    assert body["items"][0]["drugName"]


def test_medicine_history_requires_consent():
    _assert_envelope(client.get(f"/v1/patients/{AMKA}/medicine-history"), 422, "consent_required")


# ── Prescriptions ────────────────────────────────────────────────────────────


def test_prescription_search_pending():
    r = client.get("/v1/prescriptions?status=pending")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["count"] == len(body["items"]) > 0
    item = body["items"][0]
    assert {"rxId", "patientAmka", "medication", "medicineBarcode", "status"} <= set(item)
    assert all(i["status"] == "PENDING" for i in body["items"])


def test_dispensed_search_requires_amka():
    err = _assert_envelope(
        client.get("/v1/prescriptions?status=dispensed"), 422, "validation_failed"
    )
    assert "606" in err["message"]


def test_dispensed_search_with_amka():
    r = client.get(f"/v1/prescriptions?status=dispensed&amka={AMKA}")
    assert r.status_code == 200, r.text
    assert all(i["patientAmka"] == AMKA for i in r.json()["items"])


def test_prescription_detail_and_404():
    r = client.get("/v1/prescriptions/1262602210000100")
    assert r.status_code == 200 and r.json()["rxId"] == "1262602210000100"
    _assert_envelope(client.get("/v1/prescriptions/0000000000000000"), 404, "not_found")


# ── Cross-cutting ────────────────────────────────────────────────────────────


def test_request_id_header_present_on_success():
    r = client.get("/v1/status")
    assert r.status_code == 200
    assert r.headers["x-request-id"]


def test_validation_error_uses_envelope_not_fastapi_detail():
    r = client.get("/v1/prescriptions?status=bogus")
    assert r.status_code == 422
    body = r.json()
    assert "detail" not in body
    assert body["error"]["code"] == "validation_failed"
