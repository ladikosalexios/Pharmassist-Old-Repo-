"""Patient profiles + per-patient prescription / ADR history.

Reads live status from the prescriptions service for any rxId that has a full
record there, so flag/approve actions on the verification page show up
immediately in a patient's history.
"""

import asyncio
import logging
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.patient_condition import PatientCondition
from app.services.pharmapi import (
    _date,
    _map_pharmapi_status,
    pharmapi_get_patient,
    pharmapi_get_patient_intolerances,
    pharmapi_get_patient_medicine_history,
)
from app.utils.environment import is_mock_pharmapi

from ..constants import PrescriptionStatus
from .prescriptions import MOCK_PRESCRIPTIONS
from .side_effects import MOCK_SIDE_EFFECTS

logger = logging.getLogger(__name__)

PATIENT_PROFILES: dict = {
    "P001": {
        "id": "P001",
        "amka": "15031962456",
        "firstName": "Maria",
        "lastName": "Stavrou",
        "name": "Maria Stavrou",
        "dateOfBirth": "1962-03-15",
        "age": 64,
        "sex": "F",
        "phone": "+30 694 312 3456",
        "nationality": "Ελληνική",
        "address": "Αριστοτέλους 22, Θεσσαλονίκη 546 24",
        "conditions": ["Type II Diabetes", "Hypertension", "Hyperlipidemia"],
        "allergies": ["Penicillin (anaphylaxis)", "Sulfa drugs"],
        "intolerances": ["Lactose"],
        "safetyFlags": {
            "g6pd": False,
            "pregnancyWeeks": None,
            "renalFunction": "MILD_IMPAIRMENT",
            "hepaticFunction": "NORMAL",
            "breastfeeding": False,
        },
    },
    "P004": {
        "id": "P004",
        "amka": "08111974201",
        "firstName": "Eleni",
        "lastName": "Papadopoulos",
        "name": "Eleni Papadopoulos",
        "dateOfBirth": "1974-11-08",
        "age": 51,
        "sex": "F",
        "phone": "+30 697 555 0142",
        "nationality": "Ελληνική",
        "address": "Εγνατία 88, Θεσσαλονίκη 546 22",
        "conditions": ["Atrial fibrillation"],
        "allergies": [],
        "intolerances": [],
        "safetyFlags": {
            "g6pd": False,
            "pregnancyWeeks": None,
            "renalFunction": "NORMAL",
            "hepaticFunction": "NORMAL",
            "breastfeeding": False,
        },
    },
    "P010": {
        "id": "P010",
        "amka": "22071993789",
        "firstName": "Sarah",
        "lastName": "Johnson",
        "name": "Sarah Johnson",
        "dateOfBirth": "1993-07-22",
        "age": 32,
        "sex": "F",
        "phone": "+30 698 011 2233",
        "nationality": "Βρετανική",
        "address": "Μητροπόλεως 15, Θεσσαλονίκη 546 21",
        "conditions": ["Bacterial sinusitis"],
        "allergies": [],
        "intolerances": [],
        "safetyFlags": {
            "g6pd": False,
            "pregnancyWeeks": 18,
            "renalFunction": "NORMAL",
            "hepaticFunction": "NORMAL",
            "breastfeeding": False,
        },
    },
    "P012": {
        "id": "P012",
        "amka": "03051961334",
        "firstName": "Dimitrios",
        "lastName": "Konstantinou",
        "name": "Dimitrios Konstantinou",
        "dateOfBirth": "1961-05-03",
        "age": 64,
        "sex": "M",
        "phone": "+30 698 555 7012",
        "nationality": "Ελληνική",
        "address": "Αγίου Δημητρίου 41, Θεσσαλονίκη 546 25",
        "conditions": ["Hyperlipidemia", "Coronary artery disease"],
        "allergies": [],
        "intolerances": [],
        "safetyFlags": {
            "g6pd": False,
            "pregnancyWeeks": None,
            "renalFunction": "NORMAL",
            "hepaticFunction": "MODERATE_IMPAIRMENT",
            "breastfeeding": False,
        },
    },
    "P020": {
        "id": "P020",
        "amka": "12101948112",
        "firstName": "Anna",
        "lastName": "Kostas",
        "name": "Anna Kostas",
        "dateOfBirth": "1948-10-12",
        "age": 77,
        "sex": "F",
        "phone": "+30 697 999 0011",
        "nationality": "Ελληνική",
        "address": "Τσιμισκή 67, Θεσσαλονίκη 546 23",
        "conditions": ["Coronary stent (2025)", "Atrial fibrillation"],
        "allergies": [],
        "intolerances": [],
        "safetyFlags": {
            "g6pd": False,
            "pregnancyWeeks": None,
            "renalFunction": "MODERATE_IMPAIRMENT",
            "hepaticFunction": "NORMAL",
            "breastfeeding": False,
        },
    },
    "P031": {
        "id": "P031",
        "amka": "27021982557",
        "firstName": "Nikos",
        "lastName": "Vlachos",
        "name": "Nikos Vlachos",
        "dateOfBirth": "1982-02-27",
        "age": 43,
        "sex": "M",
        "phone": "+30 698 222 0099",
        "nationality": "Ελληνική",
        "address": "Βενιζέλου 9, Θεσσαλονίκη 546 31",
        "conditions": ["Type II Diabetes"],
        "allergies": ["Aspirin (urticaria)"],
        "intolerances": [],
        "safetyFlags": {
            "g6pd": True,
            "pregnancyWeeks": None,
            "renalFunction": "NORMAL",
            "hepaticFunction": "NORMAL",
            "breastfeeding": False,
        },
    },
    "P024": {
        "id": "P024",
        "amka": "03091954221",
        "firstName": "James",
        "lastName": "Martinez",
        "name": "James Martinez",
        "dateOfBirth": "1954-09-03",
        "age": 71,
        "sex": "M",
        "phone": "+30 693 412 7801",
        "nationality": "Αμερικανική",
        "address": "Πλατεία Αριστοτέλους 3, Θεσσαλονίκη 546 24",
        "conditions": ["Atrial fibrillation", "Hypertension"],
        "allergies": [],
        "intolerances": [],
        "safetyFlags": {
            "g6pd": False,
            "pregnancyWeeks": None,
            "renalFunction": "MILD_IMPAIRMENT",
            "hepaticFunction": "NORMAL",
            "breastfeeding": False,
        },
    },
    "P033": {
        "id": "P033",
        "amka": "19011968147",
        "firstName": "Maria",
        "lastName": "Garcia",
        "name": "Maria Garcia",
        "dateOfBirth": "1968-01-19",
        "age": 58,
        "sex": "F",
        "phone": "+30 694 881 3302",
        "nationality": "Ελληνική",
        "address": "Φιλίππου 28, Θεσσαλονίκη 546 40",
        "conditions": ["Hypertension"],
        "allergies": [],
        "intolerances": [],
        "safetyFlags": {
            "g6pd": False,
            "pregnancyWeeks": None,
            "renalFunction": "NORMAL",
            "hepaticFunction": "NORMAL",
            "breastfeeding": False,
        },
    },
    "P040": {
        "id": "P040",
        "amka": "08111947033",
        "firstName": "Nikos",
        "lastName": "Papadopoulos",
        "name": "Nikos Papadopoulos",
        "dateOfBirth": "1947-11-08",
        "age": 78,
        "sex": "M",
        "phone": "+30 697 630 9415",
        "nationality": "Ελληνική",
        "address": "Γεωργίου Παπανδρέου 14, Θεσσαλονίκη 564 30",
        "conditions": ["Type II Diabetes", "G6PD deficiency (moderate)"],
        "allergies": [],
        "intolerances": [],
        "safetyFlags": {
            "g6pd": True,
            "pregnancyWeeks": None,
            "renalFunction": "MILD_IMPAIRMENT",
            "hepaticFunction": "NORMAL",
            "breastfeeding": False,
        },
    },
    "P051": {
        "id": "P051",
        "amka": "26061980554",
        "firstName": "Eleni",
        "lastName": "Demetriou",
        "name": "Eleni Demetriou",
        "dateOfBirth": "1980-06-26",
        "age": 45,
        "sex": "F",
        "phone": "+30 698 274 6103",
        "nationality": "Ελληνική",
        "address": "Νίκης 50, Θεσσαλονίκη 546 22",
        "conditions": ["Hyperlipidemia"],
        "allergies": [],
        "intolerances": [],
        "safetyFlags": {
            "g6pd": False,
            "pregnancyWeeks": None,
            "renalFunction": "NORMAL",
            "hepaticFunction": "NORMAL",
            "breastfeeding": False,
        },
    },
    "P062": {
        "id": "P062",
        "amka": "14081996228",
        "firstName": "Andreas",
        "lastName": "Vasilakis",
        "name": "Andreas Vasilakis",
        "dateOfBirth": "1996-08-14",
        "age": 29,
        "sex": "M",
        "phone": "+30 699 103 5820",
        "nationality": "Ελληνική",
        "address": "Κ. Καρτάλη 33, Θεσσαλονίκη 546 46",
        "conditions": ["Recent ACS (3 months ago)", "Reflux"],
        "allergies": [],
        "intolerances": [],
        "safetyFlags": {
            "g6pd": False,
            "pregnancyWeeks": None,
            "renalFunction": "NORMAL",
            "hepaticFunction": "NORMAL",
            "breastfeeding": False,
        },
    },
    "P078": {
        "id": "P078",
        "amka": "04092017819",
        "firstName": "Sofia",
        "lastName": "Ioannidou",
        "name": "Sofia Ioannidou",
        "dateOfBirth": "2017-09-04",
        "age": 8,
        "sex": "F",
        "phone": "+30 694 500 1122",
        "nationality": "Ελληνική",
        "address": "Αγίας Σοφίας 8, Θεσσαλονίκη 546 22",
        "conditions": ["Acute otitis media"],
        "allergies": [],
        "intolerances": [],
        "safetyFlags": {
            "g6pd": False,
            "pregnancyWeeks": None,
            "renalFunction": "NORMAL",
            "hepaticFunction": "NORMAL",
            "breastfeeding": False,
        },
    },
}


