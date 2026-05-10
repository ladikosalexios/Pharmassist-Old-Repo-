"""Pharmacovigilance / adverse drug reaction reports (mock).

Severity: MILD | MODERATE | SEVERE.
Status:   PENDING_REVIEW | ESCALATED | EOF_REPORTED.
"""

MOCK_SIDE_EFFECTS: list = [
    {
        "id": "ADR-2026-0009",
        "patientId": "P001",
        "patientName": "Maria Stavrou",
        "patientPhone": "+30 694 312 3456",
        "rxId": "RX2024-005",
        "drugName": "Warfarin 5 mg",
        "severity": "SEVERE",
        "status": "ESCALATED",
        "reportedAt": "2026-04-29T16:42:00+00:00",
        "symptom": "Dark stools, dizziness on standing, gum bleeding after brushing teeth.",
        "onset": "8 hours after the second dose",
    },
    {
        "id": "ADR-2026-0008",
        "patientId": "P004",
        "patientName": "Eleni Papadopoulos",
        "patientPhone": "+30 697 555 0142",
        "rxId": "RX2024-002",
        "drugName": "Warfarin 7.5 mg",
        "severity": "MODERATE",
        "status": "PENDING_REVIEW",
        "reportedAt": "2026-04-28T11:05:00+00:00",
        "symptom": "Persistent nosebleeds and unusual bruising on forearms.",
        "onset": "Within 48 hours of dose increase",
    },
    {
        "id": "ADR-2026-0007",
        "patientId": "P010",
        "patientName": "Sarah Johnson",
        "patientPhone": "+30 698 011 2233",
        "rxId": "RX2024-001",
        "drugName": "Amoxicillin 500 mg",
        "severity": "MILD",
        "status": "PENDING_REVIEW",
        "reportedAt": "2026-04-26T08:20:00+00:00",
        "symptom": "Diffuse maculopapular rash on torso, no breathing difficulty.",
        "onset": "Day 3 of antibiotic course",
    },
    {
        "id": "ADR-2026-0006",
        "patientId": "P012",
        "patientName": "Dimitrios Konstantinou",
        "patientPhone": "+30 698 555 7012",
        "rxId": None,
        "drugName": "Atorvastatin 20 mg",
        "severity": "SEVERE",
        "status": "EOF_REPORTED",
        "reportedAt": "2026-04-22T19:14:00+00:00",
        "symptom": "Generalised muscle pain, dark urine, ALT 5x upper limit.",
        "onset": "Three weeks after starting therapy",
    },
    {
        "id": "ADR-2026-0005",
        "patientId": "P020",
        "patientName": "Anna Kostas",
        "patientPhone": "+30 697 999 0011",
        "rxId": None,
        "drugName": "Clopidogrel 75 mg",
        "severity": "MODERATE",
        "status": "ESCALATED",
        "reportedAt": "2026-04-15T12:00:00+00:00",
        "symptom": "Two episodes of melena, mild dyspnoea on exertion.",
        "onset": "Two weeks into therapy",
    },
    {
        "id": "ADR-2026-0004",
        "patientId": "P031",
        "patientName": "Nikos Vlachos",
        "patientPhone": "+30 698 222 0099",
        "rxId": None,
        "drugName": "Metformin 1000 mg",
        "severity": "MILD",
        "status": "EOF_REPORTED",
        "reportedAt": "2026-03-30T10:30:00+00:00",
        "symptom": "Mild gastrointestinal upset and metallic taste.",
        "onset": "First week of therapy",
    },
]


SEVERITY_RANK = {"MILD": 0, "MODERATE": 1, "SEVERE": 2}
STATUS_RANK = {"PENDING_REVIEW": 0, "ESCALATED": 1, "EOF_REPORTED": 2}


def stats() -> dict:
    s = {"total": len(MOCK_SIDE_EFFECTS), "pendingReview": 0, "severe": 0, "escalated": 0}
    for r in MOCK_SIDE_EFFECTS:
        if r["status"] == "PENDING_REVIEW":
            s["pendingReview"] += 1
        if r["severity"] == "SEVERE":
            s["severe"] += 1
        if r["status"] == "ESCALATED":
            s["escalated"] += 1
    return s


def next_status(current_status: str) -> str:
    if current_status == "PENDING_REVIEW":
        return "ESCALATED"
    if current_status == "ESCALATED":
        return "EOF_REPORTED"
    return current_status
