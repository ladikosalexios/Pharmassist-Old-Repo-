"""Boot-time validator for HMVS_IDENTITY_URL — the no-/identity-suffix caveat.

services/hmvs.py assembles ``{HMVS_IDENTITY_URL}/identity/connect/token``, so
setting the env var to ``https://api-ite.nmvo.eu/identity`` (which matches the
NMVO Postman env's symmetric naming) would produce a double-/identity path
that 404s every token mint. _validate_hmvs_identity_url catches that at boot.
"""

import base64
import os

# Same env-bootstrap pattern as tests/test_hmvs.py: defaults must be in place
# BEFORE app.config is first imported, since get_settings() is lru_cached and
# other modules snapshot settings at import time.
os.environ.setdefault("HMVS_MOCK", "true")
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


@pytest.fixture(autouse=True)
def _reset_settings_cache():
    """get_settings is lru_cached — clear between tests so each picks up its
    own monkeypatched env vars instead of the first test's cached value."""
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_identity_url_with_trailing_identity_aborts_in_live_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HMVS_MOCK", "false")
    monkeypatch.setenv("HMVS_IDENTITY_URL", "https://api-ite.nmvo.eu/identity")

    with pytest.raises(RuntimeError, match="no-/identity-suffix"):
        get_settings()


def test_identity_url_with_full_token_path_aborts(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HMVS_MOCK", "false")
    monkeypatch.setenv("HMVS_IDENTITY_URL", "https://api-ite.nmvo.eu/identity/connect/token")

    with pytest.raises(RuntimeError, match="no-/identity-suffix"):
        get_settings()


def test_trailing_identity_with_slash_is_caught(monkeypatch: pytest.MonkeyPatch) -> None:
    # rstrip("/") inside the validator means a trailing slash on the wrong
    # suffix must NOT mask the foot-gun.
    monkeypatch.setenv("HMVS_MOCK", "false")
    monkeypatch.setenv("HMVS_IDENTITY_URL", "https://api-ite.nmvo.eu/identity/")

    with pytest.raises(RuntimeError, match="no-/identity-suffix"):
        get_settings()


def test_correct_identity_url_passes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HMVS_MOCK", "false")
    monkeypatch.setenv("HMVS_IDENTITY_URL", "https://api-ite.nmvo.eu")
    monkeypatch.setenv("HMVS_CLIENT_ID", "id")
    monkeypatch.setenv("HMVS_CLIENT_SECRET", "secret")

    settings = get_settings()
    assert settings.hmvs_identity_url == "https://api-ite.nmvo.eu"
    assert settings.hmvs_mock is False


def test_validator_skipped_in_mock_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    # Mock mode never builds the token URL, so a misconfigured identity URL
    # must not block dev/test boots.
    monkeypatch.setenv("HMVS_MOCK", "true")
    monkeypatch.setenv("HMVS_IDENTITY_URL", "https://api-ite.nmvo.eu/identity")

    settings = get_settings()
    assert settings.hmvs_mock is True
