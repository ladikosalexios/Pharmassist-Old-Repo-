"""Non-destructive synthetic local account; never calls Pharmapi or wipes existing data."""

import asyncio

import bcrypt
from sqlalchemy import select

from app.config import get_settings
from app.db.models.pharmacist import Pharmacist
from app.db.models.pharmacist_pharmacy import PharmacistPharmacy
from app.db.models.pharmacy import Pharmacy
from app.db.session import AsyncSessionLocal


async def main():
    if get_settings().yellow_cards_mode != "local_capture":
        raise RuntimeError("Local capture mode required")
    async with AsyncSessionLocal() as db:
        if await db.scalar(select(Pharmacist).where(Pharmacist.email == "yellow.demo@example.com")):
            return
        pharmacy = Pharmacy(name="Δοκιμαστικό φαρμακείο", pharmapi_unit_id=0, active=True)
        pharmacist = Pharmacist(
            email="yellow.demo@example.com",
            password_hash=bcrypt.hashpw(b"Local-yellow-2026!", bcrypt.gensalt()).decode(),
            full_name="Δοκιμαστικός Φαρμακοποιός",
            eof_licence_no="SYNTHETIC-YELLOW",
            active=True,
        )
        db.add_all([pharmacy, pharmacist])
        await db.flush()
        db.add(
            PharmacistPharmacy(
                pharmacist_id=pharmacist.id, pharmacy_id=pharmacy.id, is_default=True
            )
        )
        await db.commit()


if __name__ == "__main__":
    asyncio.run(main())
