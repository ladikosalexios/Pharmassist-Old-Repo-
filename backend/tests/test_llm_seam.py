"""T2-2 LLM seam — DB-less unit + app-level tests (CI-runnable, mock mode).

Covers the ticket's ACs: the PII boundary (structural + the digit-token scrub),
mock determinism per prompt kind, the timeout/5xx → ai_unavailable path, and the
ai_unavailable envelope an AI endpoint surfaces. The no-Tier-1-import grep is its
own file (test_no_tier1_llm_import.py).

httpx is monkeypatched (same fake-AsyncClient pattern as
test_v1_pharmapi_context.py) so the live path runs with no network. The live
tests flip LLM_MOCK off and clear the settings cache, then restore — llm.py reads
get_settings() at call time (never snapshots it at import), so a cache_clear is
enough.
"""

import base64
import contextlib
import os
from unittest.mock import AsyncMock, MagicMock

os.environ.setdefault("ENV", "test")
os.environ.setdefault("LLM_MOCK", "true")
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

import asyncio  # noqa: E402

import httpx  # noqa: E402
import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from pydantic import ValidationError  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.services import llm as llm_module  # noqa: E402
from app.services.llm import (  # noqa: E402
    KIND_CLINICAL_SUMMARY,
    AiUnavailableError,
    ClinicalPromptInput,
    PiiBoundaryError,
    assert_no_pii,
    build_prompt,
    complete,
    embed,
    registered_kinds,
)
from main import create_app  # noqa: E402

AMKA_TOKEN = "12345678901"  # 11 digits — AMKA-shaped


@contextlib.contextmanager
def _live_llm_env():
    """Flip the seam to the live path with throwaway provider config, then
    restore mock mode + the settings cache so later tests are unaffected."""
    saved = {k: os.environ.get(k) for k in ("LLM_MOCK", "LLM_API_KEY", "LLM_API_BASE", "LLM_MODEL")}
    os.environ["LLM_MOCK"] = "false"
    os.environ["LLM_API_KEY"] = "test-key"
    os.environ["LLM_API_BASE"] = "https://api.mistral.test"
    os.environ["LLM_MODEL"] = "mistral-test"
    get_settings.cache_clear()
    try:
        yield
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        get_settings.cache_clear()



def _install_fake_post(monkeypatch, *, side_effect=None, return_value=None):
    fake_client = MagicMock()
    fake_client.post = AsyncMock(side_effect=side_effect, return_value=return_value)
    fake_cm = MagicMock()
    fake_cm.__aenter__ = AsyncMock(return_value=fake_client)
    fake_cm.__aexit__ = AsyncMock(return_value=False)
    monkeypatch.setattr(llm_module.httpx, "AsyncClient", MagicMock(return_value=fake_cm))
    return fake_client


# ── PII boundary: structural (no identity field can even exist) ────────────────


def test_input_schema_has_no_identity_fields():
    forbidden = {
        "amka",
        "name",
        "address",
        "patient_name",
        "patient_amka",
        "first_name",
        "last_name",
    }
    assert set(ClinicalPromptInput.model_fields) & forbidden == set()


def test_input_schema_forbids_extra_fields():
    # extra="forbid" — an attempt to smuggle identity in is rejected at construction.
    with pytest.raises(ValidationError):
        ClinicalPromptInput(atc_codes=["B01AA03"], amka=AMKA_TOKEN)


# ── PII boundary: the digit-token scrub ────────────────────────────────────────


def test_scrub_passes_clean_clinical_text():
    assert_no_pii("rash and fever after B01AA03; condition RENAL_SEVERE")  # no raise


def test_scrub_flags_amka_shaped_token():
    with pytest.raises(PiiBoundaryError):
        assert_no_pii(f"patient {AMKA_TOKEN} reports a rash")


def test_scrub_flags_ekaa_shaped_token():
    # 20-char alphanumeric EHIC
    with pytest.raises(PiiBoundaryError):
        assert_no_pii("patient DE801234567890123456 reports a rash")
    # 11-char alphanumeric EKAA-shaped
    with pytest.raises(PiiBoundaryError):
        assert_no_pii("patient G1-A2B3C4D5 reports a rash")


def test_scrub_flags_numeric_ehic_token():
    # 20-digit Swiss EHIC
    with pytest.raises(PiiBoundaryError):
        assert_no_pii("patient 80756015000123456789 reports a rash")


def test_scrub_numeric_ehic_boundary():
    # A 13-digit numeric run matches _NUMERIC_EHIC_RE (12-20 digits).
    with pytest.raises(PiiBoundaryError):
        assert_no_pii("barcode 2801234567890")
    # A 10-digit code is not AMKA (11) and not numeric EHIC (12-20).
    assert_no_pii("code 0123456789")  # no raise


def test_scrub_ignores_long_clinical_terms():
    # ATC codes (7 chars) and long clinical terms (no digits) should pass.
    assert_no_pii("rash after B01AA03; condition ACETYLSALICYLIC intolerance")
    # Boundary checks:
    assert_no_pii("A" * 9)  # 9 chars — pass
    assert_no_pii("A" * 23)  # 23 chars — pass


