"""Tier-2 LLM integration seam (T2-2) — the single, provider-agnostic async
client every AI feature builds on, and the hard PII boundary around it.

Design (D-15: Mistral EU, STANDARD plan, no ZDR):

* **Provider-agnostic, Mistral-targeted.** ``_chat`` speaks the OpenAI-compatible
  chat-completions shape Mistral exposes (POST {base}/v1/chat/completions); the
  base/model/key are config, so a provider swap is a config + small-edit change,
  not a rewrite. Conventions mirror ``services/pharmapi.py`` (httpx.AsyncClient
  per call, short bounded log lines, never log the body).

* **Config checked at FIRST USE, never at boot.** A Tier-1-only deployment must
  boot with no AI config at all — so ``LLM_API_*`` are optional settings and
  ``_require_llm_config`` only fires on the live path (mock skips it), exactly
  like ``crypto.CREDENTIAL_ENCRYPTION_KEY``.

* **LLM_MOCK (default true), boot-validated.** Like ``PHARMAPI_MOCK`` (FT-15):
  the token is validated fail-fast in ``config.get_settings`` so a typo can't
  silently serve canned text on a live box. In mock mode every prompt kind has a
  deterministic canned output → contract tests, mock parity, and the FT-13
  sandbox story all run with zero upstream calls.

* **HARD PII BOUNDARY.** Prompts are only ever assembled from
  :class:`ClinicalPromptInput`, whose schema admits *only* whitelisted clinical
  fields (ATC codes, English rule text, condition codes, symptom text,
  anonymised age/sex bands) and ``extra="forbid"`` — there is structurally no
  AMKA/name/address field to populate. As belt-and-braces, :func:`build_prompt`
  scans the fully-assembled prompt for AMKA-shaped (11-digit) tokens and refuses
  to dispatch if it finds one. Caveat carried to T2-12: pharmacist-entered free
  text (``symptom_text``) can embed identifiers — the scrub runs over it, and the
  DPA annex must state it is relayed as caller-supplied content.

* **Failure → ai_unavailable.** Any upstream timeout / transport error / non-200
  raises :class:`AiUnavailableError`, which ``routers/v1/errors.py`` envelopes as
  the stable ``ai_unavailable`` (503) code — on AI endpoints only. Deterministic
  endpoints (safety check, formulary, ADR CRUD) never import this module: the
  guard is ``tests/test_no_tier1_llm_import.py``.

Adding a feature's prompt kind (T2-5/6/7/9/10): call
:func:`register_prompt_kind` at import with a ``builder`` (ClinicalPromptInput →
chat messages) and a ``mock`` (ClinicalPromptInput → deterministic output dict).
``clinical_summary`` below is the reference kind that exercises every whitelisted
field and backs the seam's own tests.
"""

import hashlib
import json
import logging
import re
from collections.abc import Callable
from dataclasses import dataclass, field

import httpx
from pydantic import BaseModel, ConfigDict
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.services import ai_cache
from app.utils.environment import is_mock_llm

logger = logging.getLogger(__name__)


# ── Errors ───────────────────────────────────────────────────────────────────


class PiiBoundaryError(ValueError):
    """A prompt would carry patient identity (an AMKA-shaped token) — refused
    before dispatch. This is a data/programming error: identity must never reach
    the seam (the typed fields prevent the structured paths; this catches free
    text). The message deliberately never echoes the offending token."""


class AiUnavailableError(Exception):
    """The LLM provider failed (timeout / transport error / non-200). Enveloped
    as the ``ai_unavailable`` 503 code by routers/v1/errors.py. Carries no
    upstream body — provider internals must not leak to an API partner."""


# ── PII boundary ───────────────────────────────────────────────────────────────

# AMKA is exactly 11 digits. Match a standalone 11-digit run only: a 13-digit
# medicine barcode or a 10-digit code won't trip it, but a bare AMKA will. ATC
# and condition codes are alphanumeric, so they're never affected.
_AMKA_RE = re.compile(r"(?<!\d)\d{11}(?!\d)")

# EKAA (European Health Insurance Card) is alphanumeric, typically 10-20 chars.
# We match 10-22 chars that have at least one letter and one digit to avoid
# purely numeric AMKA/barcodes and purely alphabetic clinical terms.
_EKAA_RE = re.compile(
    r"(?<![A-Za-z0-9-])(?=[A-Za-z0-9-]*[A-Za-z])(?=[A-Za-z0-9-]*\d)[A-Za-z0-9-]{10,22}(?![A-Za-z0-9-])"
)


