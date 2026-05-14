"""Shared FastAPI dependencies.

Routers import ``get_current_user`` from here instead of from main.py — that
way main.py can include routers without each router pulling main back in
(circular-import bait).

ADR-003: the session JWT is read from a httpOnly ``pharmassist_session``
cookie, never from an Authorization header.
"""

from fastapi import Cookie, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .db.models.pharmacist import Pharmacist
from .db.models.pharmacy import Pharmacy
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

    pharmacist = await db.scalar(
        select(Pharmacist).where(
            Pharmacist.id == pharmacist_id,
            Pharmacist.active.is_(True),
        )
    )
    if pharmacist is None:
        raise HTTPException(status_code=401, detail="User not found")

    pharmacy = await db.scalar(select(Pharmacy).where(Pharmacy.id == pharmacy_id))
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
