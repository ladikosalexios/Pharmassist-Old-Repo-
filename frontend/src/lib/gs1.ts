// GS1 DataMatrix payload parser — narrow to the four AIs the HMVS dispense
// flow needs, and strict about everything else.
//
// A GS1 DataMatrix on a pharma carton encodes Application Identifiers (AIs)
// concatenated into one string. Variable-length AIs are terminated by FNC1
// (transmitted as ASCII Group Separator, 0x1D). Some scanners prepend the
// AIM symbology identifier `]d2`; some emit a leading FNC1; some do both.
//
// The four AIs we read on dispense (HMVO spec, 3 Jun 2026):
//   (01) GTIN    — 14 digits, fixed length
//   (17) EXPIRY  —  6 digits, fixed length (YYMMDD)
//   (10) BATCH   — variable, up to 20 alphanumerics, FNC1-terminated
//   (21) SERIAL  — variable, up to 20 alphanumerics, FNC1-terminated
//
// An unknown AI is treated as a corrupt scan and aborts parsing — better a
// "could not decode" toast than a misattributed dispense.

export interface Gs1Fields {
  gtin?: string;
  serial?: string;
  batch?: string;
  expiry?: string;
}

const FNC1 = 0x1d;
const FIXED_LENGTH: Record<string, number> = {
  "01": 14, // GTIN
  "17": 6, // expiry YYMMDD
};
const VARIABLE: Set<string> = new Set(["10", "21"]);

/**
 * Parse a GS1 DataMatrix payload into the four AIs the dispense flow needs.
 * Returns whatever decoded cleanly; the caller validates that all four are
 * present before issuing an HMVS call.
 *
 * Tolerates:
 *   - leading AIM identifier `]d2`
 *   - leading FNC1 (0x1D) before the first AI
 *   - FNC1 between AIs as the variable-length terminator
 *
 * Aborts (returns whatever was decoded so far) on an unknown AI rather than
 * skipping — a misread fixed-length AI would otherwise corrupt every
 * subsequent field.
 */
export function parseGs1(payload: string): Gs1Fields {
  let s = payload;
  if (s.startsWith("]d2")) s = s.slice(3);
  if (s.charCodeAt(0) === FNC1) s = s.slice(1);

  const out: Gs1Fields = {};
  let i = 0;
  while (i + 2 <= s.length) {
    const ai = s.slice(i, i + 2);
    i += 2;
    const fixed = FIXED_LENGTH[ai];
    if (fixed !== undefined) {
      const val = s.slice(i, i + fixed);
      if (val.length < fixed) break;
      i += fixed;
      assign(out, ai, val);
    } else if (VARIABLE.has(ai)) {
      const end = findFnc1(s, i);
      const val = s.slice(i, end);
      i = end === s.length ? end : end + 1;
      assign(out, ai, val);
    } else {
      // Unknown AI — stop here so we don't keep parsing garbage.
      break;
    }
  }
  return out;
}

function findFnc1(s: string, from: number): number {
  for (let i = from; i < s.length; i++) {
    if (s.charCodeAt(i) === FNC1) return i;
  }
  return s.length;
}

function assign(out: Gs1Fields, ai: string, val: string): void {
  if (ai === "01") out.gtin = val;
  else if (ai === "17") out.expiry = val;
  else if (ai === "10") out.batch = val;
  else if (ai === "21") out.serial = val;
}

/** True iff every AI required for an HMVS verify call decoded cleanly. */
export function isCompletePack(fields: Gs1Fields): fields is Required<Gs1Fields> {
  return Boolean(fields.gtin && fields.serial && fields.batch && fields.expiry);
}