def assert_no_pii(text: str) -> None:
    """Raise :class:`PiiBoundaryError` if ``text`` contains an AMKA or
    EKAA-shaped token.

    The authoritative guard, run by :func:`build_prompt` over every assembled
    prompt string before it can be sent or hashed."""
    if _AMKA_RE.search(text) or _EKAA_RE.search(text):
        raise PiiBoundaryError(
            "Refusing to dispatch a prompt containing a PII-shaped (AMKA/EKAA) "
            "token — patient identity must never cross the LLM boundary (T2-2)."
        )


# ── Typed prompt input — the structural whitelist ──────────────────────────────


class ClinicalPromptInput(BaseModel):
    """The ONLY shape a prompt is ever built from. Every field is a whitelisted,
    non-identifying clinical datum; ``extra="forbid"`` rejects any attempt to
    smuggle an off-whitelist field (e.g. ``amka=...``) at construction. There is
    structurally no field for a name, address, or AMKA.

    ``symptom_text`` and ``question`` are caller-supplied free text — the digit-
    token scrub in :func:`build_prompt` is what guards them (and only them) for
    embedded identifiers; the DPA annex (T2-12) documents this relay."""

    model_config = ConfigDict(extra="forbid")

    atc_codes: list[str] = []  # e.g. ["B01AA03", "J01CA04"]
    rule_text: list[str] = []  # English safety-rule message/details/action lines
    condition_codes: list[str] = []  # e.g. ["PREGNANCY", "RENAL_SEVERE"]
    symptom_text: str | None = None  # caller free text (ADR) — scrubbed
    question: str | None = None  # caller free text (SPC Q&A) — scrubbed
    age_band: str | None = None  # anonymised, e.g. "65-74"
    sex_band: str | None = None  # anonymised, e.g. "F"

    def cache_input(self) -> dict:
        """Canonical dict for the cache key — only the populated fields, so two
        logically-identical requests hash the same regardless of default noise."""
        return self.model_dump(exclude_none=True, exclude_defaults=True)


@dataclass(frozen=True)
class BuiltPrompt:
    kind: str
    messages: list[dict] = field(default_factory=list)
    cache_input: dict = field(default_factory=dict)


@dataclass(frozen=True)
class LlmResult:
    """What :func:`complete` returns. ``payload`` is the model's structured
    output; ``cached`` lets a caller surface a cache hit (T2-6's ``cached`` flag);
    ``model`` is the producer ("mock" or the configured model id)."""

    payload: dict
    cached: bool
    model: str | None


# ── Prompt-kind registry ────────────────────────────────────────────────────────

_Builder = Callable[[ClinicalPromptInput], list[dict]]
_Mock = Callable[[ClinicalPromptInput], dict]

_BUILDERS: dict[str, _Builder] = {}
_MOCKS: dict[str, _Mock] = {}


def register_prompt_kind(kind: str, *, builder: _Builder, mock: _Mock) -> None:
    """Register a feature's prompt kind. Called at import by each AI feature
    module (T2-5/6/7/9/10) so the seam stays feature-agnostic. ``builder`` maps
    the whitelisted input to chat messages; ``mock`` maps it to a deterministic
    canned output used when ``LLM_MOCK`` is on."""
    _BUILDERS[kind] = builder
    _MOCKS[kind] = mock


def registered_kinds() -> frozenset[str]:
    return frozenset(_BUILDERS)


def build_prompt(kind: str, fields: ClinicalPromptInput) -> BuiltPrompt:
    """Assemble the chat messages for ``kind`` and run the PII scrub over every
    assembled string before the prompt can be dispatched or cached."""
    builder = _BUILDERS.get(kind)
    if builder is None:
        raise ValueError(f"Unknown prompt kind {kind!r} — register it via register_prompt_kind()")
    messages = builder(fields)
    for message in messages:
        assert_no_pii(str(message.get("content", "")))
    return BuiltPrompt(kind=kind, messages=messages, cache_input=fields.cache_input())


# ── Live provider client (Mistral, OpenAI-compatible) ──────────────────────────


def _require_llm_config():
    """Return settings on the live path, or raise if AI config is missing. Only
    reached when ``LLM_MOCK`` is off — mock mode never needs a key (first-use
    check, mirroring crypto._get_key)."""
    s = get_settings()
    missing = [
        name
        for name, value in (
            ("LLM_API_BASE", s.llm_api_base),
            ("LLM_API_KEY", s.llm_api_key),
            ("LLM_MODEL", s.llm_model),
        )
        if not value
    ]
    if missing:
        raise RuntimeError(
            "LLM seam is not configured: missing " + ", ".join(missing) + ". "
            "Set them in the environment (Mistral STANDARD-plan key per D-15) or "
            "run with LLM_MOCK=true. They are intentionally not boot-required so a "
            "Tier-1-only deployment still starts."
        )
    return s


