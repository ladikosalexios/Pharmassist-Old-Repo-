"""Prescriptions: full mock objects + the dashboard queue base list.

The full ``MOCK_PRESCRIPTIONS`` entries get mutated in place by the approve /
patch handlers (``rx["status"] = "COMPLETED"`` etc.), and the patients service
reads from this same dict — so as long as everyone imports from this module
they share the same Python object and the mutations are visible everywhere.

``MOCK_QUEUE_BASE`` is derived from ``MOCK_PRESCRIPTIONS`` so the queue can never
drift from the detail records. Adding a prescription is a one-place change.
"""

from ..constants import PrescriptionStatus
from .safety_checks import MOCK_SAFETY_CHECKS

MOCK_PRESCRIPTIONS: dict = {
    "RX2024-005": {
        "rxId": "RX2024-005",
        "code": "RX2024-005",
        "dateIssued": "2026-04-28",
        "status": PrescriptionStatus.PENDING,
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
            "nhrn": "5201234500017",
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
                {
                    "drug": "Aspirin",
                    "effect": "High risk of bleeding when combined with anticoagulants.",
                },
                {"drug": "NSAIDs", "effect": "Increased bleeding risk; avoid concurrent use."},
                {
                    "drug": "Amiodarone",
                    "effect": "Potentiates warfarin effect; reduce warfarin dose by 30–50%.",
                },
            ],
        },
        "safetyChecks": MOCK_SAFETY_CHECKS["RX2024-005"],
    },
    "RX2024-001": {
        "rxId": "RX2024-001",
        "code": "RX2024-001",
        "dateIssued": "2026-03-11",
        "status": PrescriptionStatus.PENDING,
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
            "nhrn": "5201234500024",
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
                {"drug": "Allopurinol", "effect": "Increased risk of skin rash."},
            ],
        },
        "safetyChecks": MOCK_SAFETY_CHECKS["RX2024-001"],
    },
    "RX2024-002": {
        "rxId": "RX2024-002",
        "code": "RX2024-002",
        "dateIssued": "2026-04-12",
        "status": PrescriptionStatus.FLAGGED,
        "spcVersion": "SPC v2024.3",
        "patient": {
            "id": "P024",
            "name": "James Martinez",
            "age": 71,
            "dateOfBirth": "1954-09-03",
            "amka": "03091954221",
            "conditions": ["Atrial fibrillation", "Hypertension"],
            "allergies": "None known",
        },
        "medication": {
            "drugName": "Warfarin",
            "atcCode": "B01AA03",
            "nhrn": "5201234500017",
            "dose": "7.5 mg",
            "form": "Tablet",
            "route": "Oral",
            "frequency": "Once daily",
            "treatmentDuration": "Long-term",
            "spcRecommendedDosage": (
                "Maintenance: 2–10 mg daily, adjusted to target INR 2.0–3.0 for AF."
            ),
        },
        "prescriber": {
            "name": "Dr. Emily Roberts",
            "licenceId": "MD-50114",
            "specialty": "Cardiology",
            "contact": "+30 210 555 0103",
            "email": "e.roberts@hospital.gr",
        },
        "spcQuickReference": {
            "contraindications": [
                "Active bleeding",
                "Recent or planned surgery",
                "Severe hepatic impairment",
            ],
            "majorInteractions": [
                {"drug": "Aspirin", "effect": "Bleeding risk."},
                {
                    "drug": "Acenocoumarol",
                    "effect": "Both are vitamin-K antagonists — duplicate anticoagulation.",
                },
            ],
        },
        "safetyChecks": MOCK_SAFETY_CHECKS["RX2024-002"],
    },
    "RX2024-003": {
        "rxId": "RX2024-003",
        "code": "RX2024-003",
        "dateIssued": "2026-03-22",
        "status": PrescriptionStatus.PENDING,
        "spcVersion": "SPC v2024.3",
        "patient": {
            "id": "P033",
            "name": "Maria Garcia",
            "age": 58,
            "dateOfBirth": "1968-01-19",
            "amka": "19011968147",
            "conditions": ["Hypertension"],
            "allergies": "None known",
        },
        "medication": {
            "drugName": "Lisinopril",
            "atcCode": "C09AA03",
            "nhrn": "5201234500031",
            "dose": "10 mg",
            "form": "Tablet",
            "route": "Oral",
            "frequency": "Once daily",
            "treatmentDuration": "Long-term",
            "spcRecommendedDosage": "Initial 10 mg once daily; titrate up to 20–40 mg as tolerated.",
        },
        "prescriber": {
            "name": "Dr. David Lee",
            "licenceId": "MD-49872",
            "specialty": "General Practice",
            "contact": "+30 210 555 0181",
            "email": "d.lee@clinic.gr",
        },
        "spcQuickReference": {
            "contraindications": [
                "History of angioedema with ACEi",
                "Bilateral renal artery stenosis",
                "Pregnancy",
            ],
            "majorInteractions": [
                {"drug": "Potassium-sparing diuretics", "effect": "Hyperkalaemia risk."},
                {"drug": "NSAIDs", "effect": "Reduced antihypertensive effect; renal injury risk."},
            ],
        },
        "safetyChecks": MOCK_SAFETY_CHECKS["RX2024-003"],
    },
    "RX2024-006": {
        "rxId": "RX2024-006",
        "code": "RX2024-006",
        "dateIssued": "2026-05-02",
        "status": PrescriptionStatus.PENDING,
        "spcVersion": "SPC v2024.3",
        "patient": {
            "id": "P040",
            "name": "Nikos Papadopoulos",
            "age": 78,
            "dateOfBirth": "1947-11-08",
            "amka": "08111947033",
            "conditions": ["Type II Diabetes", "G6PD deficiency (moderate)"],
            "allergies": "None known",
        },
        "medication": {
            "drugName": "Metformin",
            "atcCode": "A10BA02",
            "nhrn": "5201234500048",
            "dose": "850 mg",
            "form": "Tablet",
            "route": "Oral",
            "frequency": "Twice daily",
            "treatmentDuration": "Long-term",
            "spcRecommendedDosage": "500–850 mg twice or three times daily; max 2,550 mg/day.",
        },
        "prescriber": {
            "name": "Dr. Anna Kostas",
            "licenceId": "MD-50220",
            "specialty": "Endocrinology",
            "contact": "+30 210 555 0212",
            "email": "a.kostas@clinic.gr",
        },
        "spcQuickReference": {
            "contraindications": [
                "eGFR < 30 mL/min/1.73m²",
                "Acute metabolic acidosis",
                "Severe hepatic impairment",
            ],
            "majorInteractions": [
                {
                    "drug": "Iodinated contrast",
                    "effect": "Risk of acute renal failure — pause metformin.",
                },
                {
                    "drug": "Loop diuretics",
                    "effect": "Reduced renal function may unmask metformin contraindication.",
                },
            ],
        },
        "safetyChecks": MOCK_SAFETY_CHECKS["RX2024-006"],
    },
    "RX2024-007": {
        "rxId": "RX2024-007",
        "code": "RX2024-007",
        "dateIssued": "2026-04-19",
        "status": PrescriptionStatus.COMPLETED,
        "completedAt": "2026-04-19T11:42:00+00:00",
        "spcVersion": "SPC v2024.3",
        "patient": {
            "id": "P051",
            "name": "Eleni Demetriou",
            "age": 45,
            "dateOfBirth": "1980-06-26",
            "amka": "26061980554",
            "conditions": ["Hyperlipidemia"],
            "allergies": "None known",
        },
        "medication": {
            "drugName": "Atorvastatin",
            "atcCode": "C10AA05",
            "nhrn": "5201234500055",
            "dose": "40 mg",
            "form": "Tablet",
            "route": "Oral",
            "frequency": "Once daily",
            "treatmentDuration": "Long-term",
            "spcRecommendedDosage": "10–80 mg once daily, titrated to LDL target.",
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
                "Active liver disease",
                "Pregnancy / breastfeeding",
            ],
            "majorInteractions": [
                {
                    "drug": "Clarithromycin",
                    "effect": "Increased atorvastatin exposure — myopathy risk.",
                },
                {"drug": "Cyclosporine", "effect": "Significantly increased atorvastatin levels."},
            ],
        },
        "safetyChecks": MOCK_SAFETY_CHECKS["RX2024-007"],
    },
    "RX2024-008": {
        "rxId": "RX2024-008",
        "code": "RX2024-008",
        "dateIssued": "2026-05-03",
        "status": PrescriptionStatus.PENDING,
        "spcVersion": "SPC v2024.3",
        "patient": {
            "id": "P062",
            "name": "Andreas Vasilakis",
            "age": 29,
            "dateOfBirth": "1996-08-14",
            "amka": "14081996228",
            "conditions": ["Recent ACS (3 months ago)", "Reflux"],
            "allergies": "None known",
        },
        "medication": {
            "drugName": "Clopidogrel",
            "atcCode": "B01AC04",
            "nhrn": "5201234500062",
            "dose": "75 mg",
            "form": "Tablet",
            "route": "Oral",
            "frequency": "Once daily",
            "treatmentDuration": "12 months",
            "spcRecommendedDosage": "75 mg once daily as maintenance.",
        },
        "prescriber": {
            "name": "Dr. Emily Roberts",
            "licenceId": "MD-50114",
            "specialty": "Cardiology",
            "contact": "+30 210 555 0103",
            "email": "e.roberts@hospital.gr",
        },
        "spcQuickReference": {
            "contraindications": [
                "Active pathological bleeding",
                "Severe hepatic impairment",
            ],
            "majorInteractions": [
                {"drug": "Omeprazole", "effect": "Reduces clopidogrel activation via CYP2C19."},
                {"drug": "Aspirin", "effect": "Additive bleeding risk; DAPT only when indicated."},
            ],
        },
        "safetyChecks": MOCK_SAFETY_CHECKS["RX2024-008"],
    },
    "RX2024-009": {
        "rxId": "RX2024-009",
        "code": "RX2024-009",
        "dateIssued": "2026-05-05",
        "status": PrescriptionStatus.PENDING,
        "spcVersion": "SPC v2024.3",
        "patient": {
            "id": "P078",
            "name": "Sofia Ioannidou",
            "age": 8,
            "dateOfBirth": "2017-09-04",
            "amka": "04092017819",
            "conditions": ["Acute otitis media"],
            "allergies": "None known",
        },
        "medication": {
            "drugName": "Amoxicillin",
            "atcCode": "J01CA04",
            "dose": "250 mg / 5 mL suspension",
            "form": "Oral suspension",
            "route": "Oral",
            "frequency": "Three times daily",
            "treatmentDuration": "10 days",
            "spcRecommendedDosage": "Paediatric: 25–50 mg/kg/day in three divided doses.",
        },
        "prescriber": {
            "name": "Dr. Kostas Manolas",
            "licenceId": "MD-50345",
            "specialty": "Paediatrics",
            "contact": "+30 210 555 0299",
            "email": "k.manolas@paediatrics.gr",
        },
        "spcQuickReference": {
            "contraindications": [
                "Hypersensitivity to penicillins or beta-lactams",
            ],
            "majorInteractions": [
                {
                    "drug": "Methotrexate",
                    "effect": "Reduced excretion — relevant in oncology paeds only.",
                },
            ],
        },
        "safetyChecks": MOCK_SAFETY_CHECKS["RX2024-009"],
    },
    # Engine-test prescriptions: not in MOCK_SAFETY_CHECKS, so they are evaluated
    # by the safety engine. Each is paired with a seeded PatientCondition that
    # triggers a condition-based rule.
    "RX-ENGINE-001": {
        "rxId": "RX-ENGINE-001",
        "code": "RX-ENGINE-001",
        "dateIssued": "2026-05-14",
        "status": PrescriptionStatus.PENDING,
        "spcVersion": "SPC v2024.3",
        "patient": {
            "id": "P010",
            "name": "Sarah Johnson",
            "age": 32,
            "dateOfBirth": "1993-07-22",
            "amka": "22071993789",
            "conditions": ["Pregnancy (18 weeks)", "Hypertension"],
            "allergies": "None known",
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
                "Maintenance: 2–10 mg daily."
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
                "Pregnancy (except for mechanical heart valves)",
                "Active bleeding or bleeding diathesis",
                "Severe hepatic impairment",
            ],
            "majorInteractions": [
                {"drug": "Aspirin", "effect": "High risk of bleeding when combined."},
                {"drug": "Amiodarone", "effect": "Potentiates warfarin — reduce dose 30–50%."},
            ],
        },
    },
    "RX-ENGINE-002": {
        "rxId": "RX-ENGINE-002",
        "code": "RX-ENGINE-002",
        "dateIssued": "2026-05-14",
        "status": PrescriptionStatus.PENDING,
        "spcVersion": "SPC v2024.3",
        "patient": {
            "id": "P040",
            "name": "Nikos Papadopoulos",
            "age": 78,
            "dateOfBirth": "1947-11-08",
            "amka": "08111947033",
            "conditions": ["Type II Diabetes", "G6PD deficiency (moderate)"],
            "allergies": "None known",
        },
        "medication": {
            "drugName": "Aspirin",
            "atcCode": "B01AC06",
            "dose": "100 mg",
            "form": "Tablet",
            "route": "Oral",
            "frequency": "Once daily",
            "treatmentDuration": "Long-term",
            "spcRecommendedDosage": "75–100 mg once daily for antiplatelet prophylaxis.",
        },
        "prescriber": {
            "name": "Dr. Anna Kostas",
            "licenceId": "MD-50220",
            "specialty": "Endocrinology",
            "contact": "+30 210 555 0212",
            "email": "a.kostas@clinic.gr",
        },
        "spcQuickReference": {
            "contraindications": [
                "Active peptic ulcer",
                "Bleeding disorders",
            ],
            "majorInteractions": [
                {"drug": "Warfarin", "effect": "Increased bleeding risk."},
                {"drug": "Clopidogrel", "effect": "DAPT — confirm indication."},
            ],
        },
    },
    "RX-ENGINE-003": {
        "rxId": "RX-ENGINE-003",
        "code": "RX-ENGINE-003",
        "dateIssued": "2026-05-14",
        "status": PrescriptionStatus.PENDING,
        "spcVersion": "SPC v2024.3",
        "patient": {
            "id": "P020",
            "name": "Anna Kostas",
            "age": 77,
            "dateOfBirth": "1948-10-12",
            "amka": "12101948112",
            "conditions": ["Hypertension", "Type II Diabetes", "Chronic Kidney Disease (stage 3b)"],
            "allergies": "None known",
        },
        "medication": {
            "drugName": "Metformin",
            "atcCode": "A10BA02",
            "dose": "500 mg",
            "form": "Tablet",
            "route": "Oral",
            "frequency": "Twice daily",
            "treatmentDuration": "Long-term",
            "spcRecommendedDosage": "500–850 mg twice or three times daily; max 2,550 mg/day.",
        },
        "prescriber": {
            "name": "Dr. Elena Stavros",
            "licenceId": "MD-50418",
            "specialty": "Endocrinology",
            "contact": "+30 210 555 0418",
            "email": "e.stavros@clinic.gr",
        },
        "spcQuickReference": {
            "contraindications": [
                "eGFR < 30 mL/min/1.73m²",
                "Acute metabolic acidosis",
                "Severe hepatic impairment",
            ],
            "majorInteractions": [
                {
                    "drug": "Iodinated contrast",
                    "effect": "Risk of acute renal failure — pause metformin.",
                },
            ],
        },
    },
    # ── Historical prescriptions designed to trigger interaction alerts ─────
    # Referenced from PATIENT_RX_HISTORY_BASE (see app/services/patients.py).
    # Each `medication.atcCode` here pairs with a seeded safety_rule so that
    # evaluate_safety produces visible output on /alerts/active in mock mode.
    # Patient-condition rules (PREGNANCY/G6PD/RENAL_SEVERE) fire via DB rows
    # seeded by scripts/seed.py — re-run that script to exercise them.
    "RX-HIST-001": {
        "rxId": "RX-HIST-001",
        "code": "RX-HIST-001",
        "dateIssued": "2025-12-04",
        "status": PrescriptionStatus.COMPLETED,
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
            # B01AC06 + Maria's pending Warfarin (B01AA03) → WARFARIN_ASPIRIN_BLEED
            "drugName": "Aspirin",
            "atcCode": "B01AC06",
            "dose": "100 mg",
            "form": "Tablet",
            "route": "Oral",
            "frequency": "Once daily",
            "treatmentDuration": "Long-term",
            "spcRecommendedDosage": "75–100 mg once daily for antiplatelet prophylaxis.",
        },
        "prescriber": {
            "name": "Dr. Michael Chen",
            "licenceId": "MD-48291",
            "specialty": "Cardiology",
            "contact": "+30 210 123 4567",
            "email": "m.chen@hospital.gr",
        },
        "spcQuickReference": {"contraindications": [], "majorInteractions": []},
    },
    "RX-HIST-002": {
        "rxId": "RX-HIST-002",
        "code": "RX-HIST-002",
        "dateIssued": "2025-10-21",
        "status": PrescriptionStatus.COMPLETED,
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
            # C01BD01 + Maria's pending Warfarin → WARFARIN_AMIODARONE_INTERACTION (SEVERE)
            "drugName": "Amiodarone",
            "atcCode": "C01BD01",
            "dose": "200 mg",
            "form": "Tablet",
            "route": "Oral",
            "frequency": "Once daily",
            "treatmentDuration": "Long-term",
            "spcRecommendedDosage": "Loading 600–1200 mg/day, maintenance 200–400 mg/day.",
        },
        "prescriber": {
            "name": "Dr. Michael Chen",
            "licenceId": "MD-48291",
            "specialty": "Cardiology",
            "contact": "+30 210 123 4567",
            "email": "m.chen@hospital.gr",
        },
        "spcQuickReference": {"contraindications": [], "majorInteractions": []},
    },
    "RX-HIST-003": {
        "rxId": "RX-HIST-003",
        "code": "RX-HIST-003",
        "dateIssued": "2026-02-18",
        "status": PrescriptionStatus.COMPLETED,
        "spcVersion": "SPC v2024.3",
        "patient": {
            "id": "P010",
            "name": "Sarah Johnson",
            "age": 32,
            "dateOfBirth": "1993-07-22",
            "amka": "22071993789",
            "conditions": ["Pregnancy (18 weeks)", "Hypertension"],
            "allergies": "None known",
        },
        "medication": {
            # B01AC06 + Sarah's pending Warfarin (RX-ENGINE-001) → WARFARIN_ASPIRIN_BLEED
            "drugName": "Aspirin",
            "atcCode": "B01AC06",
            "dose": "75 mg",
            "form": "Tablet",
            "route": "Oral",
            "frequency": "Once daily",
            "treatmentDuration": "Long-term",
            "spcRecommendedDosage": "75–100 mg once daily for antiplatelet prophylaxis.",
        },
        "prescriber": {
            "name": "Dr. Michael Chen",
            "licenceId": "MD-48291",
            "specialty": "Cardiology",
            "contact": "+30 210 123 4567",
            "email": "m.chen@hospital.gr",
        },
        "spcQuickReference": {"contraindications": [], "majorInteractions": []},
    },
    "RX-HIST-004": {
        "rxId": "RX-HIST-004",
        "code": "RX-HIST-004",
        "dateIssued": "2025-08-09",
        "status": PrescriptionStatus.COMPLETED,
        "spcVersion": "SPC v2024.3",
        "patient": {
            "id": "P040",
            "name": "Nikos Papadopoulos",
            "age": 78,
            "dateOfBirth": "1947-11-08",
            "amka": "08111947033",
            "conditions": ["Type II Diabetes", "G6PD deficiency (moderate)"],
            "allergies": "None known",
        },
        "medication": {
            # B01AC04 + Nikos's pending Aspirin (RX-ENGINE-002, B01AC06)
            # → CLOPIDOGREL_ASPIRIN_DUPLICATE
            "drugName": "Clopidogrel",
            "atcCode": "B01AC04",
            "dose": "75 mg",
            "form": "Tablet",
            "route": "Oral",
            "frequency": "Once daily",
            "treatmentDuration": "Long-term",
            "spcRecommendedDosage": "75 mg once daily after ACS or stenting.",
        },
        "prescriber": {
            "name": "Dr. Anna Kostas",
            "licenceId": "MD-50220",
            "specialty": "Endocrinology",
            "contact": "+30 210 555 0212",
            "email": "a.kostas@clinic.gr",
        },
        "spcQuickReference": {"contraindications": [], "majorInteractions": []},
    },
}


# Derived from MOCK_PRESCRIPTIONS so the dashboard queue cannot drift from the
# detail records. Keep in sync by adding new entries above only.
MOCK_QUEUE_BASE: list = [
    {
        "rxId": rx["rxId"],
        "patientName": rx["patient"]["name"],
        "medication": rx["medication"]["drugName"],
        "physician": rx["prescriber"]["name"],
        "date": rx["dateIssued"],
        "status": rx["status"],
    }
    for rx in MOCK_PRESCRIPTIONS.values()
]
