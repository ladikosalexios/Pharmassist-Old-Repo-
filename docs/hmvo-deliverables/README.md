# HMVO Gate-2 deliverable — H1 HMVS-input safeguards

Records the **Caps Lock + keyboard-layout safeguards** on the HMVS pack-code
input (deliverable **points 5 + 6**). This is the only build deliverable gating
platform + test-book access.

> Scope guard: **mock data only, no patient data, no feature beyond points 5 + 6.**

## What the recording shows

Demo surface: **`/hmvs-check`** (logged-in route, deliberately not in the nav).
Record with the UI in Greek so both warnings render in Greek:
`…/hmvs-check?lng=el`.

| # | Action | Expected |
|---|--------|----------|
| 1 | Caps Lock **OFF** — type `01057001234567892` | accepted; submit enabled |
| 2 | Caps Lock **ON** — type a char | Greek warning *«Απενεργοποιήστε το Caps Lock πριν συνεχίσετε»*; submit greyed/disabled |
| 3 | Caps Lock **OFF** — type | warning clears; submit enabled |
| 4 | Switch OS keyboard to **Greek** — type | Greek char in field → *«Αλλάξτε τη γλώσσα πληκτρολογίου σε αγγλικά πριν συνεχίσετε»*; submit disabled |
| 5 | Switch back to **English** — clear/retype | warning clears; submit enabled |

Target: **≤ 2 min**. The Caps Lock check updates on a keystroke *in the field*
(reads `getModifierState` on keydown), so press a key after toggling Caps Lock.

## Why the character-analysis heuristic is defensible

Whitepaper **EMVS1344** (Solidsoft, *"Understanding Keyboard Emulation"*,
7 Jun 2026): a keyboard-layout mismatch manifests as wrong / non-Latin
characters in scanned input (their Czech example: `0 → é`) — exactly the
failure mode H1's character-analysis detector catches. Re-confirm with Vassilis
when sending the recording (see `email-draft.md`).

## Implementation (for reference, not part of the recording)

- Component: [`frontend/src/components/HmvsSecureInput.tsx`](../../frontend/src/components/HmvsSecureInput.tsx)
- Detectors: [`useCapsLockState`](../../frontend/src/hooks/useCapsLockState.ts), [`useNonLatinInputDetector`](../../frontend/src/hooks/useNonLatinInputDetector.ts)
- Demo screen: [`frontend/src/pages/HmvsCheck.tsx`](../../frontend/src/pages/HmvsCheck.tsx)
- Greek warnings: `hmvs.capsLockWarning`, `hmvs.layoutWarning` (`frontend/src/locales/el.json`)
- Unit tests: `frontend/src/components/HmvsSecureInput.test.tsx`

## Delivery checklist

- [ ] Record the ≤2-min clip per the table above (UI in Greek).
- [ ] Save it here as `hmvs-input-safeguards-2026-06-08.<ext>`.
- [ ] Send `email-draft.md` to the HMVO contact (original thread), referencing
      IT-supplier ticket **[TICKET-REF]** and including the Vassilis confirmation ask.
- [ ] Note the send date + recipient below.

| Recording file | Sent to | Date | Ticket ref |
|----------------|---------|------|------------|
| _pending_ | _pending_ | _pending_ | _pending_ |
