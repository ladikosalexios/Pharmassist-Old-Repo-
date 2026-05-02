"""Automated safety checks per prescription (mock).

Status values: ok | review | block.
"""


MOCK_SAFETY_CHECKS: dict = {
    "RX2024-005": [
        {
            "id": "duplicate-therapy",
            "name": "Duplicate Therapy Check",
            "status": "ok",
            "message": "No duplicate therapy detected.",
            "details": "Patient is not currently on any other anticoagulant. Reviewed active prescriptions in the last 90 days.",
            "recommendedAction": None,
        },
        {
            "id": "interactions",
            "name": "Drug-Drug Interactions",
            "status": "review",
            "message": "Patient is on Aspirin 100 mg — review bleeding risk.",
            "details": (
                "Concurrent Warfarin + Aspirin significantly increases bleeding risk "
                "(major GI and intracranial bleeding rates roughly 2–3× background). "
                "Combination is acceptable when indicated (e.g. mechanical valve, recent ACS) "
                "but requires close INR monitoring and a documented clinical justification."
            ),
            "recommendedAction": (
                "Confirm clinical indication with the prescriber. If continued, schedule INR "
                "every 3–5 days for the first 2 weeks and counsel patient on bleeding signs."
            ),
        },
        {
            "id": "contraindications",
            "name": "Contraindications",
            "status": "ok",
            "message": "No contraindications identified.",
            "details": "Patient has no active bleeding, no recent surgery, no severe hepatic impairment, and is not pregnant.",
            "recommendedAction": None,
        },
        {
            "id": "dose-validation",
            "name": "Dose Validation",
            "status": "ok",
            "message": "Dose within SPC recommended range.",
            "details": "5 mg once daily falls within the SPC maintenance range of 2–10 mg daily.",
            "recommendedAction": None,
        },
        {
            "id": "spc-alignment",
            "name": "SPC Alignment",
            "status": "review",
            "message": "Confirm INR monitoring schedule is in place.",
            "details": (
                "SPC v2024.3 mandates INR monitoring at initiation, every 3–5 days during "
                "induction, and at least every 4 weeks during maintenance. No INR appointments "
                "are recorded for this patient in the last 30 days."
            ),
            "recommendedAction": "Book the next INR test before dispensing and add a recurring monthly INR reminder.",
        },
    ],
    "RX2024-001": [
        {
            "id": "duplicate-therapy",
            "name": "Duplicate Therapy Check",
            "status": "ok",
            "message": "No duplicate therapy detected.",
            "details": "No other beta-lactam antibiotic active in the patient's record.",
            "recommendedAction": None,
        },
        {
            "id": "interactions",
            "name": "Drug-Drug Interactions",
            "status": "ok",
            "message": "No major interactions detected.",
            "details": "No methotrexate, allopurinol, or other significant interactions on file.",
            "recommendedAction": None,
        },
        {
            "id": "contraindications",
            "name": "Contraindications",
            "status": "ok",
            "message": "No contraindications identified.",
            "details": "Patient has no documented penicillin or beta-lactam hypersensitivity.",
            "recommendedAction": None,
        },
        {
            "id": "dose-validation",
            "name": "Dose Validation",
            "status": "ok",
            "message": "Dose within SPC recommended range.",
            "details": "500 mg every 8 hours is within the adult SPC range (250–500 mg q8h).",
            "recommendedAction": None,
        },
        {
            "id": "spc-alignment",
            "name": "SPC Alignment",
            "status": "ok",
            "message": "Aligned with current SPC.",
            "details": "Indication, dose, route, and duration match SPC v2024.3.",
            "recommendedAction": None,
        },
    ],
}
