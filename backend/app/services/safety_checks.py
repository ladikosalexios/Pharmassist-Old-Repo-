"""Automated safety checks per prescription (mock).

Status values: ok | review | block.
"""

MOCK_SAFETY_CHECKS: dict = {
    "RX2024-005": [
        {
            "id": "duplicate-therapy",
            "checkType": "duplicate_therapy",
            "name": "Duplicate Therapy Check",
            "status": "ok",
            "message": "No duplicate therapy detected.",
            "details": "Patient is not currently on any other anticoagulant. Reviewed active prescriptions in the last 90 days.",
            "recommendedAction": None,
        },
        {
            "id": "interactions-amiodarone",
            "checkType": "interactions",
            "name": "Drug-Drug Interactions",
            "status": "block",
            "message": "Active Amiodarone — over-anticoagulation risk. Do not dispense without prescriber confirmation.",
            "details": (
                "Amiodarone is a potent CYP2C9 inhibitor; co-administered with Warfarin it "
                "markedly raises INR and bleeding risk. Active Amiodarone 200 mg on file "
                "(filled 2025-10-21). Dispensing the current Warfarin dose unchanged risks "
                "serious over-anticoagulation."
            ),
            "recommendedAction": (
                "Hold and contact the prescriber. Warfarin dose typically needs a 30–50% "
                "reduction with weekly INR monitoring until stable."
            ),
        },
        {
            "id": "interactions",
            "checkType": "interactions",
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
            "checkType": "contraindications",
            "name": "Contraindications",
            "status": "ok",
            "message": "No contraindications identified.",
            "details": "Patient has no active bleeding, no recent surgery, no severe hepatic impairment, and is not pregnant.",
            "recommendedAction": None,
        },
        {
            "id": "dose-validation",
            "checkType": "dose_validation",
            "name": "Dose Validation",
            "status": "ok",
            "message": "Dose within SPC recommended range.",
            "details": "5 mg once daily falls within the SPC maintenance range of 2–10 mg daily.",
            "recommendedAction": None,
        },
        {
            "id": "spc-alignment",
            "checkType": "spc_alignment",
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
            "checkType": "duplicate_therapy",
            "name": "Duplicate Therapy Check",
            "status": "ok",
            "message": "No duplicate therapy detected.",
            "details": "No other beta-lactam antibiotic active in the patient's record.",
            "recommendedAction": None,
        },
        {
            "id": "interactions",
            "checkType": "interactions",
            "name": "Drug-Drug Interactions",
            "status": "ok",
            "message": "No major interactions detected.",
            "details": "No methotrexate, allopurinol, or other significant interactions on file.",
            "recommendedAction": None,
        },
        {
            "id": "contraindications",
            "checkType": "contraindications",
            "name": "Contraindications",
            "status": "ok",
            "message": "No contraindications identified.",
            "details": "Patient has no documented penicillin or beta-lactam hypersensitivity.",
            "recommendedAction": None,
        },
        {
            "id": "dose-validation",
            "checkType": "dose_validation",
            "name": "Dose Validation",
            "status": "ok",
            "message": "Dose within SPC recommended range.",
            "details": "500 mg every 8 hours is within the adult SPC range (250–500 mg q8h).",
            "recommendedAction": None,
        },
        {
            "id": "spc-alignment",
            "checkType": "spc_alignment",
            "name": "SPC Alignment",
            "status": "ok",
            "message": "Aligned with current SPC.",
            "details": "Indication, dose, route, and duration match SPC v2024.3.",
            "recommendedAction": None,
        },
    ],
    "RX2024-002": [
        {
            "id": "duplicate-therapy",
            "checkType": "duplicate_therapy",
            "name": "Duplicate Therapy Check",
            "status": "review",
            "message": "Patient has an active prescription for Acenocoumarol — overlapping anticoagulants.",
            "details": "Active Acenocoumarol 4 mg once daily on file (filled 2026-04-02). Stacking warfarin on top creates a clear over-anticoagulation risk.",
            "recommendedAction": "Confirm whether the prescriber intended a switch — if so, document a stop date for Acenocoumarol before dispensing.",
        },
        {
            "id": "interactions",
            "checkType": "interactions",
            "name": "Drug-Drug Interactions",
            "status": "ok",
            "message": "No additional major interactions detected.",
            "details": "No NSAIDs, no aspirin, no amiodarone on the patient record.",
            "recommendedAction": None,
        },
        {
            "id": "contraindications",
            "checkType": "contraindications",
            "name": "Contraindications",
            "status": "ok",
            "message": "No contraindications identified.",
            "details": "No active bleeding, no recent surgery on file.",
            "recommendedAction": None,
        },
        {
            "id": "dose-validation",
            "checkType": "dose_validation",
            "name": "Dose Validation",
            "status": "ok",
            "message": "Dose within SPC recommended range.",
            "details": "7.5 mg once daily is within the SPC maintenance range (2–10 mg).",
            "recommendedAction": None,
        },
    ],
    "RX2024-003": [
        {
            "id": "duplicate-therapy",
            "checkType": "duplicate_therapy",
            "name": "Duplicate Therapy Check",
            "status": "ok",
            "message": "No duplicate ACE inhibitor on file.",
            "details": "No other ACEi or ARB active in the patient's record.",
            "recommendedAction": None,
        },
        {
            "id": "interactions",
            "checkType": "interactions",
            "name": "Drug-Drug Interactions",
            "status": "ok",
            "message": "No major interactions detected.",
            "details": "No potassium-sparing diuretics or NSAIDs on file.",
            "recommendedAction": None,
        },
        {
            "id": "contraindications",
            "checkType": "contraindications",
            "name": "Contraindications",
            "status": "ok",
            "message": "No contraindications identified.",
            "details": "No history of angioedema, bilateral renal artery stenosis, or pregnancy.",
            "recommendedAction": None,
        },
        {
            "id": "dose-validation",
            "checkType": "dose_validation",
            "name": "Dose Validation",
            "status": "ok",
            "message": "Dose within SPC recommended range.",
            "details": "10 mg once daily is the standard maintenance dose for hypertension.",
            "recommendedAction": None,
        },
        {
            "id": "spc-alignment",
            "checkType": "spc_alignment",
            "name": "SPC Alignment",
            "status": "ok",
            "message": "Aligned with current SPC.",
            "details": "Indication, dose, and duration match SPC v2024.3.",
            "recommendedAction": None,
        },
    ],
    "RX2024-006": [
        {
            "id": "duplicate-therapy",
            "checkType": "duplicate_therapy",
            "name": "Duplicate Therapy Check",
            "status": "ok",
            "message": "No duplicate biguanide on file.",
            "details": "No other metformin-containing product active.",
            "recommendedAction": None,
        },
        {
            "id": "interactions",
            "checkType": "interactions",
            "name": "Drug-Drug Interactions",
            "status": "ok",
            "message": "No major interactions detected.",
            "details": "No iodinated contrast scheduled, no recent loop diuretic addition.",
            "recommendedAction": None,
        },
        {
            "id": "contraindications",
            "checkType": "contraindications",
            "name": "Contraindications",
            "status": "block",
            "message": "eGFR 24 mL/min/1.73m² — metformin contraindicated. Do not dispense.",
            "details": (
                "Most recent eGFR on file is 24 mL/min/1.73m² (2026-05-01). The SPC "
                "contraindicates metformin below 30 mL/min/1.73m² due to lactic-acidosis "
                "risk, which is elevated further at age 78."
            ),
            "recommendedAction": (
                "Hold the dispense and contact the prescriber — metformin should be stopped "
                "or switched at this renal function. Do not dispense without explicit "
                "prescriber direction."
            ),
        },
        {
            "id": "dose-validation",
            "checkType": "dose_validation",
            "name": "Dose Validation",
            "status": "ok",
            "message": "Dose within SPC recommended range.",
            "details": "850 mg twice daily is within the SPC range (max 2,550 mg/day in divided doses).",
            "recommendedAction": None,
        },
        {
            "id": "spc-alignment",
            "checkType": "spc_alignment",
            "name": "SPC Alignment",
            "status": "ok",
            "message": "Aligned with current SPC.",
            "details": "Indication, dose, and duration match SPC v2024.3.",
            "recommendedAction": None,
        },
    ],
    "RX2024-007": [
        {
            "id": "duplicate-therapy",
            "checkType": "duplicate_therapy",
            "name": "Duplicate Therapy Check",
            "status": "ok",
            "message": "No duplicate statin on file.",
            "details": "No other HMG-CoA reductase inhibitor active.",
            "recommendedAction": None,
        },
        {
            "id": "interactions",
            "checkType": "interactions",
            "name": "Drug-Drug Interactions",
            "status": "ok",
            "message": "No major interactions detected.",
            "details": "No clarithromycin, no cyclosporine, no gemfibrozil on file.",
            "recommendedAction": None,
        },
        {
            "id": "contraindications",
            "checkType": "contraindications",
            "name": "Contraindications",
            "status": "ok",
            "message": "No contraindications identified.",
            "details": "No active liver disease, not pregnant.",
            "recommendedAction": None,
        },
        {
            "id": "dose-validation",
            "checkType": "dose_validation",
            "name": "Dose Validation",
            "status": "ok",
            "message": "Dose within SPC recommended range.",
            "details": "40 mg once daily is within the standard atorvastatin range.",
            "recommendedAction": None,
        },
        {
            "id": "spc-alignment",
            "checkType": "spc_alignment",
            "name": "SPC Alignment",
            "status": "ok",
            "message": "Aligned with current SPC.",
            "details": "Indication, dose, and duration match SPC v2024.3.",
            "recommendedAction": None,
        },
    ],
    "RX2024-008": [
        {
            "id": "duplicate-therapy",
            "checkType": "duplicate_therapy",
            "name": "Duplicate Therapy Check",
            "status": "review",
            "message": "Patient is already on Aspirin 100 mg — overlapping antiplatelets.",
            "details": "Adding Clopidogrel on top of Aspirin (dual antiplatelet therapy) is appropriate after recent ACS or stenting, but otherwise raises bleeding risk without added benefit.",
            "recommendedAction": "Confirm clinical indication for DAPT with the prescriber and document the planned duration.",
        },
        {
            "id": "interactions",
            "checkType": "interactions",
            "name": "Drug-Drug Interactions",
            "status": "review",
            "message": "PPI on file — clopidogrel efficacy may be reduced.",
            "details": "Patient is on Omeprazole, which inhibits CYP2C19 and may reduce conversion of clopidogrel to its active metabolite.",
            "recommendedAction": "Consider switching the PPI to pantoprazole or use an H2-blocker if reflux control is still required.",
        },
        {
            "id": "contraindications",
            "checkType": "contraindications",
            "name": "Contraindications",
            "status": "ok",
            "message": "No contraindications identified.",
            "details": "No active pathological bleeding on file.",
            "recommendedAction": None,
        },
        {
            "id": "dose-validation",
            "checkType": "dose_validation",
            "name": "Dose Validation",
            "status": "ok",
            "message": "Dose within SPC recommended range.",
            "details": "75 mg once daily is the standard maintenance dose.",
            "recommendedAction": None,
        },
    ],
    "RX2024-009": [
        {
            "id": "duplicate-therapy",
            "checkType": "duplicate_therapy",
            "name": "Duplicate Therapy Check",
            "status": "ok",
            "message": "No duplicate antibiotic on file.",
            "details": "No other beta-lactam in the patient's history.",
            "recommendedAction": None,
        },
        {
            "id": "interactions",
            "checkType": "interactions",
            "name": "Drug-Drug Interactions",
            "status": "ok",
            "message": "No major interactions detected.",
            "details": "Patient is not on any other prescribed medication.",
            "recommendedAction": None,
        },
        {
            "id": "contraindications",
            "checkType": "contraindications",
            "name": "Contraindications",
            "status": "ok",
            "message": "No contraindications identified.",
            "details": "No documented penicillin hypersensitivity.",
            "recommendedAction": None,
        },
        {
            "id": "dose-validation",
            "checkType": "dose_validation",
            "name": "Dose Validation",
            "status": "review",
            "message": "Paediatric weight-based dose — verify weight before dispensing.",
            "details": "SPC paediatric dose for otitis media is 25–50 mg/kg/day in divided doses. The prescription assumes ~24 kg; the last weight on file is from 8 months ago.",
            "recommendedAction": "Ask the parent to confirm the current weight before dispensing the suspension volume.",
        },
        {
            "id": "spc-alignment",
            "checkType": "spc_alignment",
            "name": "SPC Alignment",
            "status": "ok",
            "message": "Aligned with current paediatric SPC.",
            "details": "Indication, dose band, and duration match SPC v2024.3.",
            "recommendedAction": None,
        },
    ],
}
