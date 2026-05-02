"""Prescriptions: full mock objects + the dashboard queue base list.

The full ``MOCK_PRESCRIPTIONS`` entries get mutated in place by the approve /
patch handlers (``rx["status"] = "COMPLETED"`` etc.), and the patients service
reads from this same dict — so as long as everyone imports from this module
they share the same Python object and the mutations are visible everywhere.
"""

from .safety_checks import MOCK_SAFETY_CHECKS


MOCK_PRESCRIPTIONS: dict = {
    "RX2024-005": {
        "rxId": "RX2024-005",
        "code": "RX2024-005",
        "dateIssued": "2026-04-28",
        "status": "PENDING",
        "spcVersion": "SPC v2024.3",
        "patient": {
            "id": "P001",
            "name": "Maria Stavrou",
            "age": 64,
            "dateOfBirth": "1962-03-15",
            "amka": "15031962456",
            "conditions": ["Type II Diabetes", "Hypertension", "Hyperlipidemia"],
            "allergies": "Penicillin (anaphylaxis), sulfa drugs",
        },
        "medication": {
            "drugName": "Warfarin",
            "atcCode": "B01AA03",
            "dose": "5 mg",
            "form": "Tablet",
            "route": "Oral",
            "frequency": "Once daily",
            "treatmentDuration": "90 days",
            "spcRecommendedDosage": (
                "Initial: 5–10 mg daily for 1–2 days, then adjusted based on INR. "
                "Maintenance: 2–10 mg daily. Target INR 2.0–3.0 for most indications."
            ),
        },
        "prescriber": {
            "name": "Dr. Michael Chen",
            "licenceId": "MD-48291",
            "specialty": "Cardiology",
            "contact": "+30 210 123 4567",
            "email": "m.chen@hospital.gr",
        },
        "spcQuickReference": {
            "contraindications": [
                "Active bleeding or bleeding diathesis",
                "Recent or planned surgery (CNS, eye, traumatic)",
                "Severe hepatic impairment",
                "Pregnancy (except for mechanical heart valves)",
            ],
            "majorInteractions": [
                {"drug": "Aspirin", "effect": "High risk of bleeding when combined with anticoagulants."},
                {"drug": "NSAIDs", "effect": "Increased bleeding risk; avoid concurrent use."},
                {"drug": "Amiodarone", "effect": "Potentiates warfarin effect; reduce warfarin dose by 30–50%."},
            ],
        },
        "safetyChecks": MOCK_SAFETY_CHECKS["RX2024-005"],
    },
    "RX2024-001": {
        "rxId": "RX2024-001",
        "code": "RX2024-001",
        "dateIssued": "2026-03-11",
        "status": "PENDING",
        "spcVersion": "SPC v2024.3",
        "patient": {
            "id": "P010",
            "name": "Sarah Johnson",
            "age": 32,
            "dateOfBirth": "1993-07-22",
            "amka": "22071993789",
            "conditions": ["Bacterial sinusitis"],
            "allergies": "None known",
        },
        "medication": {
            "drugName": "Amoxicillin",
            "atcCode": "J01CA04",
            "dose": "500 mg",
            "form": "Capsule",
            "route": "Oral",
            "frequency": "Three times daily",
            "treatmentDuration": "7 days",
            "spcRecommendedDosage": "Adults: 250–500 mg every 8 hours, depending on severity.",
        },
        "prescriber": {
            "name": "Dr. Michael Chen",
            "licenceId": "MD-48291",
            "specialty": "General Practice",
            "contact": "+30 210 123 4567",
            "email": "m.chen@hospital.gr",
        },
        "spcQuickReference": {
            "contraindications": [
                "Hypersensitivity to penicillins or any beta-lactam antibiotic",
                "History of severe immediate hypersensitivity reaction",
            ],
            "majorInteractions": [
                {"drug": "Methotrexate", "effect": "Reduced excretion; increased toxicity risk."},
                {"drug": "Allopurinol",  "effect": "Increased risk of skin rash."},
            ],
        },
        "safetyChecks": MOCK_SAFETY_CHECKS["RX2024-001"],
    },
}


# Static queue rows that may not have full prescription details. The actual
# status comes from MOCK_PRESCRIPTIONS when the rxId is also seeded there.
MOCK_QUEUE_BASE: list = [
    {"rxId": "RX2024-001", "patientName": "Sarah Johnson",  "medication": "Amoxicillin", "physician": "Dr. Michael Chen",  "date": "2026-03-11", "status": "PENDING"},
    {"rxId": "RX2024-002", "patientName": "James Martinez", "medication": "Warfarin",    "physician": "Dr. Emily Roberts", "date": "2026-03-11", "status": "FLAGGED"},
    {"rxId": "RX2024-003", "patientName": "Maria Garcia",   "medication": "Lisinopril",  "physician": "Dr. David Lee",     "date": "2026-03-11", "status": "PENDING"},
    {"rxId": "RX2024-005", "patientName": "Maria Stavrou",  "medication": "Warfarin",    "physician": "Dr. Michael Chen",  "date": "2026-04-28", "status": "PENDING"},
]
