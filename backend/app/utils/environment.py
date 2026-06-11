import os

# Recognized PHARMAPI_MOCK tokens (case-insensitive). The two helpers below
# only ever test membership of the FALSEY set, so historically ANY other value
# — including a typo like "flase" — fell through to mock=true. On a live box
# that silently routes dispense/verify/masterdata to MOCK: the exact regression
# 3fcf012/FT-5 exist to prevent. FT-15 closes the gap by validating this token
# set fail-fast at boot (app.config._validate_pharmapi_mock) so a bad flag
# breaks the boot rather than being discovered by a mocked dispense. This set
# is only about which *explicit* values are legal — it does NOT change either
# helper's unset default (mock for the read surface, live for the safety sites).
_FALSEY_MOCK_TOKENS = ("false", "0", "no")
_TRUTHY_MOCK_TOKENS = ("true", "1", "yes")
RECOGNIZED_MOCK_TOKENS = frozenset(_FALSEY_MOCK_TOKENS + _TRUTHY_MOCK_TOKENS)


def validate_pharmapi_mock_token() -> None:
    """Fail-fast on a malformed PHARMAPI_MOCK token (FT-15).

    Called at boot from app.config.get_settings() (i.e. create_app()), NOT
    lazily at first request — a dispense must never be what discovers a bad
    flag. The two helpers below only ever test membership of the FALSEY set, so
    any unrecognized value (a typo like ``PHARMAPI_MOCK=flase``) would fall
    through to mock=true and silently route dispense/verify/masterdata to MOCK
    on a live box (the regression 3fcf012/FT-5 guard against). Validating the
    token here — in the single read point — breaks the boot instead.

    Validates only the *token*: unset is legal (each helper applies its own
    unset default), and every recognized true/false/1/0/yes/no value parses.
    Does NOT change either helper's unset default."""
    raw = os.getenv("PHARMAPI_MOCK")
    if raw is None:
        return  # unset is legal — the asymmetric helper defaults apply
    if raw.strip().lower() not in RECOGNIZED_MOCK_TOKENS:
        raise RuntimeError(
            f"PHARMAPI_MOCK={raw!r} is not a recognized boolean token. "
            "Use one of true/false/1/0/yes/no (case-insensitive), or leave it "
            "unset. A typo like 'flase' would otherwise silently route a live "
            "box to MOCK — exactly the dispense regression FT-5/3fcf012 prevent."
        )


def is_mock_pharmapi() -> bool:
    """Re-read at request time so the flag can be toggled via env without restart."""
    return os.getenv("PHARMAPI_MOCK", "true").lower() not in _FALSEY_MOCK_TOKENS


def is_mock_pharmapi_explicit() -> bool:
    """PHARMAPI_MOCK with the FAIL-LIVE default: unset ⇒ live (returns False).

    For the safety-critical call sites — dispense, login credential
    verification, masterdata sync — where production silently falling into
    mock because the env var went missing is a patient-safety / data-integrity
    hazard (the dispense regression fixed in 3fcf012): a silently-mocked
    dispense makes a pharmacist believe a prescription reached ΗΔΥΚΑ when
    nothing did. Mock here is opt-in only — set PHARMAPI_MOCK=true explicitly
    (dev compose, CI, and the test preambles already do).

    is_mock_pharmapi() above keeps the dev-friendly default-MOCK semantics for
    every read-only surface. Same parsing, same re-read-per-call behaviour —
    only the unset default differs. Do not "simplify" the two into one.
    """
    return os.getenv("PHARMAPI_MOCK", "false").lower() not in _FALSEY_MOCK_TOKENS


def is_mock_hmvs() -> bool:
    """HMVS counterpart of is_mock_pharmapi — re-read per request, default mock.

    When true the HMVS service returns canned ITE-style responses and never
    fetches an OAuth2 token or touches the network (local dev, CI, tests).
    """
    return os.getenv("HMVS_MOCK", "true").lower() not in ("false", "0", "no")


def validate_llm_mock_token() -> None:
    """Fail-fast on a malformed LLM_MOCK token (T2-2, FT-15 pattern).

    Called at boot from app.config.get_settings(), alongside
    validate_pharmapi_mock_token(). is_mock_llm() below only tests membership of
    the FALSEY set, so any unrecognized value (a typo like ``LLM_MOCK=flase``)
    would fall through to mock=true and silently serve canned AI outputs on a
    box that is supposed to call Mistral — a paying Tier-2 customer would get
    static text instead of a real explanation. Validating the token here breaks
    the boot instead. Unset is legal (the helper applies its own mock default).
    """
    raw = os.getenv("LLM_MOCK")
    if raw is None:
        return  # unset is legal — is_mock_llm() defaults to mock
    if raw.strip().lower() not in RECOGNIZED_MOCK_TOKENS:
        raise RuntimeError(
            f"LLM_MOCK={raw!r} is not a recognized boolean token. "
            "Use one of true/false/1/0/yes/no (case-insensitive), or leave it "
            "unset. A typo like 'flase' would otherwise silently serve canned "
            "AI mock outputs on a box meant to call the live LLM."
        )


def is_mock_llm() -> bool:
    """Whether the T2-2 LLM seam serves deterministic canned outputs instead of
    calling the live provider. Re-read per call so it can be toggled via env
    without a restart (same shape as is_mock_pharmapi).

    Defaults to mock (true): a Tier-1-only deployment never carries LLM config,
    every test + the FT-13 sandbox story runs with zero upstream calls, and the
    trial slice runs end-to-end on LLM_MOCK. A live Tier-2 box sets
    LLM_MOCK=false explicitly (the boot-validated token above guards typos)."""
    return os.getenv("LLM_MOCK", "true").lower() not in _FALSEY_MOCK_TOKENS
