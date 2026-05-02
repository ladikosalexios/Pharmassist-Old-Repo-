"""Summary of Product Characteristics (mock) keyed by ATC code."""


MOCK_SPC: dict = {
    "B01AA03": {
        "atcCode": "B01AA03",
        "drugName": "Warfarin",
        "version": "v2.9",
        # NB: this date is *after* RX2024-005's issue date (2026-04-28) so the
        # version badge in the UI flips to red and the "review recommended"
        # tooltip fires for that prescription. Adjust if you need a clean run.
        "updatedAt": "2026-04-29T00:00:00Z",
        "fullSpcUrl": "https://www.eof.gr/spc/warfarin",
        "recommendedDosage": (
            "Initial: 5–10 mg daily for 1–2 days, then adjusted based on INR. "
            "Maintenance: 2–10 mg daily. Target INR 2.0–3.0 for most indications. "
            "Elderly and patients with hepatic impairment may require lower starting doses."
        ),
        "fullSpcText": (
            "1. THERAPEUTIC INDICATIONS\n"
            "Warfarin is indicated for the prophylaxis and treatment of venous thromboembolism, "
            "prevention of stroke in non-valvular atrial fibrillation, and as adjunctive therapy "
            "after mechanical heart valve replacement.\n\n"
            "2. POSOLOGY AND METHOD OF ADMINISTRATION\n"
            "Initial dose 5–10 mg once daily for 1–2 days. Maintenance is individualised based "
            "on INR (typical 2–10 mg daily). Take at the same time each day.\n\n"
            "3. CONTRAINDICATIONS\n"
            "See Key Contraindications section.\n\n"
            "4. SPECIAL WARNINGS AND PRECAUTIONS\n"
            "Bleeding risk increases with age, concurrent antiplatelet therapy, recent surgery, "
            "and uncontrolled hypertension. Counsel patients on signs of bleeding.\n\n"
            "5. INTERACTION WITH OTHER MEDICINAL PRODUCTS\n"
            "See Major Interactions section. Many CYP2C9 inhibitors and inducers can shift INR."
        ),
        "contraindications": [
            "Active bleeding or bleeding diathesis",
            "Recent or planned surgery (CNS, eye, traumatic)",
            "Severe hepatic impairment",
            "Pregnancy (except for mechanical heart valves)",
            "Hypersensitivity to warfarin or any excipient",
        ],
        "majorInteractions": [
            {"drug": "Aspirin",     "effect": "Concurrent use significantly increases bleeding risk; use only with documented indication and close INR monitoring."},
            {"drug": "NSAIDs",      "effect": "Increased bleeding risk via platelet inhibition and gastric mucosal damage; avoid concurrent use."},
            {"drug": "Amiodarone",  "effect": "Potentiates warfarin effect via CYP2C9 inhibition; reduce warfarin dose by 30–50% and recheck INR within 5 days."},
            {"drug": "Fluconazole", "effect": "Marked CYP2C9 inhibition; INR can rise sharply within 3–5 days."},
        ],
    },
    "J01CA04": {
        "atcCode": "J01CA04",
        "drugName": "Amoxicillin",
        "version": "v1.4",
        "updatedAt": "2026-01-10T00:00:00Z",
        "fullSpcUrl": "https://www.eof.gr/spc/amoxicillin",
        "recommendedDosage": (
            "Adults: 250–500 mg every 8 hours, depending on severity. "
            "Children >40 kg: as adults. Children ≤40 kg: 20–40 mg/kg/day in three divided doses."
        ),
        "fullSpcText": (
            "1. THERAPEUTIC INDICATIONS\n"
            "Amoxicillin is indicated for bacterial infections including ENT, lower respiratory "
            "tract, urinary tract, skin and soft tissue, and dental infections, where the "
            "causative organism is known or suspected to be susceptible.\n\n"
            "2. POSOLOGY AND METHOD OF ADMINISTRATION\n"
            "Adults: 250–500 mg every 8 hours; severe infections may require higher doses. "
            "Renal impairment: dose interval should be extended.\n\n"
            "3. CONTRAINDICATIONS\n"
            "See Key Contraindications section.\n\n"
            "4. INTERACTIONS\n"
            "See Major Interactions section."
        ),
        "contraindications": [
            "Hypersensitivity to penicillins or any beta-lactam antibiotic",
            "History of severe immediate hypersensitivity reaction (anaphylaxis, Stevens-Johnson syndrome)",
        ],
        "majorInteractions": [
            {"drug": "Methotrexate", "effect": "Reduced renal excretion of methotrexate; increased toxicity risk — monitor closely."},
            {"drug": "Allopurinol",  "effect": "Increased risk of skin rash when used concurrently."},
            {"drug": "Warfarin",     "effect": "May potentiate anticoagulant effect; monitor INR during and after a course."},
        ],
    },
}