# Static prescription history per patient (additional rxs that aren't part of
# the verification mock). The current status of any rx that is also seeded in
# MOCK_PRESCRIPTIONS is overlaid live so flag/approve actions reflect.
PATIENT_RX_HISTORY_BASE: dict = {
    "P001": [
        {
            "rxId": "RX2024-005",
            "date": "2026-04-28",
            "drugName": "Warfarin 5 mg",
            "prescriberName": "Dr. Michael Chen",
            "status": PrescriptionStatus.PENDING,
        },
        # RX-HIST-001/002 trigger WARFARIN_ASPIRIN_BLEED + WARFARIN_AMIODARONE_INTERACTION
        # against Maria's pending Warfarin (RX2024-005).
        {
            "rxId": "RX-HIST-001",
            "date": "2025-12-04",
            "drugName": "Aspirin 100 mg",
            "prescriberName": "Dr. Michael Chen",
            "status": PrescriptionStatus.COMPLETED,
        },
        {
            "rxId": "RX-HIST-002",
            "date": "2025-10-21",
            "drugName": "Amiodarone 200 mg",
            "prescriberName": "Dr. Michael Chen",
            "status": PrescriptionStatus.COMPLETED,
        },
        {
            "rxId": "RX2023-118",
            "date": "2025-11-12",
            "drugName": "Atorvastatin 20 mg",
            "prescriberName": "Dr. Michael Chen",
            "status": PrescriptionStatus.COMPLETED,
        },
        {
            "rxId": "RX2023-077",
            "date": "2025-09-03",
            "drugName": "Metformin 1000 mg",
            "prescriberName": "Dr. Maria Lampraki",
            "status": PrescriptionStatus.COMPLETED,
        },
        {
            "rxId": "RX2023-022",
            "date": "2025-04-19",
            "drugName": "Ramipril 5 mg",
            "prescriberName": "Dr. Maria Lampraki",
            "status": PrescriptionStatus.COMPLETED,
        },
    ],
    "P004": [
        {
            "rxId": "RX2024-002",
            "date": "2026-03-11",
            "drugName": "Warfarin 7.5 mg",
            "prescriberName": "Dr. Emily Roberts",
            "status": PrescriptionStatus.FLAGGED,
        },
        {
            "rxId": "RX2023-054",
            "date": "2025-08-20",
            "drugName": "Bisoprolol 5 mg",
            "prescriberName": "Dr. Emily Roberts",
            "status": PrescriptionStatus.COMPLETED,
        },
    ],
    "P010": [
        {
            "rxId": "RX-ENGINE-001",
            "date": "2026-05-14",
            "drugName": "Warfarin 5 mg",
            "prescriberName": "Dr. Michael Chen",
            "status": PrescriptionStatus.PENDING,
        },
        {
            "rxId": "RX2024-001",
            "date": "2026-03-11",
            "drugName": "Amoxicillin 500 mg",
            "prescriberName": "Dr. Michael Chen",
            "status": PrescriptionStatus.PENDING,
        },
        # RX-HIST-003 triggers WARFARIN_ASPIRIN_BLEED against Sarah's pending Warfarin.
        {
            "rxId": "RX-HIST-003",
            "date": "2026-02-18",
            "drugName": "Aspirin 75 mg",
            "prescriberName": "Dr. Michael Chen",
            "status": PrescriptionStatus.COMPLETED,
        },
    ],
    "P012": [
        {
            "rxId": "RX2023-091",
            "date": "2025-12-08",
            "drugName": "Atorvastatin 20 mg",
            "prescriberName": "Dr. David Lee",
            "status": PrescriptionStatus.COMPLETED,
        },
        {
            "rxId": "RX2023-044",
            "date": "2025-06-14",
            "drugName": "Aspirin 100 mg",
            "prescriberName": "Dr. David Lee",
            "status": PrescriptionStatus.COMPLETED,
        },
    ],
    "P020": [
        {
            "rxId": "RX-ENGINE-003",
            "date": "2026-05-14",
            "drugName": "Metformin 500 mg",
            "prescriberName": "Dr. Elena Stavros",
            "status": PrescriptionStatus.PENDING,
        },
        {
            "rxId": "RX2023-066",
            "date": "2025-09-30",
            "drugName": "Clopidogrel 75 mg",
            "prescriberName": "Dr. Sophia Roussou",
            "status": PrescriptionStatus.COMPLETED,
        },
    ],
    "P031": [
        {
            "rxId": "RX2023-032",
            "date": "2025-05-18",
            "drugName": "Metformin 1000 mg",
            "prescriberName": "Dr. Niko Pateli",
            "status": PrescriptionStatus.COMPLETED,
        },
    ],
    "P024": [
        {
            "rxId": "RX2024-002",
            "date": "2026-04-12",
            "drugName": "Warfarin 7.5 mg",
            "prescriberName": "Dr. Emily Roberts",
            "status": PrescriptionStatus.FLAGGED,
        },
        {
            "rxId": "RX2023-041",
            "date": "2025-07-18",
            "drugName": "Bisoprolol 5 mg",
            "prescriberName": "Dr. Emily Roberts",
            "status": PrescriptionStatus.COMPLETED,
        },
    ],
    "P033": [
        {
            "rxId": "RX2024-003",
            "date": "2026-03-22",
            "drugName": "Lisinopril 10 mg",
            "prescriberName": "Dr. David Lee",
            "status": PrescriptionStatus.PENDING,
        },
        {
            "rxId": "RX2023-055",
            "date": "2025-09-10",
            "drugName": "Amlodipine 5 mg",
            "prescriberName": "Dr. David Lee",
            "status": PrescriptionStatus.COMPLETED,
        },
    ],
    "P040": [
        {
            "rxId": "RX-ENGINE-002",
            "date": "2026-05-14",
            "drugName": "Aspirin 100 mg",
            "prescriberName": "Dr. Anna Kostas",
            "status": PrescriptionStatus.PENDING,
        },
        {
            "rxId": "RX2024-006",
            "date": "2026-05-02",
            "drugName": "Metformin 850 mg",
            "prescriberName": "Dr. Anna Kostas",
            "status": PrescriptionStatus.PENDING,
        },
        {
            "rxId": "RX2023-088",
            "date": "2025-11-04",
            "drugName": "Glipizide 5 mg",
            "prescriberName": "Dr. Anna Kostas",
            "status": PrescriptionStatus.COMPLETED,
        },
        # RX-HIST-004 triggers CLOPIDOGREL_ASPIRIN_DUPLICATE against Nikos's
        # pending Aspirin (RX-ENGINE-002).
        {
            "rxId": "RX-HIST-004",
            "date": "2025-08-09",
            "drugName": "Clopidogrel 75 mg",
            "prescriberName": "Dr. Anna Kostas",
            "status": PrescriptionStatus.COMPLETED,
        },
    ],
    "P051": [
        {
            "rxId": "RX2024-007",
            "date": "2026-04-19",
            "drugName": "Atorvastatin 40 mg",
            "prescriberName": "Dr. Michael Chen",
            "status": PrescriptionStatus.COMPLETED,
        },
        {
            "rxId": "RX2023-063",
            "date": "2025-10-08",
            "drugName": "Atorvastatin 20 mg",
            "prescriberName": "Dr. Michael Chen",
            "status": PrescriptionStatus.COMPLETED,
        },
    ],
    "P062": [
        {
            "rxId": "RX2024-008",
            "date": "2026-05-03",
            "drugName": "Clopidogrel 75 mg",
            "prescriberName": "Dr. Emily Roberts",
            "status": PrescriptionStatus.PENDING,
        },
        {
            "rxId": "RX2024-004",
            "date": "2026-02-08",
            "drugName": "Aspirin 100 mg",
            "prescriberName": "Dr. Emily Roberts",
            "status": PrescriptionStatus.COMPLETED,
        },
    ],
    "P078": [
        {
            "rxId": "RX2024-009",
            "date": "2026-05-05",
            "drugName": "Amoxicillin 250 mg/5 mL",
            "prescriberName": "Dr. Kostas Manolas",
            "status": PrescriptionStatus.PENDING,
        },
    ],
}


