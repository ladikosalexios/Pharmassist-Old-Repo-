"""Tier-2 AI safety-flag explanations (T2-6) — the Greek clinical rationale layer
over the deterministic safety engine, built on the T2-2 LLM seam.

Why a separate service (and a separate endpoint, ``routers/v1/safety_explain.py``):
``POST /v1/safety/check`` (``routers/v1/safety.py``) stays deterministic and never
imports the LLM seam — it must keep its latency and keep working when the LLM is
down. Explanations are an *opt-in* second call: the caller takes the rule codes a
check produced and asks for the Greek narrative behind them.

Prompt inputs are **rule fields only** (``message_en``/``details_en``/
``recommended_action_en``, the trigger/conflicting ATC codes, the rule's trigger
condition) plus the caller-supplied **patient condition profile** (clinical codes
like ``PREGNANCY``/``RENAL_SEVERE`` — never identity). There is, by construction,
no patient identity in the prompt: the T2-2 ``ClinicalPromptInput`` whitelist has
no AMKA/name/address field, and the seam's digit-token scrub runs over every
assembled string before dispatch.

Caching (the catalog's "rationale per rule + patient condition profile",
PharmAssist_Pricing.md:92) rides T2-2's ``ai_response_cache`` for free: the cache
key is a hash of the prompt input, which is a deterministic function of
(rule_code → its unique rule text + ATC codes) and the sorted condition profile.
So two identical ``(rule, condition-profile)`` requests hash the same key — the
second is served from the cache with zero LLM calls.

``riskLevel`` is **not** generated — it is mapped deterministically from the
engine's own ``rule.severity`` so the risk classification can never be
hallucinated by the model; the LLM only produces the genuinely-generative Greek
text (rationale / mechanism / alternatives). This is the E4 "suggests, never
decides" posture: the deterministic severity stays authoritative.

The degraded no-LLM fallback the audit notes (static ``*_gr`` seed columns) is
**not** shipped here — it can't produce the condition-aware rationale the catalog
promises (TIER2-AUDIT.md §1, T2-6 note). ``LLM_MOCK`` canned Greek is the
deterministic stand-in for tests / the demo, not a product fallback.
"""

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import AdrSeverity
from app.db.models.safety_rule import SafetyRule
from app.services import llm

logger = logging.getLogger(__name__)

# The T2-2 prompt kind this feature registers. Feature-local, so the seam stays
# free of feature coupling (services/llm.py:register_prompt_kind contract).
KIND_SAFETY_EXPLANATION = "safety_explanation"

# Greek risk-level labels, mapped from the engine's severity so the classification
# is anchored to the deterministic rule, never produced by the model. An unknown
# severity falls through to its raw value rather than guessing a label.
_RISK_LEVEL_EL: dict[str, str] = {
    AdrSeverity.SEVERE: "Υψηλός",
    AdrSeverity.MODERATE: "Μέτριος",
    AdrSeverity.MILD: "Χαμηλός",
}


def _risk_level_el(severity: str) -> str:
    return _RISK_LEVEL_EL.get(severity, severity)


# ── Prompt input from rule fields (the structural PII boundary) ────────────────


def build_input(rule: SafetyRule, condition_codes: list[str]) -> llm.ClinicalPromptInput:
    """Assemble the whitelisted prompt input for one rule + a patient condition
    profile.

    ``condition_codes`` is the caller's patient profile; it is sorted+deduped here
    so the cache key is invariant to caller ordering (the whole point of the
    rule+profile cache). The rule's own ``trigger_condition_code`` rides in the
    rule text — it is a rule field, distinct from the patient profile — so a
    contraindication rule still explains its trigger even when the caller passes
    no conditions. Only ATC codes, English rule text, and condition codes cross
    the boundary; there is no field for identity to occupy."""
    atc_codes = [c for c in (rule.trigger_atc, rule.conflicting_atc) if c]
    rule_text = [t for t in (rule.message_en, rule.details_en, rule.recommended_action_en) if t]
    if rule.trigger_condition_code:
        # A rule field (not the patient profile): the clinical state that arms
        # this contraindication. Labeled so the model treats it as the rule's
        # trigger, not a patient-supplied condition.
        rule_text.append(f"Rule trigger condition: {rule.trigger_condition_code}")
    return llm.ClinicalPromptInput(
        atc_codes=atc_codes,
        rule_text=rule_text,
        condition_codes=sorted(set(condition_codes)),
    )


# ── Prompt builder + deterministic mock (registered with the seam) ─────────────


