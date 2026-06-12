"""Contract + AC tests for POST /v1/safety/explain (T2-6, mock mode, DB-less).

Covers the ticket ACs that don't need a live DB:
  - PII guard: the prompt built from rule fields is identity-free, and an
    AMKA/EKAA-shaped token in a condition code is refused before dispatch.
  - LLM_MOCK canned Greek per seeded rule: the registered mock is deterministic,
    Greek, varies per rule, and the explain assembly carries the el rationale.
  - riskLevel is mapped from the deterministic rule severity (never generated).
  - Tier gate: a core key → 403 tier_required; request validation → 422 envelope.
  - /v1/safety/check is byte-identical: its module never imports the LLM seam.

The cache-hit AC (2nd identical call → 0 LLM calls) needs the real DB cache and
lives in test_v1_safety_explain_cache_db.py (excluded from the CI DB-less job).
The HTTP success path also needs the seeded rules, so the DB-less HTTP tests here
only exercise paths that resolve before the route body touches the DB (tier 403,
body-validation 422).
"""

import base64
import os

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
import uuid  # noqa: E402
from pathlib import Path  # noqa: E402

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.constants import AdrSeverity, CheckType  # noqa: E402
from app.db.models.safety_rule import SafetyRule  # noqa: E402
from app.db.session import get_session  # noqa: E402
from app.routers.v1.deps import ApiContext, get_api_context  # noqa: E402
from app.services import llm, safety_explanations  # noqa: E402
from app.services.pharmapi import PharmapiContext  # noqa: E402
from app.services.safety_explanations import (  # noqa: E402
    KIND_SAFETY_EXPLANATION,
    build_input,
    explain_rule,
)
from main import create_app  # noqa: E402

AMKA_TOKEN = "12345678901"  # 11 digits — AMKA-shaped


# Constructed rules (no DB): the explain layer takes a SafetyRule object, so its
# logic is unit-testable exactly like the engine seam (test_v1_safety_engine.py).
def _rule(
    code: str = "WARFARIN_ASPIRIN_BLEED",
    *,
    trigger_atc: str | None = "B01AA03",
    conflicting_atc: str | None = "B01AC06",
    trigger_condition_code: str | None = None,
    severity: str = AdrSeverity.MODERATE,
) -> SafetyRule:
    return SafetyRule(
        rule_code=code,
        check_type=CheckType.INTERACTIONS,
        trigger_atc=trigger_atc,
        conflicting_atc=conflicting_atc,
        trigger_condition_code=trigger_condition_code,
        severity=severity,
        message_en=f"{code} message",
        details_en=f"{code} clinical detail",
        recommended_action_en=f"{code} recommended action",
        active=True,
    )


def _has_greek(text: str) -> bool:
    return any("Ͱ" <= ch <= "Ͽ" for ch in text)


# ── PII guard: prompt built from rule fields is identity-free ──────────────────


def test_build_input_has_no_identity_and_passes_scrub():
    fields = build_input(_rule(trigger_condition_code="PREGNANCY"), ["RENAL_SEVERE"])
    # Structural: the whitelist input carries only clinical codes + English text.
    assert fields.symptom_text is None
    assert fields.question is None
    # The assembled prompt passes the seam's digit-token scrub (no raise).
    built = llm.build_prompt(KIND_SAFETY_EXPLANATION, fields)
    for message in built.messages:
        assert "12345678901" not in message["content"]


def test_amka_shaped_condition_code_is_refused():
    # A condition code carrying an AMKA-shaped token must not cross the boundary —
    # the seam's scrub fires when the prompt is built.
    fields = build_input(_rule(), [AMKA_TOKEN])
    with pytest.raises(llm.PiiBoundaryError):
        llm.build_prompt(KIND_SAFETY_EXPLANATION, fields)


# ── LLM_MOCK canned Greek per seeded rule (mock parity) ────────────────────────


def test_mock_explanation_is_greek_and_shaped():
    fields = build_input(_rule(), [])
    payload = safety_explanations._mock_explanation(fields)
    assert set(payload) == {"rationale", "mechanism", "alternatives", "language"}
    assert payload["language"] == "el"
    assert _has_greek(payload["rationale"]) and _has_greek(payload["mechanism"])
    assert isinstance(payload["alternatives"], list) and payload["alternatives"]
    assert _has_greek(payload["alternatives"][0])


def test_mock_explanation_is_deterministic_and_varies_per_rule():
    a1 = safety_explanations._mock_explanation(build_input(_rule(conflicting_atc="B01AC06"), []))
    a2 = safety_explanations._mock_explanation(build_input(_rule(conflicting_atc="B01AC06"), []))
    b = safety_explanations._mock_explanation(build_input(_rule(conflicting_atc="M01AE01"), []))
    assert a1 == a2  # deterministic
    assert a1 != b  # a different rule (different conflicting ATC) → different text


