"""Auth + session schemas (login response, /auth/me, Pharmapi session status)."""

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
    connected_at: str | None
    session_age_minutes: float | None
    session_valid_for_minutes: float | None
    pharmapi_user: dict | None
