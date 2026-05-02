"""Auth + session schemas (login response, /auth/me, Pharmapi session status)."""

from typing import Optional

from pydantic import BaseModel


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    pharmacist_name: str
    pharmacy: str


class PharmacistMe(BaseModel):
    email: str
    name: str
    pharmacy: str


class SessionStatus(BaseModel):
    pharmapi_connected: bool
    connected_at: Optional[str]
    session_age_minutes: Optional[float]
    session_valid_for_minutes: Optional[float]
    pharmapi_user: Optional[dict]
