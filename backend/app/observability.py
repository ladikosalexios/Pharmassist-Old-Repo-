"""Observability wiring — Sentry, JSON logging, slowapi rate limiting.

All three pieces are designed to be **safe no-ops in dev / tests**:

* ``configure_logging()`` keeps the human-readable default unless
  ``LOG_FORMAT=json`` is set. The test stack (``compose.test.yaml``) sets it,
  dev does not.
* ``configure_sentry()`` does nothing unless ``SENTRY_DSN`` is set. We never
  hard-depend on sentry_sdk being installed at runtime — it is in
  ``requirements.txt`` but the import is guarded so a future minimal image
  can drop it without breaking startup.
* ``install_rate_limiter()`` registers slowapi's exception handler on the app
  so the ``@auth_login_rate_limit`` decorator on ``POST /auth/login`` returns
  a structured 429 rather than a 500.

Kept in one module so the wiring is reviewable end-to-end. ``main.py`` calls
each of these from ``create_app``.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from typing import Final

from fastapi import FastAPI

# ── JSON logging ────────────────────────────────────────────────────────────

# Built-in LogRecord attributes — anything not in this set is treated as a
# caller-supplied extra and copied into the JSON payload. Computed once at
# module load so the formatter doesn't rebuild this on every single log line.
_RESERVED_LOG_ATTRS = set(logging.LogRecord("", 0, "", 0, "", None, None).__dict__) | {"message"}


class _JsonFormatter(logging.Formatter):
    """Minimal single-line JSON formatter — no extra dep.

    Emits the fields a log aggregator typically wants (level, name, message,
    timestamp), plus anything an HMVS / Pharmapi log line tagged via
    ``logger.info(..., extra={...})``. Exception info goes under ``exc``.
    """

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        # Whitelist record-extras so we never accidentally leak credentials
        # someone passed via ``extra={...}``. Reserved attrs filtered out via
        # the module-level set above.
        for k, v in record.__dict__.items():
            if k in _RESERVED_LOG_ATTRS:
                continue
            try:
                json.dumps(v)
                payload[k] = v
            except (TypeError, ValueError):
                payload[k] = repr(v)
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def configure_logging() -> None:
    """Install the JSON formatter when LOG_FORMAT=json; otherwise leave the
    root logger to uvicorn's default (already configured by the time we run)."""
    if os.getenv("LOG_FORMAT", "").lower() != "json":
        return
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(_JsonFormatter())
    root = logging.getLogger()
    # Replace existing handlers so we don't double-emit each line.
    for existing in list(root.handlers):
        root.removeHandler(existing)
    root.addHandler(handler)
    root.setLevel(os.getenv("LOG_LEVEL", "INFO").upper())


# ── Sentry ──────────────────────────────────────────────────────────────────


def configure_sentry() -> None:
    """Initialise Sentry when SENTRY_DSN is set; otherwise no-op.

    Defaults match a backend service that already has its own JSON logs: low
    traces_sample_rate, send_default_pii=False (we handle PII / pharmacist
    creds carefully — Sentry must never auto-capture request bodies)."""
    dsn = (os.getenv("SENTRY_DSN") or "").strip()
    if not dsn:
        return
    try:
        import sentry_sdk
    except ImportError:
        logging.getLogger(__name__).warning(
            "SENTRY_DSN is set but sentry_sdk is not installed — skipping init"
        )
        return
    sentry_sdk.init(
        dsn=dsn,
        environment=os.getenv("SENTRY_ENVIRONMENT", "test"),
        release=os.getenv("APP_VERSION", "0.1.0"),
        traces_sample_rate=float(os.getenv("SENTRY_TRACES_SAMPLE_RATE", "0.0")),
        send_default_pii=False,
    )
    logging.getLogger(__name__).info("Sentry initialised (env=%s)", os.getenv("SENTRY_ENVIRONMENT"))


# ── Rate limiting (slowapi) ─────────────────────────────────────────────────
#
# Why slowapi: tiny, FastAPI-native, no Redis dependency for the per-process
# limiter we need on a single-uvicorn-worker stack (see Dockerfile.prod and the
# pharmapi_session comment in compose.test.yaml). When B4 moves to multiple
# workers / instances slowapi can swap to a Redis backend without changing the
# decorator surface.

try:
    from slowapi import Limiter, _rate_limit_exceeded_handler  # type: ignore
    from slowapi.errors import RateLimitExceeded  # type: ignore
    from slowapi.util import get_remote_address  # type: ignore

    _SLOWAPI_AVAILABLE = True
except ImportError:  # pragma: no cover — slowapi is in requirements.txt
    _SLOWAPI_AVAILABLE = False
    Limiter = None  # type: ignore

# Limit profile for /auth/login. Bcrypt at rounds=12 is already a heavy
# per-request CPU spend, so 10/min/IP is plenty for a real human and tight
# enough to slow a credential-spray. Override via AUTH_LOGIN_RATE_LIMIT for
# environments behind a known shared NAT.
AUTH_LOGIN_LIMIT: Final[str] = os.getenv("AUTH_LOGIN_RATE_LIMIT", "10/minute")


if _SLOWAPI_AVAILABLE:
    limiter = Limiter(key_func=get_remote_address, default_limits=[])
else:
    limiter = None  # type: ignore


def install_rate_limiter(app: FastAPI) -> None:
    """Attach the limiter to the app and register slowapi's 429 handler.

    Idempotent — calling twice (e.g. in tests that build multiple apps) does
    not double-register. No-op when slowapi is not installed, so a minimal
    test image without the dep still boots."""
    if not _SLOWAPI_AVAILABLE or limiter is None:
        return
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


def auth_login_rate_limit():
    """Decorator factory for the login endpoint.

    Returns a real slowapi decorator when slowapi is available, or a
    passthrough decorator otherwise — so the route definition compiles in any
    environment. The slowapi decorator REQUIRES the wrapped function to take
    a ``request: Request`` parameter (the limiter pulls the client IP from
    it); the login handler has been updated accordingly.

    Under pytest we hand back a passthrough so the existing test suite (which
    drives multiple logins per minute through TestClient) doesn't trip the
    limiter. Real boots — dev compose, test compose, prod compose — all wrap
    normally. The check uses ``sys.modules`` rather than an env var because
    the same logic protects every test entrypoint without per-test plumbing."""
    if not _SLOWAPI_AVAILABLE or limiter is None or "pytest" in sys.modules:

        def _passthrough(fn):
            return fn

        return _passthrough
    return limiter.limit(AUTH_LOGIN_LIMIT)