def test_build_prompt_refuses_ekaa_in_free_text():
    # symptom_text is caller free text — the scrub is what guards it.
    fields = ClinicalPromptInput(symptom_text="onset noted, card DE801234567890123456")
    with pytest.raises(PiiBoundaryError):
        build_prompt(KIND_CLINICAL_SUMMARY, fields)


def test_embed_refuses_ekaa_token():
    with pytest.raises(PiiBoundaryError):
        asyncio.run(embed(["some text DE801234567890123456"]))


def test_build_prompt_refuses_amka_in_free_text():
    # symptom_text is caller free text — the scrub is what guards it.
    fields = ClinicalPromptInput(symptom_text=f"onset noted, AMKA {AMKA_TOKEN}")
    with pytest.raises(PiiBoundaryError):
        build_prompt(KIND_CLINICAL_SUMMARY, fields)


def test_embed_refuses_amka_token():
    with pytest.raises(PiiBoundaryError):
        asyncio.run(embed([f"some text {AMKA_TOKEN}"]))


# ── Mock determinism (per prompt kind, zero upstream calls) ────────────────────


def test_reference_kind_is_registered():
    assert KIND_CLINICAL_SUMMARY in registered_kinds()


def test_mock_complete_is_deterministic():
    fields = ClinicalPromptInput(atc_codes=["B01AA03"], condition_codes=["PREGNANCY"])
    r1 = asyncio.run(complete(KIND_CLINICAL_SUMMARY, fields))
    r2 = asyncio.run(complete(KIND_CLINICAL_SUMMARY, fields))
    assert r1.payload == r2.payload  # byte-identical canned output
    assert r1.model == "mock"
    assert r1.cached is False  # no session → uncached path
    assert r1.payload["language"] == "el"


def test_mock_output_varies_with_input():
    a = asyncio.run(complete(KIND_CLINICAL_SUMMARY, ClinicalPromptInput(atc_codes=["B01AA03"])))
    b = asyncio.run(complete(KIND_CLINICAL_SUMMARY, ClinicalPromptInput(atc_codes=["J01CA04"])))
    assert a.payload != b.payload


def test_mock_embed_is_deterministic():
    v1 = asyncio.run(embed(["σύνοψη φαρμάκου"]))
    v2 = asyncio.run(embed(["σύνοψη φαρμάκου"]))
    assert v1 == v2
    assert len(v1) == 1 and len(v1[0]) == 8


def test_unknown_prompt_kind_raises():
    with pytest.raises(ValueError):
        build_prompt("no_such_kind", ClinicalPromptInput())


# ── Failure semantics: timeout / 5xx → AiUnavailableError ──────────────────────


def test_timeout_raises_ai_unavailable(monkeypatch):
    with _live_llm_env():
        _install_fake_post(monkeypatch, side_effect=httpx.TimeoutException("timed out"))
        with pytest.raises(AiUnavailableError):
            asyncio.run(complete(KIND_CLINICAL_SUMMARY, ClinicalPromptInput(atc_codes=["B01AA03"])))


def test_5xx_raises_ai_unavailable(monkeypatch):
    with _live_llm_env():
        _install_fake_post(monkeypatch, return_value=httpx.Response(503, json={"error": "down"}))
        with pytest.raises(AiUnavailableError):
            asyncio.run(complete(KIND_CLINICAL_SUMMARY, ClinicalPromptInput(atc_codes=["B01AA03"])))


def test_missing_config_on_live_path_raises(monkeypatch):
    # No LLM_API_KEY on the live path → first-use config error (not a boot failure).
    saved = os.environ.get("LLM_MOCK")
    os.environ["LLM_MOCK"] = "false"
    os.environ.pop("LLM_API_KEY", None)
    get_settings.cache_clear()
    try:
        with pytest.raises(RuntimeError):
            asyncio.run(complete(KIND_CLINICAL_SUMMARY, ClinicalPromptInput(atc_codes=["B01AA03"])))
    finally:
        if saved is None:
            os.environ.pop("LLM_MOCK", None)
        else:
            os.environ["LLM_MOCK"] = saved
        get_settings.cache_clear()


# ── App-level envelope: an AI endpoint failure renders ai_unavailable (503) ────

_app = create_app()


@_app.get("/v1/_probe/ai_down")
async def _probe_ai_down():
    raise AiUnavailableError("provider down")


_client = TestClient(_app, raise_server_exceptions=False)


def test_ai_unavailable_renders_envelope():
    r = _client.get("/v1/_probe/ai_down")
    assert r.status_code == 503, r.text
    body = r.json()
    assert set(body) == {"error"}
    assert body["error"]["code"] == "ai_unavailable"
    assert set(body["error"]) == {"code", "message", "request_id"}
    # PHI rule: the generic message never echoes provider internals or identity.
    assert "unavailable" in body["error"]["message"].lower()
