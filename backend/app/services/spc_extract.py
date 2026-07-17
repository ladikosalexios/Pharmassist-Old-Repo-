"""LLM cleanup/extraction for SPC sections (kind ``spc_extract``).

The deterministic splitter (services/spc_parse.py) is the extraction core;
this module only *upgrades* its output when a live LLM is configured:
normalising messy section text into clean SpcDetails fields and extracting
the structured ``majorInteractions`` pairs the deterministic pass never
attempts. On mock mode, provider failure, or an invalid response shape,
callers keep the deterministic payload — enrichment can only add, never lose.

PII containment: SPC/ΦΟΧ text legitimately contains code-shaped tokens
(13-digit EANs, batch/lot identifiers) that the seam's PII scrub would flag.
The builder here masks every token matching the seam's three PII regexes with
``‹κωδικός›`` BEFORE message assembly, so ``assert_no_pii`` passes by
construction. The cache key still hashes the ORIGINAL input (masking happens
inside the builder, after ``cache_input()`` is derived by the seam). No
patient data ever enters this path — the input is regulatory document text.
"""

import logging

from pydantic import BaseModel, ConfigDict, ValidationError

from . import llm
from .llm import _AMKA_RE, _EKAA_RE, _NUMERIC_EHIC_RE

logger = logging.getLogger(__name__)

KIND_SPC_EXTRACT = "spc_extract"

# Per-section input cap: 4 target sections ≈ 24k chars total — one call, no
# multi-call chunking in Phase 1. Truncation is marked so the model knows.
_MAX_SECTION_CHARS = 6_000

# Order matters and is part of the prompt contract (see _build_messages).
_SECTION_LABELS = (
    "POSOLOGY (SPC 4.2 / PIL 3)",
    "CONTRAINDICATIONS (SPC 4.3)",
    "SPECIAL WARNINGS AND PRECAUTIONS (SPC 4.4)",
    "INTERACTIONS (SPC 4.5)",
    "STORAGE (SPC 6.3 / 6.4 / 6.6 / PIL 5)",
)


def _mask_codes(text: str) -> str:
    """Mask every PII-shaped token (per the seam's own regexes) in document
    text. Barcodes/batch numbers carry no extraction value — the model works
    from the surrounding clinical language."""
    for pattern in (_AMKA_RE, _NUMERIC_EHIC_RE, _EKAA_RE):
        text = pattern.sub("‹κωδικός›", text)
    return text


def _truncate(text: str) -> str:
    if len(text) <= _MAX_SECTION_CHARS:
        return text
    return text[:_MAX_SECTION_CHARS] + " …[περικοπή]"


class _Storage(BaseModel):
    model_config = ConfigDict(extra="ignore")
    conditions: str | None = None
    afterOpening: str | None = None
    disposal: str | None = None


class _Interaction(BaseModel):
    model_config = ConfigDict(extra="ignore")
    drug: str
    effect: str


class SpcExtractPayload(BaseModel):
    """Validated shape of the model's JSON reply — anything else is discarded."""

    model_config = ConfigDict(extra="ignore")
    recommendedDosage: str | None = None
    contraindications: list[str] = []
    precautions: list[str] = []
    majorInteractions: list[_Interaction] = []
    storage: _Storage | None = None
    foodInstructions: str | None = None


def _build_messages(fields: llm.ClinicalPromptInput) -> list[dict]:
    labeled = []
    for i, section in enumerate(fields.document_text):
        label = _SECTION_LABELS[i] if i < len(_SECTION_LABELS) else f"SECTION {i + 1}"
        labeled.append(f"## {label}\n{_truncate(_mask_codes(section))}")
    body = "\n\n".join(labeled) or "(no sections provided)"
    return [
        {
            "role": "system",
            "content": (
                "You are extracting structured fields from official Greek medicine "
                "documents (SPC/ΠΧΠ and patient leaflet/ΦΟΧ sections). The text contains "
                "NO patient data; identifier-shaped codes are masked as ‹κωδικός›. Keep "
                "the source language (Greek stays Greek). Use ONLY the provided text — "
                "never invent drugs, doses, or advice. Respond as a JSON object with "
                "exactly these keys: "
                '{"recommendedDosage": "<usual dosage summary or null>", '
                '"contraindications": ["<one contraindication per item>"], '
                '"precautions": ["<one warning/precaution per item>"], '
                '"majorInteractions": [{"drug": "<interacting drug/class>", "effect": "<clinical effect and management>"}], '
                '"storage": {"conditions": "<storage conditions or null>", "afterOpening": "<in-use shelf life or null>", "disposal": "<disposal guidance or null>"}, '
                '"foodInstructions": "<food/intake guidance or null>"}. '
                "Use null for anything the text does not state."
            ),
        },
        {"role": "user", "content": body},
    ]


def _mock_extract(fields: llm.ClinicalPromptInput) -> dict:
    """Deterministic mock for seam tests ONLY — callers never persist it
    (enrich() short-circuits to None under LLM_MOCK before completing)."""
    n = len(fields.document_text)
    return {
        "recommendedDosage": f"[MOCK] dosage from {n} sections",
        "contraindications": ["[MOCK] contraindication"],
        "precautions": ["[MOCK] precaution"],
        "majorInteractions": [{"drug": "[MOCK]", "effect": "[MOCK]"}],
        "storage": {"conditions": "[MOCK]", "afterOpening": None, "disposal": None},
        "foodInstructions": None,
    }


llm.register_prompt_kind(KIND_SPC_EXTRACT, builder=_build_messages, mock=_mock_extract)


async def enrich(session, sections: list[str]) -> dict | None:
    """LLM-normalised SpcDetails fields from deterministic sections.

    Returns None — meaning "keep the deterministic payload" — when the LLM is
    mocked, unavailable, or replies with an invalid shape. Never raises.
    """
    if llm.is_mock_llm():
        return None
    if not any(s.strip() for s in sections):
        return None
    try:
        result = await llm.complete(
            KIND_SPC_EXTRACT,
            llm.ClinicalPromptInput(document_text=sections),
            cache_session=session,
        )
        payload = SpcExtractPayload.model_validate(result.payload)
    except (llm.AiUnavailableError, ValidationError) as exc:
        logger.warning("spc_extract: enrichment skipped — %s", type(exc).__name__)
        return None
    return payload.model_dump()
