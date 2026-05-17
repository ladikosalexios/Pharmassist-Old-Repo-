"""Shared session-cookie helpers.

Used by both login routers — pharmacist (`/auth`) and company staff (`/admin`)
— so neither has to import cookie plumbing from the other.
"""

import os

from .security import TOKEN_EXPIRE_MIN

# Cookie Max-Age tracks the JWT's `exp` claim, so the browser drops the cookie
# at the same moment the server would start rejecting the token.
COOKIE_MAX_AGE_SECONDS = TOKEN_EXPIRE_MIN * 60


def cookie_secure() -> bool:
    """Secure cookie by default; opt out via COOKIE_SECURE=false for local HTTP."""
    return os.getenv("COOKIE_SECURE", "true").lower() not in ("false", "0", "no")
