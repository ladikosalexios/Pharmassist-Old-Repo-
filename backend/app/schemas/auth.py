"""Auth + session schemas (login request/response, /auth/me, Pharmapi session status)."""

import uuid
from typing import Literal

from pydantic import BaseModel, EmailStr, Field


class LoginRequest(BaseModel):
    email: EmailStr
    password: str
    mode: Literal["full", "reporting"] = "full"


class LoginResponse(BaseModel):
    scope: str = "full"
    yellow_cards_enabled: bool = False
    pharmacist_name: str
    pharmacy: str
    pharmacist_id: str
    pharmacy_id: str


class PharmacistMe(BaseModel):
    scope: str = "full"
    yellow_cards_enabled: bool = False
    email: str
    name: str
    pharmacy: str
    pharmacist_id: str
    pharmacy_id: str
    # Decrypted ΗΔΥΚΑ/Pharmapi login, shown read-only on Settings. None when
    # the pharmacy link has no stored credential.
    pharmapi_username: str | None = None


class SessionStatus(BaseModel):
    pharmapi_connected: bool
    connected_at: str | None
    session_age_minutes: float | None
    session_valid_for_minutes: float | None
    pharmapi_user: dict | None


class InviteRequest(BaseModel):
    email: EmailStr
    pharmacy_id: uuid.UUID  # Pydantic validates the format — malformed input → 422


class InviteResponse(BaseModel):
    invite_url: str
    expires_at: str
    email: str


class InviteInfo(BaseModel):
    pharmacy_name: str
    pharmacy_address: str  # formatted from the pharmacy's structured fields
    email: str
    expires_at: str


class AcceptInviteRequest(BaseModel):
    token: str
    full_name: str
    password: str = Field(min_length=8)
    eof_licence_no: str
    phone: str | None = None
    pharmapi_username: str
    pharmapi_password: str
