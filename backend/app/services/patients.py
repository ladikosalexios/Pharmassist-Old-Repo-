"""Patient profiles + per-patient prescription / ADR history.

Reads live status from the prescriptions service for any rxId that has a full
record there, so flag/approve actions on the verification page show up
immediately in a patient's history.
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.patient_condition import PatientCondition
from app.services.pharmapi import pharmapi_get_patient
from app.utils.environment import is_mock_pharmapi

from .prescriptions import MOCK_PRESCRIPTIONS
from .side_effects import MOCK_SIDE_EFFECTS

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
            "status": "PENDING",
        },
        {
            "rxId": "RX2023-118",
            "date": "2025-11-12",
            "drugName": "Atorvastatin 20 mg",
            "prescriberName": "Dr. Michael Chen",
            "status": "COMPLETED",
        },
        {
            "rxId": "RX2023-077",
            "date": "2025-09-03",
            "drugName": "Metformin 1000 mg",
            "prescriberName": "Dr. Maria Lampraki",
            "status": "COMPLETED",
        },
        {
            "rxId": "RX2023-022",
            "date": "2025-04-19",
            "drugName": "Ramipril 5 mg",
            "prescriberName": "Dr. Maria Lampraki",
            "status": "COMPLETED",
        },
    ],
    "P004": [
        {
            "rxId": "RX2024-002",
            "date": "2026-03-11",
            "drugName": "Warfarin 7.5 mg",
            "prescriberName": "Dr. Emily Roberts",
            "status": "FLAGGED",
        },
        {
            "rxId": "RX2023-054",
            "date": "2025-08-20",
            "drugName": "Bisoprolol 5 mg",
            "prescriberName": "Dr. Emily Roberts",
            "status": "COMPLETED",
        },
    ],
    "P010": [
        {
            "rxId": "RX2024-001",
            "date": "2026-03-11",
            "drugName": "Amoxicillin 500 mg",
            "prescriberName": "Dr. Michael Chen",
            "status": "PENDING",
        },
    ],
    "P012": [
        {
            "rxId": "RX2023-091",
            "date": "2025-12-08",
            "drugName": "Atorvastatin 20 mg",
            "prescriberName": "Dr. David Lee",
            "status": "COMPLETED",
        },
        {
            "rxId": "RX2023-044",
            "date": "2025-06-14",
            "drugName": "Aspirin 100 mg",
            "prescriberName": "Dr. David Lee",
            "status": "COMPLETED",
        },
    ],
    "P020": [
        {
            "rxId": "RX2023-066",
            "date": "2025-09-30",
            "drugName": "Clopidogrel 75 mg",
            "prescriberName": "Dr. Sophia Roussou",
            "status": "COMPLETED",
        },
    ],
    "P031": [
        {
            "rxId": "RX2023-032",
            "date": "2025-05-18",
            "drugName": "Metformin 1000 mg",
            "prescriberName": "Dr. Niko Pateli",
            "status": "COMPLETED",
        },
    ],
}


def rx_history(patient_id: str) -> list:
    rows = list(PATIENT_RX_HISTORY_BASE.get(patient_id, []))
    for row in rows:
        live = MOCK_PRESCRIPTIONS.get(row["rxId"])
        if live and live.get("status"):
            row["status"] = live["status"]
    rows.sort(key=lambda r: r["date"], reverse=True)
    return rows


def adr_history(patient_id: str) -> list:
    rows = [r for r in MOCK_SIDE_EFFECTS if r["patientId"] == patient_id]
    rows.sort(key=lambda r: r["reportedAt"], reverse=True)
    return rows


async def conditions(session: AsyncSession, patient_id: str) -> list:
    return (
        await session.scalars(select(PatientCondition).where(PatientCondition.amka == patient_id))
    ).all()


async def resolve(patient_key: str) -> dict | None:
    """
    Look up a patient from the third party service that provides their info.
    Currently, the only service is pharmapi.
    """
    if not is_mock_pharmapi():
        return await pharmapi_get_patient(patient_key)
    else:
        direct = PATIENT_PROFILES.get(patient_key)
        if direct:
            return direct
        for p in PATIENT_PROFILES.values():
            if p.get("amka") == patient_key:
                return p
        return None
