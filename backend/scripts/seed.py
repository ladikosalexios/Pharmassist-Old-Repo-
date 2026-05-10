"""Seed PharmAssist's DB from a live Pharmapi (ΗΔΥΚΑ) /user/me response.

Authenticates with PHARMAPI_USERNAME/PHARMAPI_PASSWORD/PHARMAPI_API_KEY
from the environment, then materialises:
  - 1 Pharmacy   (from profile.pharmacy: name, address, tax_id, pharmapi_unit_id)
  - 1 Pharmacist (from profile: email, full_name, eof_licence_no, phone)
  - 1 PharmacistPharmacy link (Pharmapi creds AES-256-GCM-encrypted)
  - 1 PatientCondition (G6PD MODERATE, on the connected pharmacist's own AMKA)

Idempotent: TRUNCATEs the four seeded tables before insert so re-running
the script always yields a clean state.

Two distinct passwords are involved here, do not confuse them:
  * LOCAL_LOGIN_PASSWORD — what a pharmacist types into /auth/login on
    PharmAssist itself; bcrypt-hashed into pharmacists.password_hash.
  * settings.pharmapi_password — the ΗΔΥΚΑ Pharmapi credential used to
    call upstream APIs; AES-256-GCM-encrypted into
    pharmacist_pharmacies.pharmapi_password.
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dataclasses import dataclass

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

# Local PharmAssist login password for the seeded pharmacist account.
# DISTINCT from the Pharmapi password — see module docstring.
LOCAL_LOGIN_PASSWORD = b"test1234"


@dataclass(frozen=True)
class SeedProfile:
    """Validated extract of Pharmapi /user/me, ready to insert."""

    pharmacy_name: str
    pharmacy_unit_id: int
    pharmacy_address: str | None
    pharmacy_tax_id: str | None
    pharmacist_full_name: str
    pharmacist_email: str
    pharmacist_phone: str | None
    pharmacist_amka: str | None
    pharmacist_eof_licence_no: str


def _full_name(name_obj) -> str:
    if isinstance(name_obj, dict):
        first = (name_obj.get("firstname") or "").strip()
        last = (name_obj.get("lastname") or "").strip()
        return f"{last} {first}".strip() or "Pharmacist"
    return str(name_obj or "Pharmacist")


def _validate(profile: dict) -> SeedProfile:
    """Pull every field we need out of /user/me and fail fast if anything
    required is missing. Doing all this up front (vs scattered through
    seed()) means we either have a complete, ready-to-insert profile OR
    we exit cleanly — never a half-seeded DB."""
    pharmacy_obj = profile.get("pharmacy")
    if not isinstance(pharmacy_obj, dict):
        raise SystemExit("[seed] Pharmapi /user/me did not return a pharmacy object")

    pharmacy_unit_id = pharmacy_obj.get("id")
    if pharmacy_unit_id is None:
        raise SystemExit("[seed] Pharmapi /user/me pharmacy.id is missing — cannot seed")

    pharmapi_user_id = profile.get("id")
    eof_licence_no = (
        profile.get("licenceNo")
        or profile.get("etaaRegNo")
        or (f"PHARMAPI-{pharmapi_user_id}" if pharmapi_user_id else None)
    )
    if not eof_licence_no:
        raise SystemExit("[seed] No usable EOF licence identifier in /user/me response")

    address = pharmacy_obj.get("address")
    postal = pharmacy_obj.get("postalCode")
    full_address = f"{(address or '').strip()} {postal or ''}".strip() or None

    return SeedProfile(
        pharmacy_name=pharmacy_obj.get("name") or "Unknown Pharmacy",
        pharmacy_unit_id=int(pharmacy_unit_id),
        pharmacy_address=full_address,
        pharmacy_tax_id=pharmacy_obj.get("taxRegistryNo"),
        pharmacist_full_name=_full_name(profile.get("name")),
        pharmacist_email=profile.get("email") or f"{settings.pharmapi_username}@pharmapi.local",
        pharmacist_phone=profile.get("mobile"),
        pharmacist_amka=profile.get("amka"),
        pharmacist_eof_licence_no=str(eof_licence_no),
    )


async def seed():
    print(f"[seed] Authenticating to Pharmapi as {settings.pharmapi_username}...")
    raw_profile = await verify_pharmapi_credentials(
        settings.pharmapi_username, settings.pharmapi_password
    )
    p = _validate(raw_profile)

    async with AsyncSessionLocal() as db:
        # Idempotent: wipe seeded tables before re-inserting. CASCADE clears
        # patient_conditions, pharmacist_pharmacies via FK chains.
        await db.execute(
            text(
                "TRUNCATE pharmacist_pharmacies, patient_conditions, pharmacists, pharmacies "
                "RESTART IDENTITY CASCADE"
            )
        )

        pharmacy = Pharmacy(
            name=p.pharmacy_name,
            address=p.pharmacy_address,
            tax_id=p.pharmacy_tax_id,
            pharmapi_unit_id=p.pharmacy_unit_id,
        )
        db.add(pharmacy)
        await db.flush()

        # bcrypt of the LOCAL PharmAssist login password — what a pharmacist
        # types into /auth/login on this app. NOT the ΗΔΥΚΑ Pharmapi password
        # (that one lives encrypted on the link row below).
        local_password_hash = bcrypt.hashpw(
            LOCAL_LOGIN_PASSWORD, bcrypt.gensalt(rounds=12)
        ).decode()
        pharmacist = Pharmacist(
            email=p.pharmacist_email,
            password_hash=local_password_hash,
            full_name=p.pharmacist_full_name,
            eof_licence_no=p.pharmacist_eof_licence_no,
            phone=p.pharmacist_phone,
            role="pharmacist",
        )
        db.add(pharmacist)
        await db.flush()

        # Pharmapi (ΗΔΥΚΑ) credentials, AES-256-GCM-encrypted at rest under
        # CREDENTIAL_ENCRYPTION_KEY. These are what the backend uses to
        # call Pharmapi on this pharmacist's behalf.
        link = PharmacistPharmacy(
            pharmacist_id=pharmacist.id,
            pharmacy_id=pharmacy.id,
            pharmapi_username=encrypt_credential(settings.pharmapi_username or ""),
            pharmapi_password=encrypt_credential(settings.pharmapi_password or ""),
            pharmapi_api_key=encrypt_credential(settings.pharmapi_api_key or ""),
            is_default=True,
        )
        db.add(link)

        if p.pharmacist_amka:
            db.add(
                PatientCondition(
                    amka=p.pharmacist_amka,
                    condition_code="G6PD",
                    severity="MODERATE",
                    notes="Seeded from Pharmapi /user/me — verify with patient on first visit",
                    recorded_by=pharmacist.id,
                    pharmacy_id=pharmacy.id,
                )
            )

        await db.commit()
        print("✓ Seed complete (sourced from Pharmapi /user/me)")
        print(
            f"  Pharmacy:    {pharmacy.id}  /  {p.pharmacy_name}  /  unit_id={p.pharmacy_unit_id}"
        )
        print(
            f"  Pharmacist:  {pharmacist.id}  /  {p.pharmacist_email}  /  {p.pharmacist_full_name}"
        )
        print(f"  Local login: {p.pharmacist_email}  /  test1234   (PharmAssist /auth/login)")
        print(f"  EOF licence: {p.pharmacist_eof_licence_no}")
        if p.pharmacist_amka:
            print(f"  Condition:   G6PD MODERATE on AMKA {p.pharmacist_amka}")


if __name__ == "__main__":
    asyncio.run(seed())
