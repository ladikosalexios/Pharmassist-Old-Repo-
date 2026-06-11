"""T2-2 — LLM_MOCK is boot-validated, fail-fast on an unrecognized token.

Mirrors the FT-15 PHARMAPI_MOCK discipline (tests/test_config_pharmapi_mock.py):
is_mock_llm() treats any unrecognized value as mock=true, so a typo like
LLM_MOCK=flase would silently serve canned AI outputs on a box meant to call the
live provider. These pin: (1) the validator rejects junk and accepts every
recognized token; (2) the validation actually RUNS at settings-load /
create_app() — not lazily at first request.
"""

import base64
import os

os.environ.setdefault("ENV", "test")
os.environ.setdefault("PHARMAPI_MOCK", "true")
os.environ.setdefault("LLM_MOCK", "true")
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
from app.utils.environment import validate_llm_mock_token  # noqa: E402


@pytest.mark.parametrize("token", ["true", "TRUE", "false", "False", "1", "0", "yes", "no", " no "])
def test_recognized_tokens_pass(monkeypatch, token):
    monkeypatch.setenv("LLM_MOCK", token)
    validate_llm_mock_token()  # no raise


def test_unset_is_legal(monkeypatch):
    monkeypatch.delenv("LLM_MOCK", raising=False)
    validate_llm_mock_token()  # no raise — is_mock_llm() defaults to mock


@pytest.mark.parametrize("bad", ["flase", "falsetto", "maybe", "", "truee", "off", "on"])
def test_unrecognized_token_raises(monkeypatch, bad):
    monkeypatch.setenv("LLM_MOCK", bad)
    with pytest.raises(RuntimeError, match="LLM_MOCK"):
        validate_llm_mock_token()


def test_get_settings_validates_at_boot(monkeypatch):
    """A bad LLM_MOCK must break the boot path (create_app() → get_settings())."""
    monkeypatch.setenv("LLM_MOCK", "flase")
    get_settings.cache_clear()
    try:
        with pytest.raises(RuntimeError, match="LLM_MOCK"):
            get_settings()
    finally:
        get_settings.cache_clear()  # don't leak the poisoned cache to other tests
