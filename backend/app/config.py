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
from typing import List

from dotenv import load_dotenv
from pydantic import BaseModel

load_dotenv()  # backend/.env when run from backend/


def _env_list(key: str, default: List[str]) -> List[str]:
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


class Settings(BaseModel):
    # ── App metadata ────────────────────────────────────────────────────────
    app_title: str
    app_description: str
    app_version: str

    # ── CORS ────────────────────────────────────────────────────────────────
    cors_allow_origins: List[str]
    cors_allow_credentials: bool
    cors_allow_methods: List[str]
    cors_allow_headers: List[str]

    # ── Auth / JWT ──────────────────────────────────────────────────────────
    secret_key: str
    token_expire_minutes: int

    # ── Pharmapi (ΗΔΥΚΑ) ────────────────────────────────────────────────────
    pharmapi_base: str
    pharmapi_username: str
    pharmapi_password: str
    pharmapi_api_key: str
    pharmapi_session_window_seconds: int

    # ── Database ────────────────────────────────────────────────────────────
    database_url: str


@lru_cache(maxsize=1)
def get_settings() -> Settings:
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
        secret_key=os.getenv("SECRET_KEY", "pharmassist-dev-secret-CHANGE-IN-PROD"),
        token_expire_minutes=_env_int(
            "TOKEN_EXPIRE_MINUTES", 480
        ),  # 8h pharmacist session
        pharmapi_base=os.getenv(
            "PHARMAPI_BASE", "https://testeps.e-prescription.gr/pharmapiv2"
        ),
        pharmapi_username=os.getenv("PHARMAPI_USERNAME", "medcare1pharmapi"),
        pharmapi_password=os.getenv("PHARMAPI_PASSWORD", "Aa900990099009!!"),
        pharmapi_api_key=os.getenv(
            "PHARMAPI_API_KEY", "pi2jwygkd07yho3a4dw6jc55tg5ra3uc"
        ),
        pharmapi_session_window_seconds=_env_int(
            "PHARMAPI_SESSION_WINDOW_SECONDS",
            23 * 3600,  # 23h (refresh before 24h hard limit)
        ),
        database_url=os.getenv(
            "DATABASE_URL",
            "postgresql+asyncpg://pharmassist:pharmassist_dev@localhost:5432/pharmassist",
        ),
    )
