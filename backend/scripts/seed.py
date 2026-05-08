import asyncio, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import bcrypt
from app.db.session import AsyncSessionLocal
from app.db.models.pharmacist import Pharmacist
from app.db.models.pharmacy import Pharmacy
from app.db.models.pharmacist_pharmacy import PharmacistPharmacy
from app.db.models.patient_condition import PatientCondition
from app.crypto import encrypt_credential
from app.config import get_settings

settings = get_settings()

async def seed():
    async with AsyncSessionLocal() as db:
        pharmacy = Pharmacy(name="PharmAssist Demo Pharmacy", address="Athens, Greece", tax_id="EL123456789", pharmapi_unit_id=1)
        db.add(pharmacy)
        await db.flush()

        password_hash = bcrypt.hashpw(b"test1234", bcrypt.gensalt(rounds=12)).decode()
        pharmacist = Pharmacist(email="pharmacist@pharmassist.gr", password_hash=password_hash, full_name="Test Pharmacist", eof_licence_no="EOF-TEST-001", role="pharmacist")
        db.add(pharmacist)
        await db.flush()

        link = PharmacistPharmacy(
            pharmacist_id=pharmacist.id, pharmacy_id=pharmacy.id,
            pharmapi_username=encrypt_credential(settings.pharmapi_username or ""),
            pharmapi_password=encrypt_credential(settings.pharmapi_password or ""),
            pharmapi_api_key=encrypt_credential(settings.pharmapi_api_key or ""),
            is_default=True,
        )
        db.add(link)

        condition = PatientCondition(amka="15031962456", condition_code="G6PD", severity="MODERATE", notes="Seeded from mock — verify with patient on first visit", recorded_by=pharmacist.id, pharmacy_id=pharmacy.id)
        db.add(condition)

        await db.commit()
        print("✓ Seed complete")
        print(f"  Pharmacy:   {pharmacy.id}")
        print(f"  Pharmacist: {pharmacist.id}  /  pharmacist@pharmassist.gr  /  test1234")

if __name__ == "__main__":
    asyncio.run(seed())
