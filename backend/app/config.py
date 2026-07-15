"""Centralised settings for the PharmAssist backend.

Plain pydantic ``BaseModel`` + a cached factory that reads env vars at first
call. We deliberately don't depend on ``pydantic-settings`` — the surface we
need is small and this keeps the dependency list minimal.

Tests can swap settings by setting env vars then calling
``get_settings.cache_clear()`` before re-importing the services that read
config at import time.
"""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Literal

from dotenv import load_dotenv
from pydantic import BaseModel

from .utils.environment import validate_llm_mock_token, validate_pharmapi_mock_token
from .utils.ratelimit import parse_rate_limit

load_dotenv()  # backend/.env when run from backend/


def _env_list(key: str, default: list[str]) -> list[str]:
    """Comma-separated list env var; empty/missing → default."""
    raw = os.getenv(key)
    if not raw:
        return list(default)
    return [s.strip() for s in raw.split(",") if s.strip()]


def _env_bool(key: str, default: bool) -> bool:
    raw = os.getenv(key)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(key: str, default: int) -> int:
    raw = os.getenv(key)
    if raw is None or raw.strip() == "":
        return default
    return int(raw)


def _env_required(key: str) -> str:
    """Required secret env var — fail loudly at startup if it is missing.

    Secrets must never fall back to a baked-in default: a known default
    would let anyone forge sessions or impersonate the app to ΗΔΥΚΑ.
    """
    value = (os.getenv(key) or "").strip()
    if not value:
        raise RuntimeError(
            f"Required environment variable {key!r} is not set. "
            "Copy backend/.env.example to backend/.env (or set it in your "
            "environment) — see the README."
        )
    return value


def _validated_v1_rate_limit(spec: str) -> str:
    """Fail-fast on a malformed V1_RATE_LIMIT — a bad spec must break the boot,
    not 500 every authenticated /v1 request at first enforcement."""
    try:
        parse_rate_limit(spec)
    except ValueError as exc:
        raise RuntimeError(
            f"V1_RATE_LIMIT={spec!r} is invalid: {exc}. "
            "Use '<count>/<second|minute|hour>', e.g. '120/minute'."
        ) from exc
    return spec


