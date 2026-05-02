"""Auth primitives: stdlib HS256 JWT, the demo user store, and password hashing.

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


# ── Demo user store (replace with DB in production) ─────────────────────────
# SHA-256 of password — run: python3 -c "import hashlib; print(hashlib.sha256(b'demo123').hexdigest())"
USERS = {
    "pharmacist@demo.gr": {
        "name": "Demo Pharmacist",
        "pharmacy": "MedCare Pharmacy",
        # SHA-256("demo123")
        "pw_hash": "d3ad9315b7be5dd53b31a273b3b3aba5defe700808305aa16a3062b76658a791",
    },
}


def verify_password(plain: str, hashed: str) -> bool:
    return hashlib.sha256(plain.encode()).hexdigest() == hashed


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
        raise HTTPException(status_code=401, detail=f"Invalid token: {e}")
