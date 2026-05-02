"""Pharmacist login + session info."""

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm

from ..deps import get_current_user
from ..schemas.auth import PharmacistMe, TokenResponse
from ..services.security import USERS, create_jwt, verify_password


router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
async def login(form: OAuth2PasswordRequestForm = Depends()):
    """
    Step 1: Pharmacist logs into PharmAssist.
    Demo: pharmacist@demo.gr / demo123
    Returns JWT for all subsequent calls.
    """
    user = USERS.get(form.username)
    if not user or not verify_password(form.password, user["pw_hash"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = create_jwt({"sub": form.username})
    return TokenResponse(
        access_token=token,
        pharmacist_name=user["name"],
        pharmacy=user["pharmacy"],
    )


@router.get("/me", response_model=PharmacistMe)
async def me(current: dict = Depends(get_current_user)):
    return PharmacistMe(email=current["email"], name=current["name"], pharmacy=current["pharmacy"])