def _build_messages(fields: llm.ClinicalPromptInput) -> list[dict]:
    """English instruction + clinical context → Greek JSON output. Mirrors the
    seam's reference kind: English labels keep the instruction unambiguous while
    the model is told to answer in Greek."""
    parts: list[str] = []
    if fields.atc_codes:
        parts.append("Relevant ATC codes: " + ", ".join(fields.atc_codes))
    if fields.condition_codes:
        parts.append("Patient condition profile: " + ", ".join(fields.condition_codes))
    if fields.rule_text:
        parts.append(
            "Triggered safety rule (English source):\n"
            + "\n".join(f"- {line}" for line in fields.rule_text)
        )
    context = "\n".join(parts) if parts else "(no clinical context provided)"
    return [
        {
            "role": "system",
            "content": (
                "You are a clinical pharmacology assistant supporting a Greek "
                "community pharmacist. You are given an English-language drug-safety "
                "rule (its alert message, clinical detail, and recommended action), "
                "the relevant ATC drug codes, and optionally the patient's condition "
                "profile as clinical codes only. The context contains NO patient "
                "identity. Explain the flagged concern in clear, professional Greek. "
                "Use ONLY the clinical context provided — do not invent drugs, doses, "
                "or identifiers. Respond as a JSON object with exactly these keys: "
                '{"rationale": "<why this is flagged, in Greek>", '
                '"mechanism": "<the pharmacological mechanism, in Greek>", '
                '"alternatives": ["<an alternative or management step, in Greek>"], '
                '"language": "el"}.'
            ),
        },
        {"role": "user", "content": context},
    ]


def _mock_explanation(fields: llm.ClinicalPromptInput) -> dict:
    """Deterministic canned Greek for ``LLM_MOCK`` — a pure function of the
    whitelisted input, so two identical requests produce byte-identical output and
    the cache-hit / mock-parity tests can assert on it, while every seeded rule
    (each with its own ATC/condition signature) gets its own text. Never calls the
    provider; the ``[MOCK]`` marker keeps a mock-warmed row from ever reading as a
    real explanation."""
    atcs = ", ".join(fields.atc_codes) or "—"
    conds = ", ".join(fields.condition_codes)
    cond_clause = f" σε ασθενή με κατάσταση: {conds}" if conds else ""
    return {
        "rationale": (
            f"[MOCK] Επισημαίνεται πιθανός κίνδυνος ασφάλειας για τα φάρμακα {atcs}"
            f"{cond_clause}. Αξιολογήστε την κλινική ένδειξη πριν τη χορήγηση."
        ),
        "mechanism": (
            f"[MOCK] Ο μηχανισμός σχετίζεται με την αλληλεπίδραση ή αντένδειξη "
            f"των δραστικών ουσιών ({atcs})."
        ),
        "alternatives": [f"[MOCK] Εξετάστε εναλλακτική αγωγή ή στενή παρακολούθηση{cond_clause}."],
        "language": "el",
    }


llm.register_prompt_kind(
    KIND_SAFETY_EXPLANATION,
    builder=_build_messages,
    mock=_mock_explanation,
)


# ── Rule loading + explanation assembly ────────────────────────────────────────


async def load_rules_by_code(session: AsyncSession, rule_codes: list[str]) -> dict[str, SafetyRule]:
    """Load the requested rules keyed by ``rule_code`` (active flag ignored — a
    caller may legitimately ask to explain a rule a past check produced). Returns
    only the codes that exist; the router treats any miss as a 422."""
    if not rule_codes:
        return {}
    result = await session.scalars(select(SafetyRule).where(SafetyRule.rule_code.in_(rule_codes)))
    return {rule.rule_code: rule for rule in result.all()}


async def explain_rule(
    session: AsyncSession | None,
    rule: SafetyRule,
    condition_codes: list[str],
    *,
    commit: bool = True,
) -> dict:
    """Produce the Greek explanation for one rule + condition profile.

    Passing ``session`` opts the call into the DB cache (a hit short-circuits the
    LLM entirely, setting ``cached: true``); passing ``None`` runs uncached — the
    DB-less unit path. ``riskLevel`` is mapped from ``rule.severity`` after the
    call, so it is identical on a cache hit, a miss, mock, or live."""
    fields = build_input(rule, condition_codes)
    result = await llm.complete(
        KIND_SAFETY_EXPLANATION,
        fields,
        cache_session=session,
        commit=commit,
    )
    payload = result.payload
    # A live model that omits the load-bearing narrative isn't a usable
    # explanation — surface it as ai_unavailable rather than returning an empty
    # rationale. The mock always populates these, so this only guards the live path.
    if not payload.get("rationale") or not payload.get("mechanism"):
        raise llm.AiUnavailableError("LLM returned an incomplete explanation payload")
    return {
        "rule_code": rule.rule_code,
        "language": payload.get("language", "el"),
        "rationale": payload["rationale"],
        "mechanism": payload["mechanism"],
        "risk_level": _risk_level_el(rule.severity),
        "alternatives": payload.get("alternatives", []),
        "cached": result.cached,
    }
