"""Tests for the G14 (session expired) auto-refresh path in pharmapi_get.

Verifies the in-band retry logic without hitting a real Pharmapi:
- A single G14 → call /user/me to refresh → re-issue original call.
- A second G14 (from the refresh itself or the retry) → 401 to caller.

httpx.AsyncClient is monkeypatched so calls return a canned sequence of
httpx.Response objects. PHARMAPI_MOCK does not need to be false here:
once we patch the HTTP layer, pharmapi_get runs its real branching
regardless of mock mode.
"""

import asyncio
import base64
import os
from unittest.mock import AsyncMock, MagicMock

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

import httpx  # noqa: E402
import pytest  # noqa: E402
from fastapi import HTTPException  # noqa: E402

from app.services import pharmapi as pharmapi_module  # noqa: E402
from app.services.pharmapi import pharmapi_get  # noqa: E402


def _g14() -> httpx.Response:
    return httpx.Response(502, json={"errorCode": "G14"})


def _install_fake_async_client(monkeypatch, responses):
    """Patch httpx.AsyncClient so .get() returns `responses` in order."""
    fake_client = MagicMock()
    fake_client.get = AsyncMock(side_effect=responses)
    fake_cm = MagicMock()
    fake_cm.__aenter__ = AsyncMock(return_value=fake_client)
    fake_cm.__aexit__ = AsyncMock(return_value=False)
    monkeypatch.setattr(pharmapi_module.httpx, "AsyncClient", MagicMock(return_value=fake_cm))
    return fake_client


def test_g14_triggers_one_refresh_then_retries_original(monkeypatch):
    target_ok = httpx.Response(200, json={"ok": True, "n": 42})
    user_me_ok = httpx.Response(200, json={"email": "x@y", "units": [{"id": 7}]})
    fake_client = _install_fake_async_client(monkeypatch, [_g14(), user_me_ok, target_ok])

    result = asyncio.run(pharmapi_get("/api/v1/whatever"))

    assert result == {"ok": True, "n": 42}
    assert fake_client.get.call_count == 3
    urls = [call.args[0] for call in fake_client.get.call_args_list]
    assert urls[0].endswith("/api/v1/whatever")
    assert urls[1].endswith("/api/v1/user/me")
    assert urls[2].endswith("/api/v1/whatever")


def test_second_g14_raises_401_without_recursing(monkeypatch):
    fake_client = _install_fake_async_client(monkeypatch, [_g14(), _g14()])

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(pharmapi_get("/api/v1/whatever"))

    assert exc_info.value.status_code == 401
    assert "re-login" in exc_info.value.detail.lower()
    # Original (G14) + refresh attempt (also G14). No third call — _retrying=True
    # short-circuits the second G14 straight to 401.
    assert fake_client.get.call_count == 2


def test_refresh_network_failure_raises_401(monkeypatch):
    fake_client = _install_fake_async_client(monkeypatch, [_g14(), httpx.ConnectError("boom")])

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(pharmapi_get("/api/v1/whatever"))

    assert exc_info.value.status_code == 401
    assert fake_client.get.call_count == 2
