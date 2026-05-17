"""Staff authentication for the admin portal.

Separate from /auth — staff sign in against the staff_users table and get a
distinct `pharmassist_admin_session` cookie. The JWT carries `typ: "staff"`.
"""

from datetime import UTC, datetime

import bcrypt
from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...db.models.staff_user import StaffUser
from ...db.session import get_session
from ...deps import get_current_staff
from ...schemas.admin import StaffLoginRequest, StaffLoginResponse, StaffMe
from ...services.cookies import COOKIE_MAX_AGE_SECONDS, cookie_secure
from ...services.security import create_jwt

router = APIRouter()

ADMIN_COOKIE_NAME = "pharmassist_admin_session"

# Constant-time login: always pay one bcrypt verify so unknown-email and
# wrong-password requests take the same wall-clock time (mirrors auth.py).
_DUMMY_PASSWORD_HASH: str = bcrypt.hashpw(
    b"unused-dummy-for-constant-time-admin-login", bcrypt.gensalt(rounds=12)
).decode()


@router.post("/login", response_model=StaffLoginResponse)
async def staff_login(
    body: StaffLoginRequest,
    response: Response,
    db: AsyncSession = Depends(get_session),
) -> StaffLoginResponse:
    """Authenticate a company staff member and issue the admin session cookie."""
    staff = await db.scalar(
        select(StaffUser).where(
            StaffUser.email == body.email,
            StaffUser.active.is_(True),
        )
    )
    password_hash = staff.password_hash if staff is not None else _DUMMY_PASSWORD_HASH
    password_ok = bcrypt.checkpw(body.password.encode(), password_hash.encode())
    if staff is None or not password_ok:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    staff.last_login_at = datetime.now(UTC)
    await db.commit()

    token = create_jwt({"sub": str(staff.id), "email": staff.email, "typ": "staff"})
    response.set_cookie(
        key=ADMIN_COOKIE_NAME,
        value=token,
        httponly=True,
        samesite="strict",
        secure=cookie_secure(),
        max_age=COOKIE_MAX_AGE_SECONDS,
        path="/",
    )
    return StaffLoginResponse(
        staff_id=str(staff.id), name=staff.full_name, email=staff.email, role=staff.role
    )


@router.post("/logout")
async def staff_logout(response: Response) -> dict:
    """Clear the admin session cookie. Idempotent — safe without a cookie."""
    response.delete_cookie(
        key=ADMIN_COOKIE_NAME,
        httponly=True,
        samesite="strict",
        secure=cookie_secure(),
        path="/",
    )
    return {"ok": True}


@router.get("/me", response_model=StaffMe)
async def staff_me(current: dict = Depends(get_current_staff)) -> StaffMe:
    return StaffMe(
        staff_id=current["staff_id"],
        name=current["name"],
        email=current["email"],
        role=current["role"],
    )
