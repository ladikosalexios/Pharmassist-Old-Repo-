"""Auth + session schemas (login request/response, /auth/me, Pharmapi session status)."""

from pydantic import BaseModel, EmailStr


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class LoginResponse(BaseModel):
    pharmacist_name: str
    pharmacy: str
    pharmacist_id: str
    pharmacy_id: str


class PharmacistMe(BaseModel):
    email: str
    name: str
    pharmacy: str
    pharmacist_id: str
    pharmacy_id: str


class SessionStatus(BaseModel):
    pharmapi_connected: bool
    connected_at: str | None
    session_age_minutes: float | None
    session_valid_for_minutes: float | None
    pharmapi_user: dict | None
