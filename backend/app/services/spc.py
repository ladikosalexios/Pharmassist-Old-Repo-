"""Summary of Product Characteristics: DB-backed resolution + mock fallback.

``resolve_spc`` is the single serving path (GET /spc/{atc}, instruction
rendering): ingested spc_documents rows win over the hand-written MOCK_SPC
fixture, which stays as the demo fallback (and the byte-identical mock-mode
path). Resolution: docs for the exact barcode → docs for the ATC → MOCK_SPC
→ None; within a pool, verified beats unverified, then newest wins, and a
PIL document's patient-language wording overlays the SPC's storage/food
fields.
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.models.spc_document import SpcDocument

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
            {
                "drug": "Aspirin",
                "effect": "Concurrent use significantly increases bleeding risk; use only with documented indication and close INR monitoring.",
            },
            {
                "drug": "NSAIDs",
                "effect": "Increased bleeding risk via platelet inhibition and gastric mucosal damage; avoid concurrent use.",
            },
            {
                "drug": "Amiodarone",
                "effect": "Potentiates warfarin effect via CYP2C9 inhibition; reduce warfarin dose by 30–50% and recheck INR within 5 days.",
            },
            {
                "drug": "Fluconazole",
                "effect": "Marked CYP2C9 inhibition; INR can rise sharply within 3–5 days.",
            },
        ],
        # SPC §4.4 — warnings/precautions require extra care or monitoring but do
        # NOT forbid use; distinct from §4.3 contraindications above.
        "precautions": [
            "Regular INR monitoring is essential — more frequently after any change in dose, diet, or co-medication",
            "Increased bleeding risk in the elderly, in hepatic/renal impairment, and with concurrent antiplatelets",
            "Counsel the patient to report signs of bleeding: unusual bruising, dark stools, blood in urine",
            "Avoid intramuscular injections while anticoagulated (haematoma risk)",
        ],
        # SPC §6.3/§6.4 storage + §6.6 disposal.
        "storage": {
            "conditions": "Store below 25 °C in the original package, protected from light and moisture.",
            "afterOpening": None,  # tablets — no in-use shelf life
            "disposal": "Return unused or expired tablets to the pharmacy; do not dispose of via household waste or wastewater.",
        },
        # SPC §4.2 food guidance — None when there is no food-related instruction.
        "foodInstructions": (
            "Take at the same time each day, with or without food. Keep vitamin K intake "
            "(green leafy vegetables) CONSISTENT — sudden dietary changes shift the INR. "
            "Avoid cranberry juice and limit alcohol."
        ),
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
            {
                "drug": "Methotrexate",
                "effect": "Reduced renal excretion of methotrexate; increased toxicity risk — monitor closely.",
            },
            {
                "drug": "Allopurinol",
                "effect": "Increased risk of skin rash when used concurrently.",
            },
            {
                "drug": "Warfarin",
                "effect": "May potentiate anticoagulant effect; monitor INR during and after a course.",
            },
        ],
        "precautions": [
            "A generalised erythematous rash in patients with glandular fever (EBV) is common — avoid if infectious mononucleosis is suspected",
            "Extend the dosing interval in renal impairment (CrCl < 30 mL/min)",
            "Prolonged use may lead to overgrowth of non-susceptible organisms; antibiotic-associated (C. difficile) colitis is possible — stop and review if severe diarrhoea develops",
        ],
        "storage": {
            "conditions": "Capsules/tablets: store below 25 °C in a dry place.",
            # The classic in-use shelf-life example: reconstituted suspension.
            "afterOpening": (
                "Oral suspension: once reconstituted, store in the refrigerator (2–8 °C) "
                "and discard after 14 days. Shake well before each dose."
            ),
            "disposal": "Return any remaining suspension to the pharmacy after the course — do not keep leftover antibiotics.",
        },
        "foodInstructions": (
            "May be taken with or without food; taking it at the start of a meal reduces "
            "stomach upset. Complete the full prescribed course."
        ),
    },
    "A10BA02": {
        "atcCode": "A10BA02",
        "drugName": "Metformin",
        "version": "v3.1",
        "updatedAt": "2026-03-02T00:00:00Z",
        "fullSpcUrl": "https://www.eof.gr/spc/metformin",
        "recommendedDosage": (
            "Adults: start 500–850 mg 2–3 times daily with or after meals; titrate over "
            "10–15 days against blood glucose. Maximum 3 g/day in divided doses."
        ),
        "fullSpcText": (
            "1. THERAPEUTIC INDICATIONS\n"
            "Treatment of type 2 diabetes mellitus, particularly in overweight patients, when "
            "dietary management and exercise alone do not result in adequate glycaemic control.\n\n"
            "2. POSOLOGY AND METHOD OF ADMINISTRATION\n"
            "Start 500–850 mg 2–3 times daily during or after meals; titrate slowly to reduce "
            "gastrointestinal side effects. Assess renal function before initiation.\n\n"
            "3. CONTRAINDICATIONS\n"
            "See Key Contraindications section.\n\n"
            "4. SPECIAL WARNINGS AND PRECAUTIONS\n"
            "Lactic acidosis is a rare but serious metabolic complication — risk rises with renal "
            "impairment, dehydration, and iodinated contrast media."
        ),
        "contraindications": [
            "Severe renal failure (GFR < 30 mL/min)",
            "Acute conditions with the potential to alter renal function (dehydration, severe infection, shock)",
            "Acute or chronic disease which may cause tissue hypoxia (cardiac or respiratory failure, recent MI)",
            "Hepatic insufficiency, acute alcohol intoxication, alcoholism",
        ],
        "majorInteractions": [
            {
                "drug": "Iodinated contrast media",
                "effect": "Risk of contrast-induced nephropathy → lactic acidosis; pause metformin before or at the time of imaging and restart ≥48 h after, once renal function is re-checked.",
            },
            {
                "drug": "Alcohol",
                "effect": "Acute intoxication potentiates the risk of lactic acidosis, especially when fasting or with hepatic impairment.",
            },
            {
                "drug": "Diuretics (especially loop)",
                "effect": "May impair renal function and raise metformin accumulation risk — monitor creatinine.",
            },
        ],
        "precautions": [
            "Check renal function (eGFR) before initiation and at least annually thereafter — more often in the elderly",
            "Pause during acute illness with dehydration (vomiting, diarrhoea, fever) and around iodinated-contrast imaging",
            "Counsel on lactic-acidosis warning signs: muscle cramps, abdominal pain, deep laboured breathing, unusual fatigue",
            "Long-term use can reduce vitamin B12 levels — consider periodic monitoring",
        ],
        "storage": {
            "conditions": "No special storage conditions; keep below 30 °C in the original package.",
            "afterOpening": None,
            "disposal": "Return unused tablets to the pharmacy; do not dispose of via household waste.",
        },
        "foodInstructions": (
            "Take WITH or immediately AFTER meals to reduce stomach upset (nausea, diarrhoea) — "
            "the most common reason patients stop taking it. Swallow whole with a glass of water."
        ),
    },
    "C10AA05": {
        "atcCode": "C10AA05",
        "drugName": "Atorvastatin",
        "version": "v2.2",
        "updatedAt": "2026-02-18T00:00:00Z",
        "fullSpcUrl": "https://www.eof.gr/spc/atorvastatin",
        "recommendedDosage": (
            "Usual starting dose 10–20 mg once daily; adjust at intervals of 4 weeks or more. "
            "Maximum 80 mg once daily."
        ),
        "fullSpcText": (
            "1. THERAPEUTIC INDICATIONS\n"
            "Hypercholesterolaemia and prevention of cardiovascular disease as an adjunct to "
            "correction of other risk factors.\n\n"
            "2. POSOLOGY AND METHOD OF ADMINISTRATION\n"
            "10–80 mg once daily, at any time of day, with or without food.\n\n"
            "3. CONTRAINDICATIONS\n"
            "See Key Contraindications section.\n\n"
            "4. SPECIAL WARNINGS AND PRECAUTIONS\n"
            "Myopathy/rhabdomyolysis risk rises with interacting medicines (strong CYP3A4 "
            "inhibitors), high doses, hypothyroidism, and renal impairment."
        ),
        "contraindications": [
            "Active liver disease or unexplained persistent elevation of serum transaminases (> 3× ULN)",
            "Pregnancy and breast-feeding",
            "Hypersensitivity to atorvastatin or any excipient",
        ],
        "majorInteractions": [
            {
                "drug": "Clarithromycin (and other strong CYP3A4 inhibitors)",
                "effect": "Markedly increased atorvastatin exposure → myopathy/rhabdomyolysis risk; suspend the statin for the antibiotic course or cap the dose per SPC.",
            },
            {
                "drug": "Ciclosporin",
                "effect": "Greatly increased statin exposure; combination should be avoided.",
            },
            {
                "drug": "Gemfibrozil / fibrates",
                "effect": "Additive myopathy risk; use only if clearly indicated, at the lowest statin dose.",
            },
        ],
        "precautions": [
            "Liver function tests before initiation and if symptoms of hepatic injury appear",
            "Counsel the patient to report unexplained muscle pain, tenderness, or weakness promptly — especially with fever or malaise",
            "Higher myopathy risk in hypothyroidism, renal impairment, age > 70, and high alcohol intake",
            "Measure CK before starting in patients with predisposing factors for rhabdomyolysis",
        ],
        "storage": {
            "conditions": "Store below 25 °C.",
            "afterOpening": None,
            "disposal": "Return unused tablets to the pharmacy.",
        },
        "foodInstructions": (
            "Can be taken at any time of day, with or without food. AVOID large quantities of "
            "grapefruit juice (more than ~1 L/day) — it raises atorvastatin levels."
        ),
    },
    "J01FA09": {
        "atcCode": "J01FA09",
        "drugName": "Clarithromycin",
        "version": "v1.8",
        "updatedAt": "2026-01-22T00:00:00Z",
        "fullSpcUrl": "https://www.eof.gr/spc/clarithromycin",
        "recommendedDosage": (
            "Adults: 250–500 mg every 12 hours for 6–14 days depending on indication and "
            "severity. Renal impairment (CrCl < 30 mL/min): halve the dose."
        ),
        "fullSpcText": (
            "1. THERAPEUTIC INDICATIONS\n"
            "Infections caused by susceptible organisms: pharyngitis, sinusitis, acute exacerbation "
            "of chronic bronchitis, community-acquired pneumonia, skin and soft-tissue infections, "
            "and H. pylori eradication regimens.\n\n"
            "2. POSOLOGY AND METHOD OF ADMINISTRATION\n"
            "250–500 mg twice daily. Tablets may be taken with or without food.\n\n"
            "3. CONTRAINDICATIONS\n"
            "See Key Contraindications section.\n\n"
            "4. SPECIAL WARNINGS AND PRECAUTIONS\n"
            "Clarithromycin is a strong CYP3A4 inhibitor and prolongs the QT interval — screen "
            "co-medication carefully before dispensing."
        ),
        "contraindications": [
            "Hypersensitivity to macrolide antibiotics",
            "Concomitant ergot alkaloids, or QT-prolonging agents such as pimozide",
            "History of QT prolongation or ventricular arrhythmia (torsades de pointes)",
            "Severe hepatic failure combined with renal impairment",
        ],
        "majorInteractions": [
            {
                "drug": "Statins (atorvastatin, simvastatin)",
                "effect": "Strong CYP3A4 inhibition raises statin exposure → myopathy/rhabdomyolysis; suspend or dose-cap the statin for the course.",
            },
            {
                "drug": "Warfarin",
                "effect": "Potentiates anticoagulation; monitor INR during and shortly after the course.",
            },
            {
                "drug": "Colchicine",
                "effect": "Life-threatening colchicine toxicity possible, particularly in renal impairment — avoid.",
            },
        ],
        "precautions": [
            "Screen ALL co-medication for CYP3A4 and QT interactions before dispensing — this is the highest-yield pharmacist check for macrolides",
            "Use with caution in patients with cardiac disease, bradycardia, or electrolyte disturbances (QT prolongation)",
            "Severe diarrhoea during or after treatment may indicate C. difficile colitis",
        ],
        "storage": {
            "conditions": "Tablets: store below 30 °C in the original package.",
            "afterOpening": (
                "Granules for oral suspension: once reconstituted, store below 25 °C (do NOT "
                "refrigerate — the suspension thickens) and discard after 14 days."
            ),
            "disposal": "Return any remaining medicine to the pharmacy after the course.",
        },
        "foodInstructions": None,  # immediate-release tablets: no food requirement
    },
}


def _compose(docs: list[SpcDocument], atc_code: str) -> dict:
    """SpcDetails payload from a pool of documents (see module docstring)."""
    ordered = sorted(docs, key=lambda d: (d.verified, d.fetched_at), reverse=True)
    base = next((d for d in ordered if d.doc_type in ("spc", "combined")), ordered[0])
    pil = next((d for d in ordered if d.doc_type in ("pil", "combined")), None)

    parsed = base.parsed or {}
    payload = {
        "atcCode": atc_code,
        "drugName": parsed.get("drugName") or "",
        "version": f"{base.source}:{base.sha256[:8]}",
        "updatedAt": base.fetched_at.isoformat() if base.fetched_at else None,
        "fullSpcUrl": base.source_url,
        "fullSpcText": None,
        # Frontend getSpc() hard-validates these three — always emit them.
        "recommendedDosage": parsed.get("recommendedDosage") or "",
        "contraindications": parsed.get("contraindications") or [],
        "majorInteractions": parsed.get("majorInteractions") or [],
        "precautions": parsed.get("precautions") or [],
        "storage": parsed.get("storage"),
        "foodInstructions": parsed.get("foodInstructions"),
        # Provenance — drives the auto-extracted / verified badge.
        "source": base.source,
        "sourceUrl": base.source_url,
        "verified": base.verified,
        "extractionMethod": base.extraction_method,
        "docType": base.doc_type,
        "documentId": str(base.id),
    }
    if pil is not None and pil.id != base.id:
        # Patient-language wording wins for the patient-facing fields.
        pil_parsed = pil.parsed or {}
        if pil_parsed.get("foodInstructions"):
            payload["foodInstructions"] = pil_parsed["foodInstructions"]
        if pil_parsed.get("storage"):
            payload["storage"] = pil_parsed["storage"]
    return payload


async def resolve_spc(
    session: AsyncSession, atc_code: str, barcode: str | None = None
) -> dict | None:
    docs: list[SpcDocument] = []
    if barcode:
        docs = list(
            await session.scalars(
                select(SpcDocument).where(
                    SpcDocument.barcode == barcode,
                    SpcDocument.parse_status != "failed",
                )
            )
        )
    if not docs:
        docs = list(
            await session.scalars(
                select(SpcDocument).where(
                    SpcDocument.atc_code == atc_code,
                    SpcDocument.parse_status != "failed",
                )
            )
        )
    if docs:
        return _compose(docs, atc_code)

    mock = MOCK_SPC.get(atc_code)
    if mock:
        return {
            **mock,
            "source": "mock",
            "sourceUrl": mock.get("fullSpcUrl"),
            "verified": False,
            "extractionMethod": "manual",
            "docType": "spc",
            "documentId": None,
        }
    return None
