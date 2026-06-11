"""Unit tests for the b2b_admin audit helper (DB-less, CI-runnable).

resolve_actor + add_admin_audit are pure/staging-only — add_admin_audit just
constructs a row and calls session.add(), so a fake session with a sync add()
exercises it end to end without Postgres.
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

import uuid  # noqa: E402

from app.services.b2b_admin_audit import (  # noqa: E402
    ACTION_SET_TIER,
    TARGET_CUSTOMER,
    add_admin_audit,
    resolve_actor,
)


class _FakeSession:
    def __init__(self):
        self.added = []

    def add(self, obj):
        self.added.append(obj)


def test_resolve_actor_prefers_explicit():
    assert resolve_actor("rekas") == "rekas"


def test_resolve_actor_defaults_to_os_user():
    actor = resolve_actor(None)
    assert isinstance(actor, str) and actor  # the OS user, never empty


def test_add_admin_audit_stages_a_correct_row():
    s = _FakeSession()
    cid = uuid.uuid4()
    row = add_admin_audit(
        s,
        actor="rekas",
        action=ACTION_SET_TIER,
        target_type=TARGET_CUSTOMER,
        target_id=cid,
        details={"tier": {"from": "core", "to": "clinical"}},
    )
    assert s.added == [row]  # staged on the caller's session, not committed here
    assert row.actor == "rekas"
    assert row.action == "SET_TIER"
    assert row.target_type == "CUSTOMER"
    assert row.target_id == str(cid)  # UUID stringified for the text column
    assert row.details["tier"]["to"] == "clinical"


def test_add_admin_audit_null_target_stays_null():
    s = _FakeSession()
    row = add_admin_audit(s, actor="x", action="X")
    assert row.target_id is None
    assert row.target_type is None
    assert row.details is None
