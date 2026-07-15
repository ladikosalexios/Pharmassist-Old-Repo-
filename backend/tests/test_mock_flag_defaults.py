"""FT-5 — the two PHARMAPI_MOCK helpers and their opposite unset-defaults.

The collapse of the three inline reads onto utils/environment MUST NOT flip
the fail-live default (the 3fcf012 bug). These tests pin both helpers'
env-unset behaviour and prove the safety-critical paths (credential verify,
masterdata) go LIVE when the flag is missing.
"""

import asyncio
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

import app.services.pharmapi as pharmapi  # noqa: E402
from app.utils.environment import is_mock_pharmapi, is_mock_pharmapi_explicit  # noqa: E402

# ── Helper-level defaults: the load-bearing asymmetry ────────────────────────


def test_unset_env_defaults_diverge_by_design(monkeypatch):
    monkeypatch.delenv("PHARMAPI_MOCK", raising=False)
    assert is_mock_pharmapi() is True  # read-only surfaces: dev-friendly mock
    assert is_mock_pharmapi_explicit() is False  # safety-critical: FAIL-LIVE


@pytest.mark.parametrize("value", ["true", "TRUE", "1", "yes"])
def test_explicit_true_means_mock_for_both(monkeypatch, value):
    monkeypatch.setenv("PHARMAPI_MOCK", value)
    assert is_mock_pharmapi() is True
    assert is_mock_pharmapi_explicit() is True


@pytest.mark.parametrize("value", ["false", "FALSE", "0", "no"])
def test_explicit_false_means_live_for_both(monkeypatch, value):
    monkeypatch.setenv("PHARMAPI_MOCK", value)
    assert is_mock_pharmapi() is False
    assert is_mock_pharmapi_explicit() is False


# ── Call-site regression: verify + masterdata go LIVE when env is unset ─────


def test_credential_verify_unset_env_takes_live_path(monkeypatch):
    monkeypatch.delenv("PHARMAPI_MOCK", raising=False)
    calls = []

    async def fake_upstream(username, password):
        calls.append((username, password))
        return {"email": "live@upstream"}

    monkeypatch.setattr(pharmapi, "verify_pharmapi_credentials", fake_upstream)
    result = asyncio.run(pharmapi.verify_pharmapi_credentials_with_decrypted("u1", "p1"))
    assert calls == [("u1", "p1")]  # upstream WAS called — live path
    assert result == {"email": "live@upstream"}


def test_credential_verify_explicit_mock_skips_upstream(monkeypatch):
    monkeypatch.setenv("PHARMAPI_MOCK", "true")

    async def must_not_be_called(username, password):  # pragma: no cover
        raise AssertionError("upstream called despite explicit mock")

    monkeypatch.setattr(pharmapi, "verify_pharmapi_credentials", must_not_be_called)
    result = asyncio.run(pharmapi.verify_pharmapi_credentials_with_decrypted("u1", "p1"))
    assert result["email"] == "u1@pharmapi.local"  # mock profile


def test_masterdata_unset_env_takes_live_path(monkeypatch):
    monkeypatch.delenv("PHARMAPI_MOCK", raising=False)
    calls = []

    async def fake_get(path, accept_xml=False, params=None, _retrying=False, ctx=None):
        calls.append((path, params))
        return {"contents": [{"barcode": "1"}], "lastPage": True}

    monkeypatch.setattr(pharmapi, "pharmapi_get", fake_get)
    result = asyncio.run(pharmapi.pharmapi_get_masterdata_medicines(page=0, size=10))
    assert calls and calls[0][0] == "/api/v1/masterdata/medicines"  # live path
    assert result["contents"]


def test_masterdata_explicit_mock_returns_empty_without_upstream(monkeypatch):
    monkeypatch.setenv("PHARMAPI_MOCK", "true")

    async def must_not_be_called(*a, **kw):  # pragma: no cover
        raise AssertionError("upstream called despite explicit mock")

    monkeypatch.setattr(pharmapi, "pharmapi_get", must_not_be_called)
    result = asyncio.run(pharmapi.pharmapi_get_masterdata_medicines())
    assert result == {"contents": [], "lastPage": True}
