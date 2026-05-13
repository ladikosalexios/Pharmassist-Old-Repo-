"""Auth primitives: stdlib HS256 JWT + the runtime user cache.

The USERS dict is populated at login time from the Pharmapi
/api/v1/user/me response; it's not a demo store any more.

Reads SECRET_KEY / TOKEN_EXPIRE_MINUTES from the centralised settings.
"""

import base64
import hashlib
import hmac
import json
import time

from fastapi import HTTPException

from ..config import get_settings

# Module-level constants kept for backward compat with anything that imports
# them by name. Sourced from settings at first import.
_settings = get_settings()
SECRET_KEY = _settings.secret_key
TOKEN_EXPIRE_MIN = _settings.token_expire_minutes


# Runtime cache: written by /auth/login on successful Pharmapi auth,
# read by deps.get_current_user when a JWT comes in. Starts empty —
# a server restart clears it and forces re-login.
USERS: dict = {}


# ── Minimal JWT (stdlib only — no python-jose needed) ───────────────────────
def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _b64url_decode(s: str) -> bytes:
    padding = 4 - len(s) % 4
    return base64.urlsafe_b64decode(s + "=" * padding)


def create_jwt(payload: dict) -> str:
    header = _b64url(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    payload = {**payload, "exp": int(time.time()) + TOKEN_EXPIRE_MIN * 60}
    body = _b64url(json.dumps(payload).encode())
    sig_input = f"{header}.{body}".encode()
    sig = hmac.new(SECRET_KEY.encode(), sig_input, hashlib.sha256).digest()
    return f"{header}.{body}.{_b64url(sig)}"


def decode_jwt(token: str) -> dict:
    try:
        header, body, sig = token.split(".")
        sig_input = f"{header}.{body}".encode()
        expected = _b64url(hmac.new(SECRET_KEY.encode(), sig_input, hashlib.sha256).digest())
        if not hmac.compare_digest(sig, expected):
            raise ValueError("bad signature")
        payload = json.loads(_b64url_decode(body))
        if payload.get("exp", 0) < time.time():
            raise ValueError("token expired")
        return payload
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {e}") from e