def test_explanation_kind_registered():
    assert KIND_SAFETY_EXPLANATION in llm.registered_kinds()


# ── explain_rule assembly (uncached path, session=None) ────────────────────────


@pytest.mark.parametrize(
    ("severity", "expected"),
    [
        (AdrSeverity.SEVERE, "Υψηλός"),
        (AdrSeverity.MODERATE, "Μέτριος"),
        (AdrSeverity.MILD, "Χαμηλός"),
    ],
)
def test_explain_rule_risk_level_from_severity(severity, expected):
    rule = _rule(severity=severity)
    result = asyncio.run(explain_rule(None, rule, []))
    assert result["risk_level"] == expected  # mapped from the engine, not generated


def test_explain_rule_shape_and_cached_false_uncached():
    result = asyncio.run(explain_rule(None, _rule(), ["PREGNANCY"]))
    assert set(result) == {
        "rule_code",
        "language",
        "rationale",
        "mechanism",
        "risk_level",
        "alternatives",
        "cached",
    }
    assert result["rule_code"] == "WARFARIN_ASPIRIN_BLEED"
    assert result["language"] == "el"
    assert result["cached"] is False  # no session → uncached
    assert _has_greek(result["rationale"])


def test_explain_rule_incomplete_live_payload_raises(monkeypatch):
    # A live model returning an empty rationale is not a usable explanation —
    # surface ai_unavailable rather than an empty field.
    async def _bad_complete(*args, **kwargs):
        return llm.LlmResult(payload={"mechanism": "x", "language": "el"}, cached=False, model="m")

    monkeypatch.setattr(llm, "complete", _bad_complete)
    with pytest.raises(llm.AiUnavailableError):
        asyncio.run(explain_rule(None, _rule(), []))


def test_unfolded_condition_profile_is_sorted_in_cache_input():
    # The cache key is invariant to caller ordering: two orderings of the same
    # profile produce identical cache input (→ identical key → a cache hit).
    a = build_input(_rule(), ["RENAL_SEVERE", "PREGNANCY"]).cache_input()
    b = build_input(_rule(), ["PREGNANCY", "RENAL_SEVERE"]).cache_input()
    assert a == b


# ── HTTP: tier gate + request validation (resolve before the route body) ───────


def _ctx(tier: str) -> ApiContext:
    location_id = uuid.uuid4()
    return ApiContext(
        customer_id=uuid.uuid4(),
        customer_name="Explain SA",
        tier=tier,
        location_id=location_id,
        location_name="Explain Store",
        api_key_id=uuid.uuid4(),
        is_eopyy=True,
        pharmapi=PharmapiContext(
            username="u",
            password="p",
            api_key="k",
            base_url="https://unused.example.test",
            pharmacy_unit_id=70123,
            session_key=f"location:{location_id}",
        ),
    )


CURRENT: dict = {"ctx": _ctx("clinical")}


async def _fake_get_session():
    # The route body never reaches the DB on these paths (tier 403 / body 422).
    yield None


app = create_app()
app.dependency_overrides[get_api_context] = lambda: CURRENT["ctx"]
app.dependency_overrides[get_session] = _fake_get_session
client = TestClient(app)


def _assert_envelope(resp, status: int, code: str):
    assert resp.status_code == status, resp.text
    body = resp.json()
    assert "error" in body
    assert body["error"]["code"] == code


def test_core_key_403s_tier_required():
    CURRENT["ctx"] = _ctx("core")
    try:
        r = client.post("/v1/safety/explain", json={"ruleCodes": ["WARFARIN_ASPIRIN_BLEED"]})
        _assert_envelope(r, 403, "tier_required")
    finally:
        CURRENT["ctx"] = _ctx("clinical")


def test_empty_rule_codes_422():
    r = client.post("/v1/safety/explain", json={"ruleCodes": []})
    _assert_envelope(r, 422, "validation_failed")


def test_missing_rule_codes_field_422():
    r = client.post("/v1/safety/explain", json={"conditionCodes": ["PREGNANCY"]})
    _assert_envelope(r, 422, "validation_failed")


# ── /v1/safety/check byte-identical: it never imports the LLM seam ─────────────

_SEAM_MARKERS = ("services.llm", "services.ai_cache", "safety_explanations", "safety_explain")


def test_safety_check_module_never_imports_the_seam():
    """POST /v1/safety/check stays deterministic: routers/v1/safety.py must not
    reference the LLM seam or the explanation feature in any form. This is the
    structural guarantee behind 'check byte-identical before/after' — the file is
    unmodified by T2-6 and provably cannot call the LLM."""
    safety_src = (
        Path(__file__).resolve().parent.parent / "app" / "routers" / "v1" / "safety.py"
    ).read_text(encoding="utf-8")
    offenders = [m for m in _SEAM_MARKERS if m in safety_src]
    assert offenders == [], f"routers/v1/safety.py references the seam: {offenders}"
