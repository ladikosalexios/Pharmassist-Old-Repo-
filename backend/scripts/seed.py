"""Seed PharmAssist's DB from a live Pharmapi (ΗΔΥΚΑ) /user/me response.

Authenticates with PHARMAPI_USERNAME/PHARMAPI_PASSWORD/PHARMAPI_API_KEY
from the environment, then materialises:
  - 1 Pharmacy   (from profile.pharmacy: name, address, tax_id, pharmapi_unit_id)
  - 1 Pharmacist (from profile: email, full_name, eof_licence_no, phone)
  - 1 PharmacistPharmacy link (Pharmapi creds AES-256-GCM-encrypted)
  - 1 PatientCondition (G6PD MODERATE, on the connected pharmacist's own AMKA)

Idempotent: TRUNCATEs the four seeded tables before insert so re-running
the script always yields a clean state. Local PharmAssist login password
is bcrypt(\"test1234\")."""
import asyncio, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import bcrypt
from sqlalchemy import text

from app.config import get_settings
from app.crypto import encrypt_credential
from app.db.models.patient_condition import PatientCondition
from app.db.models.pharmacist import Pharmacist
from app.db.models.pharmacist_pharmacy import PharmacistPharmacy
from app.db.models.pharmacy import Pharmacy
from app.db.session import AsyncSessionLocal
from app.services.pharmapi import verify_pharmapi_credentials

settings = get_settings()


def _full_name(name_obj) -> str:
    if isinstance(name_obj, dict):
        first = (name_obj.get("firstname") or "").strip()
        last = (name_obj.get("lastname") or "").strip()
        return f"{last} {first}".strip() or "Pharmacist"
    return str(name_obj or "Pharmacist")


async def seed():
    print(f"[seed] Authenticating to Pharmapi as {settings.pharmapi_username}...")
    profile = await verify_pharmapi_credentials(
        settings.pharmapi_username, settings.pharmapi_password
    )

    pharmacy_obj = profile.get("pharmacy") or {}
    if not isinstance(pharmacy_obj, dict):
        raise SystemExit("[seed] Pharmapi /user/me did not return a pharmacy object")

    pharmacy_name = pharmacy_obj.get("name") or "Unknown Pharmacy"
    pharmacy_unit_id = pharmacy_obj.get("id")
    if pharmacy_unit_id is None:
        raise SystemExit("[seed] Pharmapi /user/me pharmacy.id is missing — cannot seed")
    address = pharmacy_obj.get("address")
    postal = pharmacy_obj.get("postalCode")
    full_address = f"{(address or '').strip()} {postal or ''}".strip() or None
    tax_id = pharmacy_obj.get("taxRegistryNo")

    full_name = _full_name(profile.get("name"))
    email = profile.get("email") or f"{settings.pharmapi_username}@pharmapi.local"
    phone = profile.get("mobile")
    amka = profile.get("amka")
    pharmapi_user_id = profile.get("id")
    eof_licence_no = (
        profile.get("licenceNo")
        or profile.get("etaaRegNo")
        or (f"PHARMAPI-{pharmapi_user_id}" if pharmapi_user_id else None)
    )
    if not eof_licence_no:
        raise SystemExit("[seed] No usable EOF licence identifier in /user/me response")

    async with AsyncSessionLocal() as db:
        # Idempotent: wipe seeded tables before re-inserting. CASCADE clears
        # patient_conditions, pharmacist_pharmacies via FK chains.
        await db.execute(text(
            "TRUNCATE pharmacist_pharmacies, patient_conditions, pharmacists, pharmacies "
            "RESTART IDENTITY CASCADE"
        ))

        pharmacy = Pharmacy(
            name=pharmacy_name,
            address=full_address,
            tax_id=tax_id,
            pharmapi_unit_id=int(pharmacy_unit_id),
        )
        db.add(pharmacy)
        await db.flush()

        password_hash = bcrypt.hashpw(b"test1234", bcrypt.gensalt(rounds=12)).decode()
        pharmacist = Pharmacist(
            email=email,
            password_hash=password_hash,
            full_name=full_name,
            eof_licence_no=str(eof_licence_no),
            phone=phone,
            role="pharmacist",
        )
        db.add(pharmacist)
        await db.flush()

        link = PharmacistPharmacy(
            pharmacist_id=pharmacist.id,
            pharmacy_id=pharmacy.id,
            pharmapi_username=encrypt_credential(settings.pharmapi_username or ""),
            pharmapi_password=encrypt_credential(settings.pharmapi_password or ""),
            pharmapi_api_key=encrypt_credential(settings.pharmapi_api_key or ""),
            is_default=True,
        )
        db.add(link)

        if amka:
            db.add(PatientCondition(
                amka=amka,
                condition_code="G6PD",
                severity="MODERATE",
                notes="Seeded from Pharmapi /user/me — verify with patient on first visit",
                recorded_by=pharmacist.id,
                pharmacy_id=pharmacy.id,
            ))

        await db.commit()
        print("✓ Seed complete (sourced from Pharmapi /user/me)")
        print(f"  Pharmacy:   {pharmacy.id}  /  {pharmacy_name}  /  unit_id={pharmacy_unit_id}")
        print(f"  Pharmacist: {pharmacist.id}  /  {email}  /  {full_name}  /  test1234")
        print(f"  EOF licence: {eof_licence_no}")
        if amka:
            print(f"  Condition:   G6PD MODERATE on AMKA {amka}")


if __name__ == "__main__":
    asyncio.run(seed())
