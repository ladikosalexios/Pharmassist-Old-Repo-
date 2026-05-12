import os


def is_mock_pharmapi() -> bool:
    """Re-read at request time so the flag can be toggled via env without restart."""
    return os.getenv("PHARMAPI_MOCK", "true").lower() not in ("false", "0", "no")
