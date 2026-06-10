import os


def is_mock_pharmapi() -> bool:
    """Re-read at request time so the flag can be toggled via env without restart."""
    return os.getenv("PHARMAPI_MOCK", "true").lower() not in ("false", "0", "no")


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
    return os.getenv("PHARMAPI_MOCK", "false").lower() not in ("false", "0", "no")


def is_mock_hmvs() -> bool:
    """HMVS counterpart of is_mock_pharmapi — re-read per request, default mock.

    When true the HMVS service returns canned ITE-style responses and never
    fetches an OAuth2 token or touches the network (local dev, CI, tests).
    """
    return os.getenv("HMVS_MOCK", "true").lower() not in ("false", "0", "no")
