import { useMemo } from "react";

// Detects any code point outside 7-bit ASCII (>= U+0080). Strictly this is a
// *non-ASCII* test, which is broader than "non-Latin" — `é`, `ü`, `ñ` are Latin
// yet non-ASCII. For HMVS pack codes, which are ASCII alphanumeric, the
// distinction is moot: any non-ASCII character is equally a wrong-layout signal.
// (The hook keeps the name `useNonLatinInputDetector` because that's its
// agreed call-site contract.)
//
// A non-ASCII character in the field is our proxy for "the OS keyboard layout
// isn't English". Browsers expose no dependable way to read the active input
// language: navigator.keyboard.getLayoutMap() is Chromium-only, permission-
// adjacent, and reports the *physical* key layout rather than the language the
// user is actually typing in. So we infer it from what lands in the field.
//
// The 0x00-0x7F range necessarily spans ASCII control chars — that's the very
// definition of "non-ASCII", so the no-control-regex rule is suppressed below.
// eslint-disable-next-line no-control-regex
const NON_ASCII = /[^\x00-\x7F]/;

/** True when `value` contains any non-ASCII (e.g. Greek) character. */
export function useNonLatinInputDetector(value: string): boolean {
  return useMemo(() => NON_ASCII.test(value), [value]);
}
