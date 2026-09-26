"""DB-less tests for b2b_admin create-location argument handling (T0-4).

TIER0-RETRIEVAL-FREE.md T0-4: a location can be provisioned with no ΗΔΥΚΑ
credentials, but only EXPLICITLY (--no-retrieval). Every refusal below exits
before the CLI opens a DB session, so these run in CI without Postgres; the
DB round-trip (row + audit) lives in test_b2b_admin_audit.py.
"""

import base64
import os

os.environ.setdefault("ENV", "test")
os.environ.setdefault("CREDENTIAL_ENCRYPTION_KEY", base64.b64encode(b"\x01" * 32).decode())
os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("PHARMAPI_USERNAME", "u")
os.environ.setdefault("PHARMAPI_PASSWORD", "p")
os.environ.setdefault("PHARMAPI_API_KEY", "k")
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+asyncpg://pharmassist:pharmassist_dev@localhost:5432/pharmassist_test",
)

import asyncio  # noqa: E402
import uuid  # noqa: E402

import pytest  # noqa: E402

from app.services import b2b_admin_audit as audit  # noqa: E402
from scripts import b2b_admin  # noqa: E402

CUSTOMER_ID = str(uuid.uuid4())
SECRET_PW = "cli-secret-pw-DO-NOT-ECHO"


def _parse(*extra: str):
    return b2b_admin._build_parser().parse_args(
        ["create-location", "--customer-id", CUSTOMER_ID, "--name", "Store", *extra]
    )


@pytest.fixture(autouse=True)
def _no_db(monkeypatch):
    """Any path that reaches a DB session is a test failure here."""

    def _refuse(*_a, **_kw):
        raise AssertionError("create-location opened a DB session before validating its args")

    monkeypatch.setattr(b2b_admin, "AsyncSessionLocal", _refuse)


def test_parser_accepts_no_retrieval_without_hdyka_flags():
    args = _parse("--no-retrieval")
    assert args.no_retrieval is True
    assert args.pharmapi_unit_id is None
    assert args.pharmapi_username is None


def test_parser_defaults_to_credentialed():
    args = _parse("--pharmapi-unit-id", "70466", "--pharmapi-username", "chain12")
    assert args.no_retrieval is False
    assert args.pharmapi_unit_id == 70466


@pytest.mark.parametrize(
    ("extra", "named"),
    [
        (("--pharmapi-unit-id", "70466"), "--pharmapi-unit-id"),
        (("--pharmapi-username", "chain12"), "--pharmapi-username"),
        (("--pharmapi-password", SECRET_PW), "--pharmapi-password"),
        (("--eopyy",), "--eopyy"),
        (("--verify",), "--verify"),
    ],
)
def test_no_retrieval_refuses_any_hdyka_flag(extra, named):
    with pytest.raises(SystemExit) as exc:
        asyncio.run(b2b_admin.create_location(_parse("--no-retrieval", *extra)))
    message = str(exc.value)
    assert named in message
    assert "WITHOUT ΗΔΥΚΑ credentials" in message
    assert SECRET_PW not in message  # names the flag, never echoes a credential


@pytest.mark.parametrize(
    "extra",
    [
        (),  # nothing at all — forgetting flags must not yield an uncredentialed row
        ("--pharmapi-username", "chain12"),  # no unit id
        ("--pharmapi-unit-id", "70466"),  # no username
    ],
)
def test_credentialed_path_still_requires_unit_id_and_username(extra):
    with pytest.raises(SystemExit) as exc:
        asyncio.run(b2b_admin.create_location(_parse(*extra)))
    assert "--no-retrieval" in str(exc.value)  # points at the explicit alternative


def test_no_retrieval_create_has_its_own_audit_verb():
    assert audit.ACTION_CREATE_LOCATION_NO_RETRIEVAL == "CREATE_LOCATION_NO_RETRIEVAL"
    assert audit.ACTION_CREATE_LOCATION_NO_RETRIEVAL in audit.ALL_ACTIONS
    assert audit.ACTION_CREATE_LOCATION_NO_RETRIEVAL != audit.ACTION_CREATE_LOCATION


def test_clinical_only_is_a_valid_customer_tier_choice():
    args = b2b_admin._build_parser().parse_args(
        ["create-customer", "--name", "T0 SA", "--tier", "clinical_only"]
    )
    assert args.tier == "clinical_only"
    # The default stays core: onboarding onto the base tier is always explicit.
    assert b2b_admin._build_parser().parse_args(["create-customer", "--name", "X"]).tier == "core"