class Settings(BaseModel):
    # ── App metadata ────────────────────────────────────────────────────────
    app_title: str
    app_description: str
    app_version: str

    # ── CORS ────────────────────────────────────────────────────────────────
    cors_allow_origins: list[str]
    cors_allow_credentials: bool
    cors_allow_methods: list[str]
    cors_allow_headers: list[str]

    # ── Auth / JWT ──────────────────────────────────────────────────────────
    secret_key: str
    token_expire_minutes: int

    # ── Pharmapi (ΗΔΥΚΑ) ────────────────────────────────────────────────────
    pharmapi_base: str
    pharmapi_username: str
    pharmapi_password: str
    pharmapi_api_key: str
    pharmapi_session_window_seconds: int
    # Proactive keep-alive: ping ΗΔΥΚΑ /user/me on a timer so the 24h session
    # never lapses, even when the app is idle. Opt-in (off by default so tests
    # and CI never make live upstream calls); enabled in compose.
    pharmapi_keepalive_enabled: bool
    pharmapi_keepalive_interval_seconds: int

    # ── B2B /v1 ──────────────────────────────────────────────────────────────
    # Per-API-key fixed-window limit (FT-1), e.g. "120/minute". Enforced in
    # routers/v1/deps.get_api_context; validated fail-fast at startup below.
    v1_rate_limit: str

    # ── LLM seam (Tier-2 AI, T2-2 / D-15: Mistral EU, STANDARD plan) ─────────
    # Provider-agnostic; the wired target is Mistral's EU standard API. NONE of
    # these are fail-fast: a Tier-1-only deployment must boot without any AI
    # config. services/llm.py checks api_key/base/model at FIRST USE (like
    # crypto.CREDENTIAL_ENCRYPTION_KEY), and only on the live path — LLM_MOCK
    # (default true) skips the upstream call entirely. The embeddings model is
    # carried here so T2-9 (RAG) consumes it without a config change.
    llm_mock: bool
    llm_api_base: str
    llm_api_key: str
    llm_model: str
    llm_embed_model: str
    llm_timeout_seconds: int

    # ── Cookie security ─────────────────────────────────────────────────────
    cookie_secure: bool
    cookie_httponly: bool
    cookie_samesite: Literal["strict", "lax", "none"]

    # ── Database ────────────────────────────────────────────────────────────
    database_url: str


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    # FT-15: validate the mock flag at boot, before anything reads it lazily.
    validate_pharmapi_mock_token()
    # T2-2: same fail-fast for the LLM seam's mock flag (a typo'd LLM_MOCK would
    # otherwise silently serve canned AI outputs on a live Tier-2 box).
    validate_llm_mock_token()
    return Settings(
        app_title=os.getenv("APP_TITLE", "PharmAssist POC"),
        app_description=os.getenv(
            "APP_DESCRIPTION",
            "FastAPI backend bridging pharmacist login → Pharmapi (ΗΔΥΚΑ)",
        ),
        app_version=os.getenv("APP_VERSION", "0.1.0"),
        cors_allow_origins=_env_list("CORS_ALLOW_ORIGINS", ["*"]),
        cors_allow_credentials=_env_bool("CORS_ALLOW_CREDENTIALS", True),
        cors_allow_methods=_env_list("CORS_ALLOW_METHODS", ["*"]),
        cors_allow_headers=_env_list("CORS_ALLOW_HEADERS", ["*"]),
        secret_key=_env_required("SECRET_KEY"),
        token_expire_minutes=_env_int("TOKEN_EXPIRE_MINUTES", 480),  # 8h pharmacist session
        pharmapi_base=os.getenv("PHARMAPI_BASE", "https://testeps.e-prescription.gr/pharmapiv2"),
        pharmapi_username=_env_required("PHARMAPI_USERNAME"),
        pharmapi_password=_env_required("PHARMAPI_PASSWORD"),
        pharmapi_api_key=_env_required("PHARMAPI_API_KEY"),
        pharmapi_session_window_seconds=_env_int(
            "PHARMAPI_SESSION_WINDOW_SECONDS",
            23 * 3600,  # 23h (refresh before 24h hard limit)
        ),
        pharmapi_keepalive_enabled=_env_bool("PHARMAPI_KEEPALIVE_ENABLED", False),
        pharmapi_keepalive_interval_seconds=_env_int(
            "PHARMAPI_KEEPALIVE_INTERVAL_SECONDS",
            12 * 3600,  # 12h — comfortably within the 24h ΗΔΥΚΑ window
        ),
        v1_rate_limit=_validated_v1_rate_limit(os.getenv("V1_RATE_LIMIT", "120/minute")),
        # LLM seam (T2-2). Defaults: Mistral's EU API + a sensible model; the key
        # is empty until provisioned (checked at first use, never at boot). The
        # OpenAI-compatible chat path is POST {base}/v1/chat/completions.
        llm_mock=_env_bool("LLM_MOCK", True),
        llm_api_base=os.getenv("LLM_API_BASE", "https://api.mistral.ai"),
        llm_api_key=os.getenv("LLM_API_KEY", ""),
        llm_model=os.getenv("LLM_MODEL", "mistral-large-latest"),
        llm_embed_model=os.getenv("LLM_EMBED_MODEL", "mistral-embed"),
        llm_timeout_seconds=_env_int("LLM_TIMEOUT_SECONDS", 30),
        cookie_secure=_env_bool("COOKIE_SECURE", True),
        cookie_httponly=_env_bool("COOKIE_HTTPONLY", True),
        cookie_samesite=os.getenv("COOKIE_SAMESITE", "strict"),
        database_url=os.getenv(
            "DATABASE_URL",
            "postgresql+asyncpg://pharmassist:pharmassist_dev@localhost:5432/pharmassist",
        ),
    )
