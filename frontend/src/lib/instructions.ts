// Instruction SHEETS are rendered server-side (POST /instructions/generate —
// one SPC-enriched template; the old client-side mirror is gone). This module
// keeps only small client-side helpers.

import type { InstructionsLanguage, Prescription } from "../types";

/** Pre-fill the additional-notes textarea with key SPC contraindications, when available. */
export function defaultAdditionalNotes(rx: Prescription, language: InstructionsLanguage): string {
  const c = rx.spcQuickReference?.contraindications ?? [];
  if (c.length === 0) return "";
  const lead =
    language === "el"
      ? "Σημειώστε τα παρακάτω βασικά σημεία SPC:"
      : "Note the following key SPC points:";
  return [lead, ...c.map((line) => `• ${line}`)].join("\n");
}
