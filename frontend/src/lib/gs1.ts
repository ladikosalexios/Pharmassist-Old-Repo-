// GS1 DataMatrix payload parser — extract the four AIs the HMVS dispense flow
// needs (GTIN, serial, batch, expiry) from a scanned barcode.
//
// A GS1 DataMatrix on a pharma carton encodes Application Identifiers (AIs)
// concatenated into one string. Variable-length AIs are terminated by FNC1
// (transmitted as ASCII Group Separator, 0x1D); pre-defined-length AIs carry no
// separator. Some scanners prepend the AIM symbology identifier `]d2`; some emit
// a leading FNC1; some do both.
//
// The four AIs we extract on dispense:
//   (01) GTIN    — 14 digits, fixed length
//   (17) EXPIRY  —  6 digits, fixed length (YYMMDD)
//   (10) BATCH   — variable, FNC1-terminated
//   (21) SERIAL  — variable, FNC1-terminated
//
// Packs may legally carry ADDITIONAL AIs (NHRN, production date, active potency,
// …) in ANY order (EMVS/HMVO testbook prerequisite — case 11_CHARACTER_SET / CS_4).
// So the parser SKIPS AIs it doesn't extract — fixed-length ones by their known
// length, everything else as variable (to the next FNC1) — rather than aborting.

export interface Gs1Fields {
  gtin?: string;
  serial?: string;
  batch?: string;
  expiry?: string;
}

const FNC1 = 0x1d;

// Data length (EXCLUDING the 2-digit AI prefix) of GS1 "pre-defined length" AIs —
// the only AIs that carry NO FNC1 separator (GS1 General Specifications §7.8.6.1,
// keyed by the first two digits; value = total predefined length − 2). Every other
// AI is variable-length and FNC1-terminated. Used to skip non-extracted AIs
// without over-reading into the following element.
const PREDEFINED_DATA_LEN: Record<string, number> = {
  "00": 16,
  "01": 14,
  "02": 14,
  "03": 14,
  "04": 16,
  "11": 6,
  "12": 6,
  "13": 6,
  "14": 6,
  "15": 6,
  "16": 6,
  "17": 6,
  "18": 6,
  "19": 6,
  "20": 2,
  "31": 8,
  "32": 8,
  "33": 8,
  "34": 8,
  "35": 8,
  "36": 8,
  "41": 14,
};

/**
 * Parse a GS1 DataMatrix payload into the four AIs the dispense flow needs.
 * Returns whatever decoded cleanly; the caller validates that all four are
 * present (`isCompletePack`) before issuing an HMVS call.
 *
 * Tolerates: leading `]d2`, leading FNC1, FNC1 between AIs, AIs in any order, and
 * additional (non-extracted) AIs — which are skipped rather than aborted on.
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

    if (ai === "01" || ai === "17") {
      // Extracted, fixed-length.
      const len = ai === "01" ? 14 : 6;
      const val = s.slice(i, i + len);
      if (val.length < len) break; // truncated — stop
      i += len;
      assign(out, ai, val);
    } else if (ai === "10" || ai === "21") {
      // Extracted, variable-length (FNC1-terminated).
      const end = findFnc1(s, i);
      assign(out, ai, s.slice(i, end));
      i = end === s.length ? end : end + 1;
    } else if (ai in PREDEFINED_DATA_LEN) {
      // Additional fixed-length AI we don't need — skip its data (no FNC1).
      const len = PREDEFINED_DATA_LEN[ai];
      if (i + len > s.length) break; // truncated — stop
      i += len;
    } else {
      // Additional variable-length AI — skip to the next FNC1 (or end).
      const end = findFnc1(s, i);
      i = end === s.length ? end : end + 1;
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

// We do NOT validate AI *content* locally (e.g. that GTIN/expiry are digit-only).
// The EMVS/HMVO qualification testbook (case 12_INVALID_GS1_ELEMENTS) requires a
// pack with an invalid GTIN or expiry to be SENT so the registry returns the
// appropriate 422 (e.g. 61020008 / 61020007) — confirmed live against IQE. A
// genuinely unreadable scan (missing AIs) is still rejected locally because
// isCompletePack stays false; only *malformed content* in present AIs is sent.
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
