"""Patient instruction rendering (SPC-driven) + delivery log.

The counselling sheet is assembled per medicine from the SPC store
(``services/spc.MOCK_SPC``, keyed by ATC): §4.2 food/intake guidance, §6.3/§6.4
in-use storage, and disposal. Drugs without SPC coverage get only the
prescription facts + the generic safety sections — the sheet never invents
drug-specific advice (the old template hardcoded warfarin's vitamin-K line
for every drug; that class of bug is what this rewrite removes).

Generation is server-side only — the frontend previews by calling
POST /instructions/generate, so there is exactly one template.
"""

from .spc import MOCK_SPC

# In-memory log of instruction sends (would be email/SMS/queue in prod).
INSTRUCTION_DELIVERIES: list = []


def _meds(rx: dict) -> list[dict]:
    """Medicine list, tolerant of every rx shape we produce.

    Mock: ``medication`` dict (+ optional ``medications`` list). Live scans:
    ``medications`` list of partials (drugName/atcCode/nhrn) with
    ``medication`` as a plain name string.
    """
    meds = rx.get("medications")
    if isinstance(meds, list) and meds:
        return [m for m in meds if isinstance(m, dict)]
    m = rx.get("medication")
    if isinstance(m, dict):
        return [m]
    if isinstance(m, str) and m:
        return [{"drugName": m}]
    return []


def _patient_name(rx: dict) -> str:
    patient = rx.get("patient")
    if isinstance(patient, dict) and patient.get("name"):
        return patient["name"]
    return rx.get("patientName") or "—"


def _med_lines(med: dict, el: bool) -> list[str]:
    """Per-medicine block: prescription facts + SPC-derived guidance."""
    spc = MOCK_SPC.get(med.get("atcCode") or "") or {}
    lines: list[str] = []

    dose_bits = [med.get(k) for k in ("dose", "form", "route") if med.get(k)]
    if el:
        if dose_bits:
            lines.append(f"  Δόση: {med.get('dose')} ({', '.join(str(b) for b in dose_bits[1:])})")
        if med.get("frequency"):
            lines.append(f"  Συχνότητα: {med['frequency']}")
        if med.get("treatmentDuration"):
            lines.append(f"  Διάρκεια θεραπείας: {med['treatmentDuration']}")
        if not dose_bits and spc.get("recommendedDosage"):
            lines.append(f"  Συνήθης δοσολογία (SPC): {spc['recommendedDosage']}")
        if spc.get("foodInstructions"):
            lines += ["  Λήψη με τροφή (SPC):", f"    {spc['foodInstructions']}"]
        storage = spc.get("storage") or {}
        if storage.get("afterOpening"):
            lines += ["  Φύλαξη μετά το άνοιγμα (SPC):", f"    {storage['afterOpening']}"]
        if storage.get("disposal"):
            lines.append(f"  Απόρριψη: {storage['disposal']}")
    else:
        if dose_bits:
            lines.append(f"  Dose: {med.get('dose')} ({', '.join(str(b) for b in dose_bits[1:])})")
        if med.get("frequency"):
            lines.append(f"  Frequency: {med['frequency']}")
        if med.get("treatmentDuration"):
            lines.append(f"  Treatment duration: {med['treatmentDuration']}")
        if not dose_bits and spc.get("recommendedDosage"):
            lines.append(f"  Usual dosage (SPC): {spc['recommendedDosage']}")
        if spc.get("foodInstructions"):
            lines += ["  Food & intake (SPC):", f"    {spc['foodInstructions']}"]
        storage = spc.get("storage") or {}
        if storage.get("afterOpening"):
            lines += ["  Storage after opening (SPC):", f"    {storage['afterOpening']}"]
        if storage.get("disposal"):
            lines.append(f"  Disposal: {storage['disposal']}")
    return lines


