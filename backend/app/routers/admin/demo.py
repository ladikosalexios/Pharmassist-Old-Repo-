"""Demo / test-data seeder — NON-PRODUCTION tooling.

Populates a pharmacy with obviously-synthetic patient conditions, ADR reports,
and documentation entries so a demo or test environment has realistic data.
Intended for test/demo pharmacies only; re-running adds another sample set.
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...db.models.adr_report import AdrReport
from ...db.models.documentation_log import DocumentationLog
from ...db.models.patient_condition import PatientCondition
from ...db.models.pharmacist_pharmacy import PharmacistPharmacy
from ...db.models.pharmacy import Pharmacy
from ...db.session import get_session
from ...deps import get_current_staff
from ...schemas.admin import DemoSeedRequest, DemoSeedResponse
from ...services.audit import write_staff_audit

router = APIRouter()

# Synthetic sample data — test/demo use only.
_DEMO_CONDITIONS = [
    {
        "amka": "01018012345",
        "condition_code": "G6PD",
        "name": "G6PD Deficiency",
        "severity": "MODERATE",
    },
    {
        "amka": "02029098765",
        "condition_code": "PREGNANCY",
        "name": "Pregnancy",
        "severity": None,
    },
]
_DEMO_ADR = [
    {
        "patient_amka": "01018012345",
        "patient_name": "Demo Patient A",
        "medicine_name": "Demo Drug A",
        "symptom_description": "Mild rash after the first dose",
        "severity": "MILD",
    },
    {
        "patient_amka": "02029098765",
        "patient_name": "Demo Patient B",
        "medicine_name": "Demo Drug B",
        "symptom_description": "Nausea and dizziness",
        "severity": "MODERATE",
    },
]
_DEMO_DOCS = [
    {
        "action_type": "APPROVE",
        "prescription_barcode": "DEMO-RX-001",
        "patient_amka": "01018012345",
        "patient_name": "Demo Patient A",
        "medicine_name": "Demo Drug A",
        "info_provided": "Take with food",
        "delivery_method": "PRINT",
        "discrepancy_type": None,
        "notes": None,
    },
    {
        "action_type": "FLAG",
        "prescription_barcode": "DEMO-RX-002",
        "patient_amka": "02029098765",
        "patient_name": "Demo Patient B",
        "medicine_name": "Demo Drug B",
        "info_provided": None,
        "delivery_method": None,
        "discrepancy_type": "dose_error",
        "notes": "Dose exceeds the SPC maximum",
    },
]


@router.post("/demo/seed", response_model=DemoSeedResponse)
async def seed_demo_data(
    body: DemoSeedRequest,
    request: Request,
    current: dict = Depends(get_current_staff),
    db: AsyncSession = Depends(get_session),
) -> DemoSeedResponse:
    """Insert a sample set of clinical records for a pharmacy — demo/test only."""
    pharmacy = await db.get(Pharmacy, body.pharmacy_id)
    if pharmacy is None:
        raise HTTPException(404, "Pharmacy not found")

    # Clinical records need a pharmacist actor — use one linked to the pharmacy.
    link = await db.scalar(
        select(PharmacistPharmacy).where(PharmacistPharmacy.pharmacy_id == pharmacy.id)
    )
    if link is None:
        raise HTTPException(
            409, "Pharmacy has no pharmacist linked — onboard one before seeding demo data"
        )
    pharmacist_id = link.pharmacist_id

    for c in _DEMO_CONDITIONS:
        db.add(
            PatientCondition(
                amka=c["amka"],
                condition_code=c["condition_code"],
                name=c["name"],
                severity=c["severity"],
                recorded_by=pharmacist_id,
                pharmacy_id=pharmacy.id,
            )
        )
    for a in _DEMO_ADR:
        db.add(
            AdrReport(
                pharmacist_id=pharmacist_id,
                pharmacy_id=pharmacy.id,
                patient_amka=a["patient_amka"],
                patient_name=a["patient_name"],
                medicine_name=a["medicine_name"],
                symptom_description=a["symptom_description"],
                severity=a["severity"],
            )
        )
    for d in _DEMO_DOCS:
        db.add(
            DocumentationLog(
                pharmacist_id=pharmacist_id,
                pharmacy_id=pharmacy.id,
                action_type=d["action_type"],
                prescription_barcode=d["prescription_barcode"],
                patient_amka=d["patient_amka"],
                patient_name=d["patient_name"],
                medicine_name=d["medicine_name"],
                info_provided=d["info_provided"],
                delivery_method=d["delivery_method"],
                discrepancy_type=d["discrepancy_type"],
                notes=d["notes"],
                safety_check_snapshot=[],
                pharmacist_signature="DEMO-SEED",
            )
        )

    write_staff_audit(
        db,
        staff_id=current["staff_id"],
        action="demo.seed",
        resource_type="pharmacy",
        resource_id=str(pharmacy.id),
        pharmacy_id=str(pharmacy.id),
        request=request,
    )
    await db.commit()
    return DemoSeedResponse(
        pharmacy_id=pharmacy.id,
        patient_conditions=len(_DEMO_CONDITIONS),
        adr_reports=len(_DEMO_ADR),
        documentation_logs=len(_DEMO_DOCS),
    )
