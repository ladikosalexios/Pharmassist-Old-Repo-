"""Pharmacist login + session info (ADR-003: JSON body, JWT in httpOnly cookie).

The JWT lives ONLY in a SameSite=Strict, httpOnly cookie — it is never
returned in the response body. The response carries display fields
(pharmacist_name, pharmacy, ids) the SPA needs to render its shell.
"""

import os

import bcrypt
from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..crypto import decrypt_credential
from ..db.models.pharmacist import Pharmacist
from ..db.models.pharmacist_pharmacy import PharmacistPharmacy
from ..db.models.pharmacy import Pharmacy
from ..db.session import get_session
from ..deps import get_current_user
from ..schemas.auth import LoginRequest, LoginResponse, PharmacistMe
from ..services.pharmapi import (
    _start_pharmapi_session,
    verify_pharmapi_credentials_with_decrypted,
)
from ..services.security import create_jwt

router = APIRouter(prefix="/auth", tags=["auth"])

COOKIE_NAME = "pharmassist_session"
COOKIE_MAX_AGE_SECONDS = 8 * 60 * 60  # 28800s == 8h pharmacist session

# Pinned to the same cost factor (rounds=12) as real password hashes (see
# scripts/seed.py). Used to neutralise the timing side-channel when an email
# isn't on file — we always pay one bcrypt verify regardless. Keep in sync if
# the production cost factor ever changes.
_DUMMY_PASSWORD_HASH: str = bcrypt.hashpw(
    b"unused-dummy-for-constant-time-login", bcrypt.gensalt(rounds=12)
).decode()


def _cookie_secure() -> bool:
    """Secure cookie by default; opt out via COOKIE_SECURE=false for local HTTP."""
    return os.getenv("COOKIE_SECURE", "true").lower() not in ("false", "0", "no")


@router.post("/login", response_model=LoginResponse)
async def login(
    body: LoginRequest,
    response: Response,
    db: AsyncSession = Depends(get_session),
) -> LoginResponse:
    """Authenticate against the pharmacists table + ΗΔΥΚΑ, issue a session cookie."""
    pharmacist = await db.scalar(
        select(Pharmacist).where(
            Pharmacist.email == body.email,
            Pharmacist.active.is_(True),
        )
    )
    # Always run bcrypt — against the real hash if the account exists, against
    # the dummy hash otherwise — so unknown-email and wrong-password requests
    # take the same wall-clock time. Do NOT short-circuit on `pharmacist is None`
    # before checkpw, or you leak account existence via response latency.
    password_hash = pharmacist.password_hash if pharmacist is not None else _DUMMY_PASSWORD_HASH
    password_ok = bcrypt.checkpw(body.password.encode(), password_hash.encode())
    if pharmacist is None or not password_ok:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    link = await db.scalar(
        select(PharmacistPharmacy).where(
            PharmacistPharmacy.pharmacist_id == pharmacist.id,
            PharmacistPharmacy.is_default.is_(True),
        )
    )
    if link is None:
        raise HTTPException(status_code=500, detail="Pharmacist has no default pharmacy linked")

    pharmacy = await db.scalar(select(Pharmacy).where(Pharmacy.id == link.pharmacy_id))
    if pharmacy is None:
        raise HTTPException(status_code=500, detail="Linked pharmacy missing")

    # Decrypt ΗΔΥΚΑ credentials in-memory; never log or persist plaintext.
    pharmapi_username = decrypt_credential(link.pharmapi_username or "")
    pharmapi_password = decrypt_credential(link.pharmapi_password or "")
    profile = await verify_pharmapi_credentials_with_decrypted(pharmapi_username, pharmapi_password)
    _start_pharmapi_session(profile)

    # JWT payload deliberately holds ids + email only — no creds, no profile.
    token = create_jwt(
        {
            "sub": str(pharmacist.id),
            "pharmacy_id": str(pharmacy.id),
            "email": pharmacist.email,
        }
    )
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        httponly=True,
        samesite="strict",
        secure=_cookie_secure(),
        max_age=COOKIE_MAX_AGE_SECONDS,
    )

    return LoginResponse(
        pharmacist_name=pharmacist.full_name,
        pharmacy=pharmacy.name,
        pharmacist_id=str(pharmacist.id),
        pharmacy_id=str(pharmacy.id),
    )


@router.post("/logout")
async def logout(response: Response) -> dict:
    """Clear the session cookie. Idempotent — safe to call without a cookie."""
    response.delete_cookie(
        key=COOKIE_NAME,
        httponly=True,
        samesite="strict",
        secure=_cookie_secure(),
    )
    return {"ok": True}


@router.get("/me", response_model=PharmacistMe)
async def me(current: dict = Depends(get_current_user)) -> PharmacistMe:
    return PharmacistMe(
        email=current["email"],
        name=current["name"],
        pharmacy=current["pharmacy"],
        pharmacist_id=current["pharmacist_id"],
        pharmacy_id=current["pharmacy_id"],
    )
