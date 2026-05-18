"""Seed PharmAssist's DB from a live Pharmapi (ΗΔΥΚΑ) /user/me response.

Authenticates with PHARMAPI_USERNAME/PHARMAPI_PASSWORD/PHARMAPI_API_KEY
from the environment, then materialises:
  - 1 Pharmacy   (from profile.pharmacy: name, address, tax_id, pharmapi_unit_id;
                  structured address/contact fields are static demo values)
  - 1 Pharmacist (from profile: email, full_name, eof_licence_no, phone)
  - 1 PharmacistPharmacy link (Pharmapi username + password, AES-256-GCM-encrypted)
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
import uuid

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dataclasses import dataclass
from datetime import datetime

import bcrypt
from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert

from app.config import get_settings
from app.crypto import encrypt_credential
from app.db.models.adr_report import AdrReport
from app.db.models.drug_catalog import DrugCatalog
from app.db.models.patient_condition import PatientCondition
from app.db.models.pharmacist import Pharmacist
from app.db.models.pharmacist_pharmacy import PharmacistPharmacy
from app.db.models.pharmacy import Pharmacy
from app.db.models.safety_rule import SafetyRule
from app.db.session import AsyncSessionLocal
from app.services.pharmapi import verify_pharmapi_credentials
from scripts.seed_data import (
    DRUG_CATALOG_DATA,
    PATIENT_CONDITION_DATA,
    SAFETY_RULES_DATA,
    SEED_ADR_REPORTS,
)

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


def seed_adr_report(report: dict, pharmacist_id: str, pharmacy_id: str) -> AdrReport:
    return AdrReport(
        pharmacist_id=pharmacist_id,
        pharmacy_id=pharmacy_id,
        patient_amka=report["patientId"],
        patient_name=report["patientName"],
        medicine_barcode=None,
        medicine_name=report["drugName"],
        atc_code=None,
        symptom_description=report["symptom"],
        onset_timing=report["onset"],
        severity=report["severity"],
        status=report["status"],
        eof_report_ref=None,
        reported_at=datetime.fromisoformat(report["reportedAt"]),
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
                "TRUNCATE pharmacist_pharmacies, patient_conditions, pharmacists, pharmacies, adr_reports RESTART IDENTITY CASCADE"  # noqa: E501
            )
        )

        pharmacy = Pharmacy(
            name=p.pharmacy_name,
            address=p.pharmacy_address,
            tax_id=p.pharmacy_tax_id,
            pharmapi_unit_id=p.pharmacy_unit_id,
            # Structured registration fields — Pharmapi /user/me does not
            # expose them, so they're hard-coded from a known test pharmacy
            # (sanctioned demo data, safe to commit).
            street_name="ΛΕΩΦΟΡΟΣ ΠΕΝΤΕΛΗΣ",
            street_number="138",
            area="ΧΑΛΑΝΔΡΙ",
            city="ΑΘΗΝΑ",
            postal_code="15234",
            phone="2106855263",
            fax="2106855272",
            email="mpempi24@otenet.gr",
            geographic_region="ΧΑΛΑΝΔΡΙ ΑΤΤΙΚΗ",
            accounting_category="B",
            is_branch=False,
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
            is_default=True,
        )
        db.add(link)

        # Conditions for engine-test prescriptions (RX-ENGINE-001/002/003).
        # Each condition triggers a contraindication rule in safety_rules.
        for condition in PATIENT_CONDITION_DATA:
            db.add(
                PatientCondition(
                    **condition,
                    recorded_by=pharmacist.id,
                    pharmacy_id=pharmacy.id,
                )
            )

        # commit records with no foreign keys
        await db.commit()

        for report in SEED_ADR_REPORTS:
            adr_report = seed_adr_report(report, pharmacist.id, pharmacy.id)
            db.add(adr_report)

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
        print("  Conditions:  PREGNANCY (22071993789), G6PD MODERATE (08111947033),")
        print("               RENAL_SEVERE (12101948112)")

    await seed_drug_catalog()
    await seed_safety_rules()


async def seed_drug_catalog():
    async with AsyncSessionLocal() as db:
        for drug in DRUG_CATALOG_DATA:
            stmt = (
                insert(DrugCatalog)
                .values(id=uuid.uuid4(), **drug)
                .on_conflict_do_nothing(index_elements=["gns_code"])
            )
            await db.execute(stmt)
        await db.commit()
    print(f"✓ drug_catalog seeded ({len(DRUG_CATALOG_DATA)} rows attempted, duplicates skipped)")


async def seed_safety_rules():
    async with AsyncSessionLocal() as db:
        for rule in SAFETY_RULES_DATA:
            stmt = (
                insert(SafetyRule)
                .values(id=uuid.uuid4(), **rule)
                .on_conflict_do_nothing(index_elements=["rule_code"])
            )
            await db.execute(stmt)
        await db.commit()
    print(f"✓ safety_rules seeded ({len(SAFETY_RULES_DATA)} rows attempted, duplicates skipped)")


if __name__ == "__main__":
    asyncio.run(seed())
