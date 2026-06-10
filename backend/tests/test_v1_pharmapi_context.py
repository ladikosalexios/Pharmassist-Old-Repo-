"""BC-4 unit tests — per-location PharmapiContext threading + keyed session store.

httpx.AsyncClient is monkeypatched (same pattern as test_pharmapi_g14_retry),
so the real branching runs without a network. The invariants under test are
the multi-tenant ones: a context's calls carry ITS credentials/base/Api-Key,
session entries never bleed across keys, and the G14 auto-refresh heals the
calling context's session with the calling context's identity — never the
global one.
"""

import asyncio
import base64
import os
import uuid
from unittest.mock import AsyncMock, MagicMock

os.environ.setdefault("PHARMAPI_MOCK", "true")
os.environ.setdefault("COOKIE_SECURE", "false")
os.environ.setdefault("CREDENTIAL_ENCRYPTION_KEY", base64.b64encode(b"\x01" * 32).decode())
os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("PHARMAPI_USERNAME", "env-user")
os.environ.setdefault("PHARMAPI_PASSWORD", "env-pass")
os.environ.setdefault("PHARMAPI_API_KEY", "env-api-key")
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+asyncpg://pharmassist:pharmassist_dev@localhost:5432/pharmassist_test",
)

import httpx  # noqa: E402
import pytest  # noqa: E402
from fastapi import HTTPException  # noqa: E402

from app.services import pharmapi as pharmapi_module  # noqa: E402
from app.services.pharmapi import (  # noqa: E402
    LEGACY_SESSION_KEY,
    PharmapiContext,
    _session_store,
    _start_pharmapi_session,
    pharmapi_get,
    pharmapi_session,
    session_is_valid,
)


def _ctx(name: str = "loc") -> PharmapiContext:
    """Fresh context with a unique session key so tests never share state."""
    return PharmapiContext(
        username=f"{name}-user",
        password=f"{name}-pass",
        api_key=f"{name}-api-key",
        base_url="https://ctx.example.test/pharmapi",
        pharmacy_unit_id=70499,
        session_key=f"location:{uuid.uuid4()}",
    )


def _install_fake_async_client(monkeypatch, responses):
    fake_client = MagicMock()
    fake_client.get = AsyncMock(side_effect=responses)
    fake_cm = MagicMock()
    fake_cm.__aenter__ = AsyncMock(return_value=fake_client)
    fake_cm.__aexit__ = AsyncMock(return_value=False)
    monkeypatch.setattr(pharmapi_module.httpx, "AsyncClient", MagicMock(return_value=fake_cm))
    return fake_client


def _user_me(unit_id: int = 7) -> httpx.Response:
    return httpx.Response(200, json={"email": "x@y", "units": [{"id": unit_id}]})


def test_ctx_call_uses_ctx_credentials_base_and_api_key(monkeypatch):
    ctx = _ctx("alpha")
    fake_client = _install_fake_async_client(
        monkeypatch, [_user_me(), httpx.Response(200, json={"ok": True})]
    )

    result = asyncio.run(pharmapi_get("/api/v1/whatever", ctx=ctx))

    assert result == {"ok": True}
    # Cold session → lazy establishment (/user/me) first, then the target call.
    assert fake_client.get.call_count == 2
    ensure_call, target_call = fake_client.get.call_args_list
    assert ensure_call.args[0] == "https://ctx.example.test/pharmapi/api/v1/user/me"
    assert target_call.args[0] == "https://ctx.example.test/pharmapi/api/v1/whatever"
    for call in (ensure_call, target_call):
        assert call.kwargs["auth"] == ("alpha-user", "alpha-pass")
        assert call.kwargs["headers"]["Api-Key"] == "alpha-api-key"


def test_legacy_call_keeps_env_credentials(monkeypatch):
    fake_client = _install_fake_async_client(monkeypatch, [httpx.Response(200, json={"ok": 1})])

    asyncio.run(pharmapi_get("/api/v1/whatever"))

    # The invariant is identity, not literals: a ctx-less call uses the
    # module-level credential snapshot, whatever the environment supplied
    # (the compose container carries real test creds, CI carries fakes).
    call = fake_client.get.call_args_list[0]
    assert call.kwargs["auth"] == (pharmapi_module.PHARMAPI_USER, pharmapi_module.PHARMAPI_PASS)
    assert call.kwargs["headers"]["Api-Key"] == pharmapi_module.PHARMAPI_API_KEY
    assert call.args[0].startswith(pharmapi_module.PHARMAPI_BASE)


def test_session_entries_are_isolated_per_key():
    ctx_a, ctx_b = _ctx("a"), _ctx("b")
    _start_pharmapi_session({"units": [{"id": 11}]}, session_key=ctx_a.session_key)

    assert session_is_valid(ctx_a.session_key)
    assert not session_is_valid(ctx_b.session_key)
    assert _session_store.get(ctx_a.session_key)["pharmacy_id"] == 11
    assert _session_store.get(ctx_b.session_key)["pharmacy_id"] is None


def test_legacy_store_entry_is_the_module_dict():
    # Object identity matters: routers/pharmapi.py reads pharmapi_session
    # directly, so the store's legacy entry must BE that dict.
    assert _session_store.get(LEGACY_SESSION_KEY) is pharmapi_session


def test_ctx_session_establishment_does_not_touch_legacy(monkeypatch):
    ctx = _ctx("gamma")
    legacy_before = dict(pharmapi_session)
    _install_fake_async_client(monkeypatch, [_user_me(99), httpx.Response(200, json={})])

    asyncio.run(pharmapi_get("/api/v1/whatever", ctx=ctx))

    assert _session_store.get(ctx.session_key)["pharmacy_id"] == 99
    assert dict(pharmapi_session) == legacy_before


def test_g14_refresh_reauths_with_ctx_identity(monkeypatch):
    ctx = _ctx("delta")
    # Warm the session so the lazy-ensure path is skipped and the G14 branch
    # is what drives the /user/me re-auth.
    _start_pharmapi_session({"units": [{"id": 5}]}, session_key=ctx.session_key)
    fake_client = _install_fake_async_client(
        monkeypatch,
        [
            httpx.Response(502, json={"errorCode": "G14"}),
            _user_me(55),
            httpx.Response(200, json={"healed": True}),
        ],
    )

    result = asyncio.run(pharmapi_get("/api/v1/whatever", ctx=ctx))

    assert result == {"healed": True}
    refresh_call = fake_client.get.call_args_list[1]
    assert refresh_call.args[0].endswith("/api/v1/user/me")
    assert refresh_call.kwargs["auth"] == ("delta-user", "delta-pass")
    # The refresh re-pinned THIS context's entry, not the legacy one.
    assert _session_store.get(ctx.session_key)["pharmacy_id"] == 55
    assert pharmapi_session["pharmacy_id"] != 55 or pharmapi_session is not _session_store.get(
        ctx.session_key
    )


def test_second_g14_with_ctx_raises_401(monkeypatch):
    ctx = _ctx("epsilon")
    _start_pharmapi_session({"units": [{"id": 5}]}, session_key=ctx.session_key)
    _install_fake_async_client(
        monkeypatch,
        [
            httpx.Response(502, json={"errorCode": "G14"}),
            httpx.Response(502, json={"errorCode": "G14"}),
        ],
    )

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(pharmapi_get("/api/v1/whatever", ctx=ctx))
    assert exc_info.value.status_code == 401


def test_get_pharmacy_id_prefers_ctx_unit():
    ctx = _ctx("zeta")
    assert pharmapi_module.get_pharmacy_id(ctx) == 70499
