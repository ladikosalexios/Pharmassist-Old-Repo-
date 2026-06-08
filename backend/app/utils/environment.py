import os


def is_mock_pharmapi() -> bool:
    """Re-read at request time so the flag can be toggled via env without restart."""
    return os.getenv("PHARMAPI_MOCK", "true").lower() not in ("false", "0", "no")


def is_mock_hmvs() -> bool:
    """HMVS counterpart of is_mock_pharmapi — re-read per request, default mock.

    When true the HMVS service returns canned ITE-style responses and never
    fetches an OAuth2 token or touches the network (local dev, CI, tests).
    """
    return os.getenv("HMVS_MOCK", "true").lower() not in ("false", "0", "no")
