"""FT-6 — /v1 tenant-attributed access log + D-5 consent attestation record.

Real get_api_context (fake DB session) so the tenant stamping on
request.state is exercised end to end. Assertions read the captured
LogRecord's structured extras; the PHI test asserts the raw AMKA appears
NOWHERE in what the logger emitted — only the route template and the HMAC
patient_ref do.
"""

import base64
import logging
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
from fastapi.testclient import TestClient  # noqa: E402

from app.crypto import encrypt_credential  # noqa: E402
from app.db.models.api_key import ApiKey  # noqa: E402
from app.db.models.customer import Customer  # noqa: E402
from app.db.models.location import Location  # noqa: E402
from app.db.session import get_session  # noqa: E402
from app.observability import patient_ref  # noqa: E402
from app.services.api_keys import generate_api_key, hash_api_key  # noqa: E402
from main import create_app  # noqa: E402

AMKA = "15031962456"  # Maria Stavrou — mock fixtures incl. intolerances
RAW_KEY = generate_api_key("test")

# tier set explicitly: an unflushed ORM row has tier=None (the 'core' default is
# server-side), which get_api_context ranks as clinical_only — below retrieval.
_CUSTOMER = Customer(id=uuid.uuid4(), name="Log SA", active=True, tier="core")
_LOCATION = Location(
    id=uuid.uuid4(),
    customer_id=_CUSTOMER.id,
    name="Log Store",
    pharmapi_unit_id=70466,
    pharmapi_username=encrypt_credential("log-user"),
    pharmapi_password=encrypt_credential("log-pass"),
    is_eopyy=True,
    active=True,
)
_KEY = ApiKey(
    id=uuid.uuid4(),
    location_id=_LOCATION.id,
    key_hash=hash_api_key(RAW_KEY),
    label="test",
    active=True,
    last_used_at=None,
)
_LOCATION.customer = _CUSTOMER
_KEY.location = _LOCATION


class _FakeScalarResult:
    def __init__(self, row):
        self._row = row

    def one_or_none(self):
        return self._row


class _FakeSession:
    async def scalars(self, stmt):
        params = stmt.compile().params
        key_hash = next((v for k, v in params.items() if k.startswith("key_hash")), None)
        return _FakeScalarResult(_KEY if key_hash == _KEY.key_hash else None)

    async def commit(self):
        pass


async def _fake_get_session():
    yield _FakeSession()


app = create_app()
app.dependency_overrides[get_session] = _fake_get_session
client = TestClient(app, raise_server_exceptions=False)


def _v1_records(caplog):
    return [r for r in caplog.records if r.name == "v1.access"]


@pytest.fixture(autouse=True)
def _capture(caplog):
    caplog.set_level(logging.INFO, logger="v1.access")
    yield


def test_authenticated_request_line_carries_tenant_attribution(caplog):
    r = client.get("/v1/status", headers={"X-API-Key": RAW_KEY})
    assert r.status_code == 200, r.text
    (rec,) = _v1_records(caplog)
    assert rec.route == "/v1/status"
    assert rec.method == "GET"
    assert rec.status == 200
    assert rec.api_key_id == str(_KEY.id)
    assert rec.location_id == str(_LOCATION.id)
    assert rec.customer_id == str(_CUSTOMER.id)
    assert rec.request_id == r.headers["x-request-id"]
    assert isinstance(rec.duration_ms, float)


def test_consent_attestation_is_recorded_with_patient_pseudonym(caplog):
    r = client.get(
        f"/v1/patients/{AMKA}/intolerances?patientConsent=true",
        headers={"X-API-Key": RAW_KEY},
    )
    assert r.status_code == 200, r.text
    (rec,) = _v1_records(caplog)
    # The D-5 attestation record: who (key/location), for whom (pseudonym),
    # what (route), asserted consent, when (log timestamp).
    assert rec.patient_consent is True
    assert rec.api_key_id == str(_KEY.id)
    assert rec.patient_ref == patient_ref(AMKA)
    assert len(rec.patient_ref) == 16 and rec.patient_ref != AMKA


def test_raw_amka_never_reaches_the_log(caplog):
    client.get(f"/v1/patients/{AMKA}", headers={"X-API-Key": RAW_KEY})
    (rec,) = _v1_records(caplog)
    assert rec.route == "/v1/patients/{patient_key}"  # template, not rendered
    # The PHI rule, asserted hard: neither the formatted text nor any
    # structured field carries the identifier.
    assert AMKA not in caplog.text
    assert all(AMKA not in str(v) for v in rec.__dict__.values())


def test_consent_field_absent_when_param_not_sent(caplog):
    client.get(f"/v1/patients/{AMKA}", headers={"X-API-Key": RAW_KEY})
    (rec,) = _v1_records(caplog)
    assert not hasattr(rec, "patient_consent")
    assert hasattr(rec, "patient_ref")  # pseudonym rides every patient read


def test_unauthenticated_request_logged_without_attribution(caplog):
    r = client.get("/v1/status", headers={"X-API-Key": "pa_test_bogus"})
    assert r.status_code == 401
    (rec,) = _v1_records(caplog)
    assert rec.status == 401
    assert rec.api_key_id is None
    assert rec.location_id is None


def test_non_v1_traffic_is_not_logged(caplog):
    assert client.get("/health").status_code == 200
    assert _v1_records(caplog) == []
