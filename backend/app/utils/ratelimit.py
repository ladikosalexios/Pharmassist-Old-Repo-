"""In-process fixed-window rate limiter for the /v1 per-API-key limit (FT-1).

Deliberately NOT slowapi: its decorator surface keys on the client IP (B2B
integrators call from NAT'd server farms — one customer's farm must not
throttle as one "user", and two tenants behind one egress must not share a
bucket), its stock 429 body violates the BC-5 envelope, and it is disabled
wholesale under pytest (app/observability.py) so the contract would have no
test coverage. Counters here are keyed by api_key_id, enforced inside
get_api_context after the key resolves — unauthenticated traffic 401s before
it ever touches a counter.

Single-uvicorn-worker constraint applies — same as the Pharmapi session store
(D-1/D-8): a second worker would fork the counters per process and make every
limit N× looser. The Redis swap (FT-7) upgrades both seams together.
"""

import time
from collections.abc import Hashable
from functools import lru_cache

WINDOW_SECONDS: dict[str, float] = {"second": 1.0, "minute": 60.0, "hour": 3600.0}


@lru_cache(maxsize=8)
def parse_rate_limit(spec: str) -> tuple[int, float]:
    """``"120/minute"`` → ``(120, 60.0)``. Raises ValueError on malformed input.

    Period vocabulary matches slowapi's singular forms (second/minute/hour) so
    AUTH_LOGIN_RATE_LIMIT and V1_RATE_LIMIT read the same way in an env file.
    """
    count_str, sep, period = spec.strip().lower().partition("/")
    if not sep or period not in WINDOW_SECONDS:
        raise ValueError(f"rate limit spec must be '<count>/<second|minute|hour>', got {spec!r}")
    try:
        count = int(count_str)
    except ValueError as exc:
        raise ValueError(f"rate limit count must be an integer, got {spec!r}") from exc
    if count <= 0:
        raise ValueError(f"rate limit count must be positive, got {spec!r}")
    return count, WINDOW_SECONDS[period]


class FixedWindowLimiter:
    """``{key → (window_start, hit_count)}`` fixed-window counters.

    No locking: all mutation happens synchronously between awaits on the one
    event loop, and a fixed window needs no timer task — each hit lazily rolls
    its own window. Memory is bounded by the number of distinct active keys.
    """

    def __init__(self) -> None:
        self._counters: dict[Hashable, tuple[float, int]] = {}

    def hit(self, key: Hashable, limit: int, window_seconds: float) -> float | None:
        """Record one hit. Returns None when allowed, or the seconds until the
        window resets when the limit is exceeded (the Retry-After value)."""
        now = time.monotonic()
        start, count = self._counters.get(key, (now, 0))
        if now - start >= window_seconds:
            start, count = now, 0
        count += 1
        self._counters[key] = (start, count)
        if count > limit:
            return max(0.0, window_seconds - (now - start))
        return None

    def reset(self) -> None:
        """Test hook — drop all counters."""
        self._counters.clear()


# The /v1 per-API-key limiter instance (one per process — see module docstring).
v1_api_key_limiter = FixedWindowLimiter()
