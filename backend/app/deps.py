"""Shared FastAPI dependencies.

Routers import ``get_current_user`` from here instead of from main.py — that
way main.py can include routers without each router pulling main back in
(circular-import bait).

ADR-003: the session JWT is read from a httpOnly ``pharmassist_session``
cookie, never from an Authorization header.
"""

from fastapi import Cookie, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from .db.models.pharmacist import Pharmacist
from .db.models.pharmacy import Pharmacy
from .db.models.staff_user import StaffUser
from .db.session import get_session
from .services.security import decode_jwt


async def get_current_user(
    session_token: str | None = Cookie(default=None, alias="pharmassist_session"),
    db: AsyncSession = Depends(get_session),
) -> dict:
    if not session_token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    payload = decode_jwt(session_token)
    pharmacist_id = payload.get("sub")
    pharmacy_id = payload.get("pharmacy_id")
    if not pharmacist_id or not pharmacy_id:
        raise HTTPException(status_code=401, detail="Invalid session payload")

    # `Base.get_by_id` handles str→UUID coercion; the `active` predicate stays
    # inline because `get_by_id` doesn't filter on it.
    pharmacist = await Pharmacist.get_by_id(db, pharmacist_id)
    if pharmacist is None or not pharmacist.active:
        raise HTTPException(status_code=401, detail="User not found")

    pharmacy = await Pharmacy.get_by_id(db, pharmacy_id)
    if pharmacy is None:
        raise HTTPException(status_code=401, detail="Pharmacy not found")

    return {
        "pharmacist_id": str(pharmacist.id),
        "pharmacy_id": str(pharmacy.id),
        "email": pharmacist.email,
        "name": pharmacist.full_name,
        "pharmacy": pharmacy.name,
        "role": pharmacist.role,
    }


async def get_current_staff(
    session_token: str | None = Cookie(default=None, alias="pharmassist_admin_session"),
    db: AsyncSession = Depends(get_session),
) -> dict:
    """Resolve the current company staff member from the admin session cookie.

    Separate from `get_current_user` — different cookie, different table. The
    `typ: "staff"` JWT claim stops a pharmacist token being replayed here, and
    staff tokens omit `pharmacy_id` so they fail `get_current_user` in turn.
    """
    if not session_token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    payload = decode_jwt(session_token)
    staff_id = payload.get("sub")
    if not staff_id or payload.get("typ") != "staff":
        raise HTTPException(status_code=401, detail="Invalid session payload")

    staff = await StaffUser.get_by_id(db, staff_id)
    if staff is None or not staff.active:
        raise HTTPException(status_code=401, detail="Staff account not found")

    return {
        "staff_id": str(staff.id),
        "email": staff.email,
        "name": staff.full_name,
        "role": staff.role,
    }
