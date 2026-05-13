"""Pharmacist login + session info."""

from fastapi import APIRouter, Depends
from fastapi.security import OAuth2PasswordRequestForm

from ..deps import get_current_user
from ..schemas.auth import PharmacistMe, TokenResponse
from ..services.pharmapi import _start_pharmapi_session, verify_pharmapi_credentials
from ..services.security import USERS, create_jwt

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
async def login(form: OAuth2PasswordRequestForm = Depends()):
    """Validate credentials live against Pharmapi GET /api/v1/user/me.

    On success: cache the profile, pin the 24h Pharmapi session, and
    return a JWT for subsequent calls.
    """
    profile = await verify_pharmapi_credentials(form.username, form.password)

    pharmacist_email = profile.get("email") or f"{form.username}@pharmapi.local"

    name_obj = profile.get("name", {})
    pharmacist_name = (
        f"{name_obj.get('firstname', '')} {name_obj.get('lastname', '')}".strip()
        if isinstance(name_obj, dict)
        else str(name_obj)
    ) or form.username

    pharmacy_obj = profile.get("pharmacy", {})
    pharmacy_name = (
        pharmacy_obj.get("name", "") if isinstance(pharmacy_obj, dict) else str(pharmacy_obj)
    )

    USERS[pharmacist_email] = {"name": pharmacist_name, "pharmacy": pharmacy_name}
    _start_pharmapi_session(profile)

    token = create_jwt({"sub": pharmacist_email})
    return TokenResponse(
        access_token=token,
        pharmacist_name=pharmacist_name,
        pharmacy=pharmacy_name,
    )


@router.get("/me", response_model=PharmacistMe)
async def me(current: dict = Depends(get_current_user)):
    return PharmacistMe(email=current["email"], name=current["name"], pharmacy=current["pharmacy"])