def _map_history_item(item: dict) -> dict:
    return {
        "rxId": item.get("prescriptionBarcode"),
        "date": _date(item.get("prescriptionExecutionDate")),
        "drugName": item.get("medicineCommercialName"),
        "prescriberName": None,
        "status": _map_pharmapi_status(item.get("prescriptionStatusDesc")),
        "quantityPrescribed": item.get("quantityPrescribed"),
        "quantityOutstanding": item.get("quantityOutstanding"),
        "euDispensed": str(item.get("euDispensed", "")).lower() == "true",
    }


def _mock_rx_rows(patient_id: str) -> list:
    rows = [dict(r) for r in PATIENT_RX_HISTORY_BASE.get(patient_id, [])]
    for row in rows:
        live = MOCK_PRESCRIPTIONS.get(row["rxId"])
        if live and live.get("status"):
            row["status"] = live["status"]
    rows.sort(key=lambda r: r["date"], reverse=True)
    return rows


async def rx_history(patient_id: str) -> list:
    """Flat list of history items — used by the safety engine for ATC lookups."""
    if not is_mock_pharmapi():
        data = await pharmapi_get_patient_medicine_history(patient_id)
        return [_map_history_item(item) for item in data.get("items", [])]
    return _mock_rx_rows(patient_id)