def _parse_json_content(content: str) -> dict:
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError as exc:
        raise AiUnavailableError(f"LLM returned non-JSON content: {exc}") from exc
    if not isinstance(parsed, dict):
        raise AiUnavailableError("LLM returned a non-object JSON payload")
    return parsed


async def _chat(messages: list[dict]) -> dict:
    """One chat-completion round-trip against the live provider. Returns the
    model's parsed JSON object. Any timeout / transport error / non-200 / unparsable
    body raises :class:`AiUnavailableError` — never leaking the upstream body."""
    s = _require_llm_config()
    url = f"{s.llm_api_base.rstrip('/')}/v1/chat/completions"
    body = {
        "model": s.llm_model,
        "messages": messages,
        "temperature": 0,  # determinism: same prompt → same answer where possible
        "response_format": {"type": "json_object"},
    }
    headers = {
        "Authorization": f"Bearer {s.llm_api_key}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    # Never log the messages — they carry clinical narrative; the kind/byte count is safe.
    logger.info("[LLM] POST %s model=%s messages=%d", url, s.llm_model, len(messages))
    try:
        async with httpx.AsyncClient(timeout=s.llm_timeout_seconds) as client:
            r = await client.post(url, json=body, headers=headers)
    except httpx.HTTPError as exc:
        logger.warning("[LLM] transport error: %s", exc)
        raise AiUnavailableError("LLM provider unreachable") from exc

    if r.status_code != 200:
        # Bounded, body-free log — provider error bodies may echo the prompt.
        logger.warning("[LLM] upstream %s", r.status_code)
        raise AiUnavailableError(f"LLM provider returned {r.status_code}")

    try:
        content = r.json()["choices"][0]["message"]["content"]
    except (KeyError, IndexError, ValueError) as exc:
        logger.warning("[LLM] unexpected response shape: %s", exc)
        raise AiUnavailableError("LLM response shape unexpected") from exc
    return _parse_json_content(content)


# ── Public entry point ──────────────────────────────────────────────────────────


async def complete(
    kind: str,
    fields: ClinicalPromptInput,
    *,
    cache_session: AsyncSession | None = None,
) -> LlmResult:
    """Build → scrub → (cache lookup) → generate (mock or live) → (cache store).

    ``cache_session`` opts the call into the DB cache: a hit short-circuits before
    any upstream call, a miss is generated, stored and committed (a concurrent
    double-miss is healed via the UNIQUE constraint). Without a session the call
    is uncached (used by the determinism tests).

    WARNING: storing a miss commits the WHOLE session — anything else staged on
    it lands with the cache row. Pass a dedicated session, or one carrying no
    other pending writes (today's AI endpoints are read-only besides this, which
    is what makes the convenience safe — keep it that way).

    The active model identity ("mock" or the configured model id) is part of the
    cache key, so a model swap or a mock↔live flip auto-invalidates: a hit is
    always an output of the identity that would generate on a miss. Orphaned
    rows from old models are retention's job (T2-12); there is deliberately no
    in-place refresh. Raises :class:`PiiBoundaryError` (refused) or
    :class:`AiUnavailableError` (upstream down)."""
    built = build_prompt(kind, fields)

    # Resolved once so the key, the generate branch, and the stored row all agree
    # on one identity even if the env flag flips mid-call. The mock path stays
    # config-free: get_settings() is only consulted when live.
    mock = is_mock_llm()
    active_model = "mock" if mock else get_settings().llm_model

    key = None
    if cache_session is not None:
        key = ai_cache.cache_key(built.kind, built.cache_input, model=active_model)
        hit = await ai_cache.get_cached(cache_session, key)
        if hit is not None:
            return LlmResult(payload=hit.payload, cached=True, model=hit.model)

    if mock:
        payload = _MOCKS[built.kind](fields)
    else:
        payload = await _chat(built.messages)

    if cache_session is not None and key is not None:
        ai_cache.stage_cached(
            cache_session, key=key, prompt_kind=built.kind, payload=payload, model=active_model
        )
        try:
            await cache_session.commit()
        except IntegrityError:
            # Concurrent double-miss: another request inserted this key first.
            # Roll back and serve the winner's row so both callers agree. If the
            # winner vanished between its insert and our re-read (a retention
            # delete racing us), fall through and return the freshly-generated
            # payload uncached — correctness over cache bookkeeping.
            await cache_session.rollback()
            winner = await ai_cache.get_cached(cache_session, key)
            if winner is not None:
                return LlmResult(payload=winner.payload, cached=True, model=winner.model)

    return LlmResult(payload=payload, cached=False, model=active_model)


# ── Embeddings (thin — T2-9 wires pgvector + the SPC corpus over this) ──────────


def _mock_embedding(text: str, dim: int = 8) -> list[float]:
    """Deterministic pseudo-embedding from a content hash — stable across runs so
    T2-9's mock-parity tests can assert on it. NOT semantically meaningful; the
    live path returns real Mistral vectors."""
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    return [digest[i] / 255.0 for i in range(dim)]


async def embed(texts: list[str]) -> list[list[float]]:
    """Embed ``texts`` (Mistral ``mistral-embed`` on the live path). The PII scrub
    applies here too — the SPC corpus is non-PII but a caller question (T2-9) must
    not smuggle an AMKA into a vector. Thin by design: T2-9 owns chunking,
    pgvector storage, and retrieval."""
    for text in texts:
        assert_no_pii(text)

    if is_mock_llm():
        return [_mock_embedding(t) for t in texts]

    s = _require_llm_config()
    url = f"{s.llm_api_base.rstrip('/')}/v1/embeddings"
    headers = {"Authorization": f"Bearer {s.llm_api_key}", "Content-Type": "application/json"}
    try:
        async with httpx.AsyncClient(timeout=s.llm_timeout_seconds) as client:
            r = await client.post(
                url, json={"model": s.llm_embed_model, "input": texts}, headers=headers
            )
    except httpx.HTTPError as exc:
        logger.warning("[LLM] embeddings transport error: %s", exc)
        raise AiUnavailableError("LLM provider unreachable") from exc
    if r.status_code != 200:
        logger.warning("[LLM] embeddings upstream %s", r.status_code)
        raise AiUnavailableError(f"LLM provider returned {r.status_code}")
    try:
        return [item["embedding"] for item in r.json()["data"]]
    except (KeyError, IndexError, ValueError) as exc:
        logger.warning("[LLM] embeddings response shape unexpected: %s", exc)
        raise AiUnavailableError("LLM response shape unexpected") from exc


# ── Reference prompt kind ───────────────────────────────────────────────────────
# The seam ships exactly one kind: a generic clinical summary that exercises every
# whitelisted field. It is the worked example the PII-guard, mock-determinism, and
# (with a stubbed transport) timeout tests run against, and the template a feature
# batch copies. Feature kinds are registered by their own modules (T2-5/6/7/9/10),
# never here — that keeps the seam free of feature coupling.

KIND_CLINICAL_SUMMARY = "clinical_summary"


def _build_clinical_summary(fields: ClinicalPromptInput) -> list[dict]:
    parts: list[str] = []
    if fields.atc_codes:
        parts.append("ATC codes: " + ", ".join(fields.atc_codes))
    if fields.condition_codes:
        parts.append("Patient conditions: " + ", ".join(fields.condition_codes))
    if fields.rule_text:
        parts.append("Safety rules:\n" + "\n".join(f"- {line}" for line in fields.rule_text))
    if fields.age_band or fields.sex_band:
        parts.append(
            f"Demographics band: age={fields.age_band or '?'} sex={fields.sex_band or '?'}"
        )
    if fields.symptom_text:
        parts.append(f"Reported symptoms: {fields.symptom_text}")
    if fields.question:
        parts.append(f"Question: {fields.question}")
    context = "\n".join(parts) if parts else "(no clinical context provided)"
    return [
        {
            "role": "system",
            "content": (
                "You are a clinical pharmacology assistant. Using ONLY the clinical "
                "context provided (drug codes, rule text, condition codes, anonymised "
                "demographic bands), reply with a concise summary in Greek. The context "
                "contains no patient identity. Respond as a JSON object: "
                '{"summary": "<el text>", "language": "el"}.'
            ),
        },
        {"role": "user", "content": context},
    ]


def _mock_clinical_summary(fields: ClinicalPromptInput) -> dict:
    """Deterministic canned output — derived from the input so two identical
    inputs always produce byte-identical output, but never calls the provider."""
    atcs = ", ".join(fields.atc_codes) or "—"
    conds = ", ".join(fields.condition_codes) or "—"
    return {
        "summary": f"[MOCK] Κλινική σύνοψη — φάρμακα: {atcs}· καταστάσεις: {conds}.",
        "language": "el",
    }


register_prompt_kind(
    KIND_CLINICAL_SUMMARY,
    builder=_build_clinical_summary,
    mock=_mock_clinical_summary,
)
