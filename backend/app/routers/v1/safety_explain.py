"""B2B /v1 AI safety-flag explanations (T2-6) — POST /v1/safety/explain.

A SEPARATE endpoint from POST /v1/safety/check (routers/v1/safety.py): that route
stays deterministic and never imports the LLM seam, so it keeps its latency and
keeps working when the LLM is down. This one takes the rule codes a check produced
(+ an optional patient condition profile) and returns the Greek clinical rationale
behind each, via the T2-2 seam (services/safety_explanations.py).

Tier-gated `clinical`. Reads rule fields from the DB in every mode (safety_rules is
a local seeded table, not upstream — there is no PHARMAPI mock branch); the
mock-vs-live split here is the LLM_MOCK seam, which serves deterministic canned
Greek with zero upstream calls. Caching by (rule_code, sorted condition-profile)
rides T2-2's ai_response_cache: an identical second request is served with zero
LLM calls and `cached: true`.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.schemas.v1 import V1SafetyExplainRequest, V1SafetyExplainResponse
from app.services import safety_explanations

from .deps import ApiContext, require_tier, tier_required_response
from .errors import V1Error

router = APIRouter(prefix="/safety", tags=["b2b-v1"])


def _normalize(codes: list[str]) -> list[str]:
    """Trim + upper-case + de-duplicate (preserving first-seen order). Rule and
    condition codes are uppercase identifiers, so normalising here keeps the cache
    key stable regardless of caller casing and collapses accidental duplicates."""
    seen: set[str] = set()
    out: list[str] = []
    for raw in codes:
        code = raw.strip().upper()
        if code and code not in seen:
            seen.add(code)
            out.append(code)
    return out


@router.post(
    "/explain",
    response_model=V1SafetyExplainResponse,
    responses=tier_required_response("clinical"),
)
async def safety_explain(
    body: V1SafetyExplainRequest,
    ctx: ApiContext = Depends(require_tier("clinical")),  # noqa: B008
    session: AsyncSession = Depends(get_session),
):
    """Explain one or more safety-rule flags in Greek (rationale, mechanism, risk
    level, alternatives), optionally tailored to a patient condition profile.

    Unknown rule codes → 422; the rationale is decision support, not a decision —
    riskLevel is mapped from the deterministic rule severity, never generated.
    """
    rule_codes = _normalize(body.rule_codes)
    condition_codes = _normalize(body.condition_codes)

    rules = await safety_explanations.load_rules_by_code(session, rule_codes)
    missing = [code for code in rule_codes if code not in rules]
    if missing:
        raise V1Error(
            "validation_failed",
            422,
            f"Unknown rule code(s): {', '.join(missing)}",
        )

    # Sequential on purpose: one AsyncSession is not concurrency-safe, and each
    # cache miss commits its row before the next lookup. A check typically yields a
    # handful of rules, and cache hits make repeats free.
    explanations = [
        await safety_explanations.explain_rule(session, rules[code], condition_codes)
        for code in rule_codes
    ]
    return V1SafetyExplainResponse(explanations=explanations)