async def rx_history_page(patient_id: str, page: int = 0, size: int = 50) -> dict:
    """Paginated prescription history for the patient profile tab.

    Returns the Pharmapi pagination envelope plus a `blocked` flag that is
    True when error 609 prevents access (pharmacy not yet permissioned).
    Mock mode returns the full fixture wrapped in a single-page envelope.
    """
    if not is_mock_pharmapi():
        data = await pharmapi_get_patient_medicine_history(patient_id, page=page, size=size)
        return {
            "items": [_map_history_item(i) for i in data.get("items", [])],
            "page": page,
            "totalPages": data.get("totalPages", 1),
            "lastPage": data.get("lastPage", True),
            "totalEntries": data.get("totalEntries", 0),
            "blocked": data.get("blocked", False),
        }
    rows = _mock_rx_rows(patient_id)
    return {
        "items": rows,
        "page": page,
        "totalPages": 1,
        "lastPage": True,
        "totalEntries": len(rows),
        "blocked": False,
    }


def adr_history(patient_id: str) -> list:
    rows = [r for r in MOCK_SIDE_EFFECTS if r["patientId"] == patient_id]
    rows.sort(key=lambda r: r["reportedAt"], reverse=True)
    return rows


async def conditions(session: AsyncSession, amka: str, pharmacy_id: uuid.UUID) -> list:
    """Active conditions recorded for a patient at this pharmacy.

    Soft-deleted rows (active=false) are excluded so a removed condition stops
    powering both this list and the safety engine's contraindication checks.
    """
    return (
        await session.scalars(
            select(PatientCondition)
            .where(
                PatientCondition.amka == amka,
                PatientCondition.pharmacy_id == pharmacy_id,
                PatientCondition.active.is_(True),
            )
            .order_by(PatientCondition.created_at.desc())
        )
    ).all()


