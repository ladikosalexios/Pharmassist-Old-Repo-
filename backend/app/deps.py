"""Shared FastAPI dependencies.

Routers import ``get_current_user`` from here instead of from main.py — that
way main.py can include routers without each router pulling main back in
(circular-import bait).

ADR-003: the session JWT is read from a httpOnly ``pharmassist_session``
cookie, never from an Authorization header.
"""

import uuid

from fastapi import Cookie, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .db.models.pharmacist import Pharmacist
from .db.models.pharmacist_pharmacy import PharmacistPharmacy
from .db.models.pharmacy import Pharmacy
from .db.session import get_session
from .services.security import decode_jwt


async def get_identity(
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

    link = await db.scalar(
        select(PharmacistPharmacy).where(
            PharmacistPharmacy.pharmacist_id == uuid.UUID(pharmacist_id),
            PharmacistPharmacy.pharmacy_id == uuid.UUID(pharmacy_id),
        )
    )
    if link is None:
        raise HTTPException(401, "Pharmacy membership no longer exists")
    return {
        "scope": payload.get("scope", "full"),
        "pharmacist_id": str(pharmacist.id),
        "pharmacy_id": str(pharmacy.id),
        "email": pharmacist.email,
        "name": pharmacist.full_name,
        "eof_licence_no": pharmacist.eof_licence_no,
        "pharmacy": pharmacy.name,
        "role": pharmacist.role,
    }


async def get_current_user(current: dict = Depends(get_identity)) -> dict:
    if current.get("scope", "full") != "full":
        raise HTTPException(403, "Reporting session cannot access the prescription workspace")
    return current
