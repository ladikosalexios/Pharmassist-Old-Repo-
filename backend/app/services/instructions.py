"""Patient instruction template + delivery log."""

# In-memory log of instruction sends (would be email/SMS/queue in prod).
INSTRUCTION_DELIVERIES: list = []


def render_instructions(rx: dict, language: str, opts: dict) -> str:
    """Format a patient counselling sheet from a prescription, in Greek or English.

    Mirrors the frontend's ``lib/instructions.ts`` so the live preview and
    server-rendered output stay byte-identical.
    """
    drug = rx["medication"]
    pt = rx["patient"]
    notes = (opts or {}).get("additionalNotes", "").strip()
    include_side = bool((opts or {}).get("includeSideEffects", True))
    include_lifestyle = bool((opts or {}).get("includeLifestyle", True))

    lang = (language or "en").lower()
    if lang.startswith("el"):
        lines = [
            f"ΟΔΗΓΙΕΣ ΑΣΘΕΝΟΥΣ — {drug['drugName']}",
            f"Ασθενής: {pt['name']}",
            "",
            "ΛΗΨΗ:",
            f"  Δόση: {drug['dose']} ({drug['form']}, {drug['route']})",
            f"  Συχνότητα: {drug['frequency']}",
            f"  Διάρκεια θεραπείας: {drug['treatmentDuration']}",
        ]
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
                "ΔΙΑΤΡΟΦΙΚΕΣ / ΤΡΟΠΟΥ ΖΩΗΣ ΟΔΗΓΙΕΣ:",
                "Διατηρήστε σταθερή πρόσληψη βιταμίνης Κ. Αποφύγετε αλκοόλ. Ενυδάτωση.",
            ]
        lines += [
            "",
            "ΑΝ ΞΕΧΑΣΕΤΕ ΜΙΑ ΔΟΣΗ:",
            "Πάρτε την μόλις τη θυμηθείτε, εκτός αν πλησιάζει η ώρα της επόμενης. Μη διπλασιάσετε.",
            "",
            "ΕΠΙΚΟΙΝΩΝΙΑ ΜΕ ΙΑΤΡΟ ΑΝ:",
            "• Εμφανιστούν σοβαρά συμπτώματα ή αιμορραγία",
            "• Δεν βελτιώνεστε εντός λίγων ημερών",
            "• Ξεκινήσετε νέα φαρμακευτική αγωγή",
        ]
    else:
        lines = [
            f"PATIENT INSTRUCTIONS — {drug['drugName']}",
            f"Patient: {pt['name']}",
            "",
            "HOW TO TAKE:",
            f"  Dose: {drug['dose']} ({drug['form']}, {drug['route']})",
            f"  Frequency: {drug['frequency']}",
            f"  Treatment duration: {drug['treatmentDuration']}",
        ]
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
                "DIET / LIFESTYLE:",
                "Maintain consistent vitamin K intake. Avoid alcohol. Stay hydrated.",
            ]
        lines += [
            "",
            "IF YOU MISS A DOSE:",
            "Take it as soon as you remember, unless it is close to the next dose. Do not double up.",
            "",
            "CONTACT YOUR DOCTOR IF:",
            "• You develop severe symptoms or bleeding",
            "• You do not improve within a few days",
            "• You start any new medication",
        ]
    return "\n".join(lines)
