"""FT-15 — PHARMAPI_MOCK is boot-validated, fail-fast on an unrecognized token.

The fail-live guarantee (is_mock_pharmapi_explicit, unset ⇒ LIVE) only covered
the *unset* case; both helpers treat any unrecognized value as mock=true, so a
typo like PHARMAPI_MOCK=flase silently routes dispense/verify/masterdata to MOCK
on a live box — the exact regression 3fcf012/FT-5 exist to prevent. These tests
pin: (1) the validator rejects junk and accepts every recognized token; (2) the
validation actually RUNS at settings-load / create_app() — not lazily at first
request; (3) FT-5's asymmetric unset defaults are untouched (covered by
tests/test_mock_flag_defaults.py — re-asserted here at the boot boundary).
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

import pytest  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.utils.environment import (  # noqa: E402
    RECOGNIZED_MOCK_TOKENS,
    validate_pharmapi_mock_token,
)

# ── Unit: the validator ──────────────────────────────────────────────────────


@pytest.mark.parametrize("token", ["true", "TRUE", "false", "False", "1", "0", "yes", "no", " no "])
def test_recognized_tokens_pass(monkeypatch, token):
    monkeypatch.setenv("PHARMAPI_MOCK", token)
    validate_pharmapi_mock_token()  # no raise


def test_unset_is_legal(monkeypatch):
    monkeypatch.delenv("PHARMAPI_MOCK", raising=False)
    validate_pharmapi_mock_token()  # no raise — helpers apply their own defaults


@pytest.mark.parametrize("bad", ["flase", "falsetto", "maybe", "", "truee", "off", "on"])
def test_unrecognized_token_raises(monkeypatch, bad):
    monkeypatch.setenv("PHARMAPI_MOCK", bad)
    with pytest.raises(RuntimeError, match="PHARMAPI_MOCK"):
        validate_pharmapi_mock_token()


def test_recognized_set_is_the_helper_token_set():
    # The validator and the helpers must agree on the legal tokens; if a future
    # change widens one it must widen the other.
    assert RECOGNIZED_MOCK_TOKENS == frozenset({"true", "1", "yes", "false", "0", "no"})


# ── Boot integration: validation runs at settings-load, not at first request ──


def test_get_settings_validates_at_boot(monkeypatch):
    """A bad flag must break the boot path (create_app() → get_settings())."""
    monkeypatch.setenv("PHARMAPI_MOCK", "flase")
    get_settings.cache_clear()
    try:
        with pytest.raises(RuntimeError, match="PHARMAPI_MOCK"):
            get_settings()
    finally:
        get_settings.cache_clear()  # don't leak the poisoned cache to other tests