async def get_condition(
    session: AsyncSession,
    condition_id: uuid.UUID,
    amka: str,
    pharmacy_id: uuid.UUID,
) -> PatientCondition | None:
    """Fetch a single active condition scoped to the patient + pharmacy.

    Scoping by amka + pharmacy_id stops one pharmacy editing or removing a
    condition that belongs to another pharmacy's record for the same patient.
    """
    return (
        await session.scalars(
            select(PatientCondition).where(
                PatientCondition.id == condition_id,
                PatientCondition.amka == amka,
                PatientCondition.pharmacy_id == pharmacy_id,
                PatientCondition.active.is_(True),
            )
        )
    ).one_or_none()


async def create_condition(
    session: AsyncSession,
    *,
    amka: str,
    condition_code: str,
    name: str,
    severity: str | None,
    notes: str | None,
    recorded_by: uuid.UUID,
    pharmacy_id: uuid.UUID,
) -> PatientCondition:
    condition = PatientCondition(
        amka=amka,
        condition_code=condition_code,
        name=name,
        severity=severity,
        notes=notes,
        recorded_by=recorded_by,
        pharmacy_id=pharmacy_id,
        active=True,
    )
    session.add(condition)
    await session.commit()
    await session.refresh(condition)
    return condition


async def update_condition(
    session: AsyncSession,
    condition: PatientCondition,
    *,
    fields: dict,
) -> PatientCondition:
    """Apply a partial update. `fields` holds only the keys the caller sent."""
    for key, value in fields.items():
        setattr(condition, key, value)
    await session.commit()
    await session.refresh(condition)
    return condition


