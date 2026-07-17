"""Tests for the SPC fetch jobs (services/spc_ingest.py job layer)."""

import base64
import os
from datetime import timedelta

os.environ.setdefault("ENV", "test")
os.environ.setdefault("PHARMAPI_MOCK", "true")
os.environ.setdefault("LLM_MOCK", "true")
os.environ.setdefault("COOKIE_SECURE", "false")
os.environ.setdefault("CREDENTIAL_ENCRYPTION_KEY", base64.b64encode(b"\x01" * 32).decode())
os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("PHARMAPI_USERNAME", "u")
os.environ.setdefault("PHARMAPI_PASSWORD", "p")
os.environ.setdefault("PHARMAPI_API_KEY", "k")

import pytest  # noqa: E402

from app.services import spc_ingest  # noqa: E402
from app.services.spc_ingest import (  # noqa: E402
    _enabled_sources,
    fire_spc_fetch_for_meds,
    next_attempt_delay,
)


@pytest.mark.parametrize(
    ("attempts", "hours"),
    [(0, 0), (1, 1), (2, 6), (3, 24), (4, 72), (5, 168), (9, 168)],
)
def test_backoff_schedule(attempts, hours):
    assert next_attempt_delay(attempts) == timedelta(hours=hours)


def test_enabled_sources_default_off():
    # Fetch flags default False — no source enabled unless opted in.
    assert _enabled_sources() == []


def test_enabled_sources_follow_flags(monkeypatch):
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "spc_fetch_eof_enabled", True, raising=False)
    monkeypatch.setattr(get_settings(), "spc_fetch_ema_enabled", True, raising=False)
    assert _enabled_sources() == ["eof", "ema"]


def test_fire_hook_noops_when_disabled():
    # No adapters enabled → no task creation, no in-flight tracking, no error
    # even outside an event loop (asyncio.create_task would raise here if the
    # guard failed).
    fire_spc_fetch_for_meds([{"nhrn": "2801234567890", "atcCode": "N05AH03"}])
    assert spc_ingest._in_flight == set()


def test_fire_hook_noops_on_empty_meds(monkeypatch):
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "spc_fetch_eof_enabled", True, raising=False)
    fire_spc_fetch_for_meds([])
    fire_spc_fetch_for_meds(None)
    assert spc_ingest._in_flight == set()
