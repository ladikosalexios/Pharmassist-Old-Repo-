"""DB-less unit tests for the T2-2 AI response-cache primitive.

cache_key is pure; stage_cached just constructs a row and calls session.add(), so
a fake session exercises it without Postgres (same pattern as
test_b2b_admin_audit_unit.py). The full miss→store→hit round-trip against a real
DB lives in test_ai_cache_db.py (compose-only).
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

from app.services import ai_cache  # noqa: E402


class _FakeSession:
    def __init__(self):
        self.added = []

    def add(self, obj):
        self.added.append(obj)


def test_cache_key_is_deterministic():
    a = ai_cache.cache_key("clinical_summary", {"atc_codes": ["B01AA03"]})
    b = ai_cache.cache_key("clinical_summary", {"atc_codes": ["B01AA03"]})
    assert a == b


def test_cache_key_invariant_to_dict_order():
    a = ai_cache.cache_key("k", {"atc_codes": ["X"], "condition_codes": ["Y"]})
    b = ai_cache.cache_key("k", {"condition_codes": ["Y"], "atc_codes": ["X"]})
    assert a == b


def test_cache_key_changes_with_kind_and_input():
    base = ai_cache.cache_key("k", {"atc_codes": ["B01AA03"]})
    assert ai_cache.cache_key("other", {"atc_codes": ["B01AA03"]}) != base
    assert ai_cache.cache_key("k", {"atc_codes": ["J01CA04"]}) != base


def test_cache_key_is_sha256_hex():
    key = ai_cache.cache_key("k", {"a": 1})
    assert len(key) == 64 and all(c in "0123456789abcdef" for c in key)


def test_stage_cached_stages_a_correct_row():
    s = _FakeSession()
    row = ai_cache.stage_cached(
        s, key="abc123", prompt_kind="clinical_summary", payload={"summary": "ναι"}, model="mock"
    )
    assert s.added == [row]  # staged, not committed here
    assert row.cache_key == "abc123"
    assert row.prompt_kind == "clinical_summary"
    assert row.payload == {"summary": "ναι"}
    assert row.model == "mock"