async def deactivate_condition(
    session: AsyncSession, condition: PatientCondition
) -> PatientCondition:
    """Soft delete: keep the row for audit, flip active=false."""
    condition.active = False
    await session.commit()
    await session.refresh(condition)
    return condition


async def resolve(patient_key: str) -> dict | None:
    """
    Look up a patient from the third party service that provides their info.
    Currently, the only service is pharmapi.
    """
    if not is_mock_pharmapi():
        # AMKA: exactly 11 digits. Anything else (e.g. 16-char European EKAA) routes to ekaa param.
        patient_key = patient_key.strip()
        get_patient = (
            pharmapi_get_patient(amka=patient_key)
            if patient_key.isdigit() and len(patient_key) == 11
            else pharmapi_get_patient(ekaa=patient_key)
        )
        patient, raw_intolerances = await asyncio.gather(
            get_patient,
            pharmapi_get_patient_intolerances(patient_key),
            return_exceptions=True,
        )
        if isinstance(patient, Exception):
            raise patient
        patient_dict = patient.model_dump()
        if isinstance(raw_intolerances, Exception):
            logger.warning("Failed to fetch intolerances for %s: %s", patient_key, raw_intolerances)
            patient_dict["intolerances"] = []
        else:
            patient_dict["intolerances"] = [
                {
                    "activeSubstance": item.get("activeSubstance"),
                    "intolerance": item.get("intolerance"),
                    "remarks": item.get("remarks"),
                }
                for item in raw_intolerances
            ]
        return patient_dict
    else:
        direct = PATIENT_PROFILES.get(patient_key)
        if direct:
            return direct
        for p in PATIENT_PROFILES.values():
            if p.get("amka") == patient_key:
                return p
        return None
