"""Tests for the spc_extract LLM kind (services/spc_extract.py)."""

import asyncio
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

import pytest  # noqa: E402
from pydantic import ValidationError  # noqa: E402

from app.services import llm  # noqa: E402
from app.services.spc_extract import KIND_SPC_EXTRACT, _mask_codes, enrich  # noqa: E402

EAN_SECTION = (
    "Δοσολογία: 500 mg δύο φορές ημερησίως. "
    "Συσκευασία με barcode 2802910304012 και παρτίδα LOT-2024A-001."
)


def test_mask_codes_strips_barcode_and_lot():
    masked = _mask_codes(EAN_SECTION)
    assert "2802910304012" not in masked
    assert "LOT-2024A-001" not in masked
    assert "‹κωδικός›" in masked
    assert "500 mg" in masked  # short numbers survive


def test_builder_output_passes_pii_scrub_with_ean_text():
    # The seam's build_prompt runs assert_no_pii over every message — a raw
    # 13-digit EAN would raise PiiBoundaryError; the builder's masking must
    # make document text pass by construction.
    fields = llm.ClinicalPromptInput(document_text=[EAN_SECTION])
    built = llm.build_prompt(KIND_SPC_EXTRACT, fields)
    assert any("‹κωδικός›" in m["content"] for m in built.messages)


def test_mock_is_deterministic():
    fields = llm.ClinicalPromptInput(document_text=["a", "b"])
    one = llm._MOCKS[KIND_SPC_EXTRACT](fields)
    two = llm._MOCKS[KIND_SPC_EXTRACT](fields)
    assert one == two
    assert one["recommendedDosage"].startswith("[MOCK]")


def test_enrich_returns_none_under_llm_mock():
    # LLM_MOCK=true — enrichment must short-circuit so [MOCK] text can never
    # be persisted into a document's parsed payload.
    assert asyncio.run(enrich(None, [EAN_SECTION])) is None


def test_enrich_returns_none_for_empty_sections(monkeypatch):
    monkeypatch.setenv("LLM_MOCK", "false")
    assert asyncio.run(enrich(None, ["", "   "])) is None


def test_enrich_live_invalid_shape_returns_none(monkeypatch):
    monkeypatch.setenv("LLM_MOCK", "false")

    async def bad_chat(messages):  # noqa: ARG001
        return {"totally": "wrong", "contraindications": "not-a-list"}

    monkeypatch.setattr(llm, "_chat", bad_chat)
    assert asyncio.run(enrich(None, [EAN_SECTION])) is None


def test_enrich_live_valid_shape_roundtrips(monkeypatch):
    monkeypatch.setenv("LLM_MOCK", "false")

    async def good_chat(messages):  # noqa: ARG001
        return {
            "recommendedDosage": "500 mg δύο φορές ημερησίως",
            "contraindications": ["Υπερευαισθησία"],
            "precautions": ["Νεφρική παρακολούθηση"],
            "majorInteractions": [{"drug": "Βαρφαρίνη", "effect": "Αυξημένη αιμορραγία"}],
            "storage": {"conditions": "< 25 °C", "afterOpening": None, "disposal": None},
            "foodInstructions": "Με τροφή",
        }

    monkeypatch.setattr(llm, "_chat", good_chat)
    payload = asyncio.run(enrich(None, [EAN_SECTION]))
    assert payload["majorInteractions"] == [{"drug": "Βαρφαρίνη", "effect": "Αυξημένη αιμορραγία"}]
    assert payload["foodInstructions"] == "Με τροφή"


def test_enrich_live_provider_down_returns_none(monkeypatch):
    monkeypatch.setenv("LLM_MOCK", "false")

    async def down(messages):  # noqa: ARG001
        raise llm.AiUnavailableError("boom")

    monkeypatch.setattr(llm, "_chat", down)
    assert asyncio.run(enrich(None, [EAN_SECTION])) is None


@pytest.mark.parametrize("bad", [{"amka": "x"}, {"documenttext": []}])
def test_prompt_input_whitelist_still_forbids_extras(bad):
    with pytest.raises(ValidationError):
        llm.ClinicalPromptInput(document_text=[], **bad)
