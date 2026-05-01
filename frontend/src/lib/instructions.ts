// Mirror of backend.main._instructions_template — kept here so the page's
// preview updates instantly without an API round-trip on every keystroke.

import type { InstructionsLanguage, InstructionsOptions, Prescription } from "../types";

export function renderInstructions(
  rx: Prescription,
  language: InstructionsLanguage,
  options: InstructionsOptions,
): string {
  const drug = rx.medication;
  const pt = rx.patient;
  const notes = (options.additionalNotes ?? "").trim();

  if (language === "el") {
    const lines: string[] = [
      `ΟΔΗΓΙΕΣ ΑΣΘΕΝΟΥΣ — ${drug.drugName}`,
      `Ασθενής: ${pt.name}`,
      "",
      "ΛΗΨΗ:",
      `  Δόση: ${drug.dose} (${drug.form}, ${drug.route})`,
      `  Συχνότητα: ${drug.frequency}`,
      `  Διάρκεια θεραπείας: ${drug.treatmentDuration}`,
    ];
    if (notes) lines.push("", "ΣΗΜΑΝΤΙΚΑ ΣΗΜΕΙΑ:", notes);
    if (options.includeSideEffects) lines.push(
      "", "ΠΙΘΑΝΕΣ ΑΝΕΠΙΘΥΜΗΤΕΣ ΕΝΕΡΓΕΙΕΣ:",
      "Ενημερώστε αμέσως τον φαρμακοποιό ή ιατρό σας αν παρατηρήσετε ασυνήθιστα συμπτώματα.",
    );
    if (options.includeLifestyle) lines.push(
      "", "ΔΙΑΤΡΟΦΙΚΕΣ / ΤΡΟΠΟΥ ΖΩΗΣ ΟΔΗΓΙΕΣ:",
      "Διατηρήστε σταθερή πρόσληψη βιταμίνης Κ. Αποφύγετε αλκοόλ. Ενυδάτωση.",
    );
    lines.push(
      "", "ΑΝ ΞΕΧΑΣΕΤΕ ΜΙΑ ΔΟΣΗ:",
      "Πάρτε την μόλις τη θυμηθείτε, εκτός αν πλησιάζει η ώρα της επόμενης. Μη διπλασιάσετε.",
      "", "ΕΠΙΚΟΙΝΩΝΙΑ ΜΕ ΙΑΤΡΟ ΑΝ:",
      "• Εμφανιστούν σοβαρά συμπτώματα ή αιμορραγία",
      "• Δεν βελτιώνεστε εντός λίγων ημερών",
      "• Ξεκινήσετε νέα φαρμακευτική αγωγή",
    );
    return lines.join("\n");
  }

  // English (and "other" — currently uses the English template).
  const lines: string[] = [
    `PATIENT INSTRUCTIONS — ${drug.drugName}`,
    `Patient: ${pt.name}`,
    "",
    "HOW TO TAKE:",
    `  Dose: ${drug.dose} (${drug.form}, ${drug.route})`,
    `  Frequency: ${drug.frequency}`,
    `  Treatment duration: ${drug.treatmentDuration}`,
  ];
  if (notes) lines.push("", "KEY POINTS:", notes);
  if (options.includeSideEffects) lines.push(
    "", "POSSIBLE SIDE EFFECTS:",
    "Tell your pharmacist or doctor immediately if you notice unusual symptoms.",
  );
  if (options.includeLifestyle) lines.push(
    "", "DIET / LIFESTYLE:",
    "Maintain consistent vitamin K intake. Avoid alcohol. Stay hydrated.",
  );
  lines.push(
    "", "IF YOU MISS A DOSE:",
    "Take it as soon as you remember, unless it is close to the next dose. Do not double up.",
    "", "CONTACT YOUR DOCTOR IF:",
    "• You develop severe symptoms or bleeding",
    "• You do not improve within a few days",
    "• You start any new medication",
  );
  return lines.join("\n");
}

/** Pre-fill the additional-notes textarea with key SPC contraindications, when available. */
export function defaultAdditionalNotes(rx: Prescription, language: InstructionsLanguage): string {
  const c = rx.spcQuickReference?.contraindications ?? [];
  if (c.length === 0) return "";
  const lead = language === "el"
    ? "Σημειώστε τα παρακάτω βασικά σημεία SPC:"
    : "Note the following key SPC points:";
  return [lead, ...c.map((line) => `• ${line}`)].join("\n");
}