def render_instructions(rx: dict, language: str, opts: dict) -> str:
    """Format a patient counselling sheet, in Greek or English.

    One block per medicine (multi-med prescriptions supported); drug-specific
    guidance comes ONLY from the SPC store for that medicine's ATC.
    """
    meds = _meds(rx)
    notes = (opts or {}).get("additionalNotes", "").strip()
    include_side = bool((opts or {}).get("includeSideEffects", True))
    include_lifestyle = bool((opts or {}).get("includeLifestyle", True))

    el = (language or "en").lower().startswith("el")
    title_drugs = " + ".join(m.get("drugName") or "—" for m in meds) or "—"

    if el:
        lines = [f"ΟΔΗΓΙΕΣ ΑΣΘΕΝΟΥΣ — {title_drugs}", f"Ασθενής: {_patient_name(rx)}"]
        for i, med in enumerate(meds, start=1):
            med_lines = _med_lines(med, el=True)
            if not med_lines and len(meds) == 1:
                continue  # nothing to say under a bare "ΛΗΨΗ:" header
            header = (
                f"ΦΑΡΜΑΚΟ {i}/{len(meds)}: {med.get('drugName') or '—'}"
                if len(meds) > 1
                else "ΛΗΨΗ:"
            )
            lines += ["", header]
            lines += med_lines
        if notes:
            lines += ["", "ΣΗΜΑΝΤΙΚΑ ΣΗΜΕΙΑ:", notes]
        if include_side:
            lines += [
                "",
                "ΠΙΘΑΝΕΣ ΑΝΕΠΙΘΥΜΗΤΕΣ ΕΝΕΡΓΕΙΕΣ:",
                "Ενημερώστε αμέσως τον φαρμακοποιό ή ιατρό σας αν παρατηρήσετε ασυνήθιστα συμπτώματα.",
            ]
        if include_lifestyle:
            lines += [
                "",
                "ΓΕΝΙΚΕΣ ΟΔΗΓΙΕΣ:",
                "Ακολουθήστε πιστά τη δοσολογία. Μη διακόπτετε τη θεραπεία χωρίς οδηγία ιατρού.",
            ]
        lines += [
            "",
            "ΑΝ ΞΕΧΑΣΕΤΕ ΜΙΑ ΔΟΣΗ:",
            "Πάρτε την μόλις τη θυμηθείτε, εκτός αν πλησιάζει η ώρα της επόμενης. Μη διπλασιάσετε.",
            "",
            "ΕΠΙΚΟΙΝΩΝΙΑ ΜΕ ΙΑΤΡΟ ΑΝ:",
            "• Εμφανιστούν σοβαρά ή ασυνήθιστα συμπτώματα",
            "• Δεν βελτιώνεστε εντός λίγων ημερών",
            "• Ξεκινήσετε νέα φαρμακευτική αγωγή",
        ]
    else:
        lines = [f"PATIENT INSTRUCTIONS — {title_drugs}", f"Patient: {_patient_name(rx)}"]
        for i, med in enumerate(meds, start=1):
            med_lines = _med_lines(med, el=False)
            if not med_lines and len(meds) == 1:
                continue  # nothing to say under a bare "HOW TO TAKE:" header
            header = (
                f"MEDICINE {i}/{len(meds)}: {med.get('drugName') or '—'}"
                if len(meds) > 1
                else "HOW TO TAKE:"
            )
            lines += ["", header]
            lines += med_lines
        if notes:
            lines += ["", "KEY POINTS:", notes]
        if include_side:
            lines += [
                "",
                "POSSIBLE SIDE EFFECTS:",
                "Tell your pharmacist or doctor immediately if you notice unusual symptoms.",
            ]
        if include_lifestyle:
            lines += [
                "",
                "GENERAL GUIDANCE:",
                "Follow the prescribed dosage exactly. Do not stop treatment without medical advice.",
            ]
        lines += [
            "",
            "IF YOU MISS A DOSE:",
            "Take it as soon as you remember, unless it is close to the next dose. Do not double up.",
            "",
            "CONTACT YOUR DOCTOR IF:",
            "• You develop severe or unusual symptoms",
            "• You do not improve within a few days",
            "• You start any new medication",
        ]
    return "\n".join(lines)
