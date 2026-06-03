# HMVO Compliance & HMVS Integration — Ticket Breakdown

Implementation tickets for the commitments made in the HMVO IT-supplier reply (caps-lock + keyboard-layout safeguards, full Greek UI, NHRN visibility, HMVS verify / decommission / reactivate endpoints, dispense-only scoping, audit trail, test-book delivery).

Companion to `docs/redesign-tickets.md` — both tracks run in parallel. This doc spells out **where they collide**, **how to sequence around it**, and gives each ticket a paste-and-go Claude Code prompt.

## TL;DR

- **16 tickets**, total effort ~**5–6 engineer-weeks**.
- Mostly independent of the redesign, **with 4 explicit coordination points** (see Conflict Matrix below).
- The **i18n foundation (HMV-6a) MUST land in FR-0** — if FR-0 ships without it, every redesign component bakes English strings in and we have to retrofit later.
- **HMV-11 (Dispense wizard HMVS step)** layers on top of FR-3 — FR-3 should ship a non-HMVS dispense flow first; HMV-11 wires HMVS on top once endpoints exist.
- HMVO's test book hasn't arrived yet — HMV-15 is sized as a placeholder; rescope when received.

## Conflict matrix with the redesign

| HMVO ticket | Redesign ticket(s) it touches | Resolution |
|---|---|---|
| **HMV-1** Credential storage admin UI | **FR-5c** Settings | Coordinate: HMV-1's admin UI form lives inside the Settings screen FR-5c builds. Eng A owns both. |
| **HMV-5** NHRN/EOF display | **FR-2** Review + **FR-3** Dispense | Cross-cutting: NHRN must be present in the prescription detail card (FR-2) and the dispense wizard's drug summary (FR-3). Added as an explicit acceptance criterion in both. |
| **HMV-6a** i18n foundation | **FR-0** Foundation | Must merge: add `react-i18next` + the i18n setup to FR-0's design-system foundation. Cheap to do upfront, expensive to retrofit. |
| **HMV-11** Dispense wizard HMVS step | **FR-3** Dispense wizard | Layer: FR-3 ships a mock/non-HMVS dispense flow first; HMV-11 layers the HMVS verify / decommission step on top once HMV-7 / HMV-8 / HMV-10 exist. |

The remaining 12 tickets touch backend services or pure-utility frontend components that don't collide with redesign file ownership.

## Engineering allocation

Adding HMVO to the two-engineer redesign team means **carrying it on Eng A** (who owns FR-3 Dispense and FR-5c Settings — the two redesign tickets where HMVO work naturally lives). Eng B stays on the parallel redesign track (FR-2 / FR-4 / FR-5a-b). This adds ~3–4 weeks to Eng A's load on top of the redesign work — so total Eng A timeline goes from ~5d (redesign-only) to ~5d + ~3w (HMVO). Plan accordingly, or add a third engineer.

## Sequencing across both tracks

```
Week 1: [FR-0+HMV-6a] (i18n in foundation)  →  unblocks everyone
        [HMV-1, HMV-2] backend infra (parallel)
        [HMV-3, HMV-4] compliance hooks (parallel)

Week 2: [FR-0.5, FR-1, FR-2, FR-4]  ←  redesign work proceeds
        [HMV-7, HMV-8, HMV-9] HMVS endpoints
        [HMV-13] sandbox env

Week 3: [FR-3]  ←  base dispense wizard (non-HMVS)
        [HMV-10] data matrix scanner
        [HMV-5] NHRN audit pass

Week 4: [HMV-11] HMVS step layered on FR-3
        [HMV-12] HMVS audit log
        [FR-5a, FR-5b, FR-5c+HMV-1 admin]

Week 5: [HMV-14] screen recording
        [HMV-6b] Greek translation pass
        [FR-6] polish

Week 6: [HMV-15] test book completion (depends on HMVO sending it)
```

---

# Tickets

## Layer 1 — Backend infrastructure

### HMV-1 — HMVS credential storage

**Owner:** Eng A
**Branch:** `feat/hmv-1-credential-storage`
**Depends on:** —
**Coordinates with:** FR-5c Settings (admin UI lives there)
**Effort:** 3 days

#### Scope
HMVS requires per-pharmacy credentials (HMVS portal username + password, possibly client cert). Store encrypted at rest using the existing AES-256-GCM pattern (`app/crypto.py`), mirror how Pharmapi credentials are handled today.

#### Acceptance criteria
- New columns on `pharmacist_pharmacies`: `hmvs_username TEXT`, `hmvs_password TEXT` (both nullable, both encrypted)
- Alembic migration added; runs cleanly forward + backward
- `app/services/hmvs_credentials.py` with `get_hmvs_credentials(session, pharmacy_id)` returning decrypted creds (or None)
- The credential decryption only happens in-memory at the moment of use — never logged, never persisted plaintext
- The admin UI form (lives in FR-5c Settings) takes username + password, validates non-empty, encrypts before persist
- Unit test for the encrypt-then-decrypt round-trip

#### Claude Code prompt
```
You are adding HMVS credential storage to PharmAssist. HMVS = the Hellenic
Medicines Verification System (Greek FMD). Credentials are per-pharmacy and
must be encrypted at rest using the same pattern as Pharmapi credentials.

INPUTS
- Read backend/app/db/models/pharmacist_pharmacy.py — see how
  pharmapi_username and pharmapi_password are modelled (Text, nullable,
  encrypted at the application layer).
- Read backend/app/crypto.py — encrypt_credential / decrypt_credential
  are AES-256-GCM with a 12-byte nonce, base64-encoded. CREDENTIAL_ENCRYPTION_KEY
  is loaded lazily.
- Read backend/alembic/versions/ for migration style (naming convention,
  upgrade/downgrade pattern). Add new models to alembic/env.py if you
  create a new table (you should not — extend pharmacist_pharmacies).
- Read backend/app/services/pharmacy.py + how login() reads pharmapi
  credentials in app/routers/auth.py — mirror that exact pattern.

STUB CONTRACT (write this)
# backend/app/services/hmvs_credentials.py
async def get_hmvs_credentials(
    session: AsyncSession,
    pharmacy_id: uuid.UUID,
) -> tuple[str, str] | None:
    """Return (username, password) decrypted in memory, or None if not set
    on the default pharmacist_pharmacy link for this pharmacy."""

async def set_hmvs_credentials(
    session: AsyncSession,
    pharmacist_id: uuid.UUID,
    pharmacy_id: uuid.UUID,
    username: str,
    password: str,
) -> None:
    """Encrypt and persist HMVS credentials on the pharmacist_pharmacies
    link row. Caller is responsible for verifying ownership before calling."""

ACCEPTANCE CRITERIA
- Alembic migration adds hmvs_username + hmvs_password as Text NULL columns
  on pharmacist_pharmacies. Naming convention matches existing pharmapi_* cols.
- Migration runs alembic upgrade head and alembic downgrade -1 cleanly.
- alembic/env.py changes only if you added a new model (you should not).
- backend/app/services/hmvs_credentials.py implements both functions above.
- A unit test in backend/tests/test_hmvs_credentials.py round-trips a
  credential through encrypt + persist + fetch + decrypt and asserts equality.
- Ruff + ruff format clean (line length 100). Run: cd backend && ruff check .
  && ruff format .

DO NOT
- Do not log credentials anywhere — not even at DEBUG.
- Do not add an admin UI endpoint in this ticket — that lands as part of FR-5c.
- Do not change how Pharmapi credentials work — pattern is the reference,
  don't refactor.

FINALIZE
- Run: cd backend && pytest tests/test_hmvs_credentials.py -v
- Run: cd backend && alembic upgrade head && alembic downgrade -1 && alembic upgrade head
- Commit with message: "feat(hmv-1): HMVS credential storage on
  pharmacist_pharmacies"
- Open PR titled: "HMV-1: HMVS credential storage (encrypted at rest)"
```

---

### HMV-2 — HMVS HTTP client + session management

**Owner:** Eng A
**Branch:** `feat/hmv-2-hmvs-client`
**Depends on:** HMV-1
**Effort:** 2 days

#### Scope
The HMVS HTTP client that all the verify/decommission/reactivate endpoints (HMV-7/8/9) call through. Mirrors `app/services/pharmapi.py` in structure: auth, session, retry, error mapping. HMVS uses Basic Auth + (likely) an API key + (likely) mTLS — confirm exact auth shape with HMVO test docs when sandbox access lands.

#### Acceptance criteria
- `app/services/hmvs.py` with `hmvs_get` / `hmvs_post` analogous to `pharmapi_get` / `pharmapi_post`
- Credentials loaded lazily via `get_hmvs_credentials(session, pharmacy_id)`
- Errors from HMVS mapped to `HTTPException(502, "HMVS: <code> — <message>")` consistently
- A `HMVS_BASE_URL` setting in `app/config.py` (defaults to HMVO sandbox URL — env-overridable)
- A `HMVS_MOCK=true` env toggle that short-circuits to a deterministic mock response (mirrors `is_mock_pharmapi()`)
- Unit test covers: successful response parsing, error response mapping, mock-mode short-circuit

#### Claude Code prompt
```
You are building the HMVS HTTP client — the single point of contact between
PharmAssist backend and the Hellenic Medicines Verification System. All HMVS
verify/decommission/reactivate endpoints will go through this.

INPUTS
- Read backend/app/services/pharmapi.py end-to-end. The shape you are
  building is analogous: base URL + auth headers + httpx async client +
  error mapping + mock-mode toggle.
- Read backend/app/services/hmvs_credentials.py (HMV-1) — the credential
  loader is your auth source.
- Read backend/app/config.py — add HMVS_BASE_URL there. Default to the
  HMVO sandbox URL ("https://hmvo-sandbox.example.gr" — placeholder until
  real URL arrives; document in a comment).
- Read backend/app/utils/environment.py — is_mock_pharmapi() is the
  pattern. Add is_mock_hmvs() the same way (reading HMVS_MOCK env var).

STUB CONTRACT
# backend/app/services/hmvs.py
async def hmvs_get(
    session: AsyncSession,
    pharmacy_id: uuid.UUID,
    path: str,
    *,
    params: dict | None = None,
) -> dict:
    """GET with HMVS Basic Auth. Maps non-2xx to HTTPException(502, ...).
    Returns parsed JSON dict."""

async def hmvs_post(
    session: AsyncSession,
    pharmacy_id: uuid.UUID,
    path: str,
    *,
    json: dict,
) -> dict:
    """POST with HMVS Basic Auth. Same error mapping. Returns parsed JSON."""

# backend/app/utils/environment.py — add:
def is_mock_hmvs() -> bool: ...

ACCEPTANCE CRITERIA
- hmvs.py uses httpx.AsyncClient with a 10s timeout. Re-use the client per
  process (module-level singleton) — same pattern as pharmapi.py.
- When is_mock_hmvs() is True, every call short-circuits to a stub response
  (return {"status": "OK", "mock": True}) without touching the network.
- 4xx responses raise HTTPException(502, "HMVS: <upstream_status> — <body[:200]>").
- 5xx responses raise HTTPException(502, "HMVS: upstream error <status>").
- Network errors (httpx.RequestError) raise HTTPException(502, "HMVS:
  network error — <repr>").
- backend/tests/test_hmvs_client.py covers: (a) mock-mode returns the stub,
  (b) 200 OK returns parsed JSON, (c) 400 maps to 502 with the upstream
  body in the detail, (d) RequestError maps to 502.
- Use respx or httpx.MockTransport to stub the upstream — no real network
  in tests.
- Ruff + ruff format clean.

DO NOT
- Do not retry automatically — HMVS calls are state-changing (decommission
  is non-idempotent). Caller decides if retry is safe.
- Do not log request bodies — they will contain pack serial numbers (sensitive).
- Do not store the http client in a global variable that crosses test runs.

FINALIZE
- Run: cd backend && pytest tests/test_hmvs_client.py -v
- Run: cd backend && ruff check . && ruff format .
- Commit: "feat(hmv-2): HMVS HTTP client with mock toggle and error mapping"
- Open PR: "HMV-2: HMVS client (depends on HMV-1)"
```

---

## Layer 2 — Compliance safeguards (HMVO requirements)

### HMV-3 — Caps Lock blocker hook + input component

**Owner:** Eng A (or Eng B — pure frontend utility)
**Branch:** `feat/hmv-3-caps-lock-blocker`
**Depends on:** —
**Effort:** 1 day

#### Scope
HMVO requires that any input field that will feed an HMVS submission must block the submission while Caps Lock is on, and show a Greek warning. We build this as a reusable hook + an `<HmvsSecureInput>` component so every place we accept a pack serial number gets the same protection.

#### Acceptance criteria
- `frontend/src/hooks/useCapsLockState.ts` returns the current Caps Lock state (boolean), updates on keyboard events while the bound input is focused
- `frontend/src/components/HmvsSecureInput.tsx` is the input component to use for HMVS serial / GTIN fields:
  - Renders an `<input>` with the i18n string for the field label
  - When Caps Lock is on, sets `aria-invalid`, disables the submit button via context, shows a Greek warning ("Απενεργοποιήστε το Caps Lock πριν συνεχίσετε")
  - Emits an `onBlock(reason)` callback so the parent form's submit handler can react
- Unit test (Vitest) covers: Caps Lock off → no block, Caps Lock on → block + warning, Caps Lock toggled off → block clears

#### Claude Code prompt
```
You are building a reusable input component for HMVS data entry that blocks
submission while Caps Lock is active. HMVO requires this because case-sensitive
HMVS serial numbers typed with Caps Lock generate false counterfeit alerts.

INPUTS
- Read frontend/src/components for the existing component style (Tailwind,
  no styled-components, no CSS modules). Use the patterns you find.
- Read frontend/src/lib/i18n.ts (or wherever HMV-6a placed the i18n setup —
  if it's not there yet, this ticket is blocked. Stop and tell the user.)
- Web platform reference: KeyboardEvent.getModifierState('CapsLock') is the
  detection method. Bind to keydown and keyup on the input.

STUB CONTRACT
// frontend/src/hooks/useCapsLockState.ts
export function useCapsLockState(ref: RefObject<HTMLInputElement>): boolean;

// frontend/src/components/HmvsSecureInput.tsx
interface HmvsSecureInputProps {
  value: string;
  onChange: (v: string) => void;
  onBlock?: (reason: 'caps-lock' | null) => void;
  label: string;            // already-translated string
  warningText?: string;     // defaults to i18n('hmvs.capsLockWarning')
  placeholder?: string;
}
export function HmvsSecureInput(props: HmvsSecureInputProps): JSX.Element;

ACCEPTANCE CRITERIA
- useCapsLockState returns true the moment Caps Lock is detected as active
  on any key event from the bound input; returns false otherwise.
- HmvsSecureInput renders:
  - The input itself with the given value/onChange
  - When Caps Lock active: aria-invalid="true", a warning element with
    role="alert" containing the Greek warning string, a red border via
    Tailwind (border-red-500), and onBlock('caps-lock') is called.
  - When Caps Lock not active: warning hidden, onBlock(null) called once
    on transition.
- Greek string: "Απενεργοποιήστε το Caps Lock πριν συνεχίσετε" — pulled
  from i18n if HMV-6a is in place; hardcoded as fallback with a TODO if not.
- Vitest test in HmvsSecureInput.test.tsx asserts:
  - Initial render: no warning, onBlock not called with caps-lock
  - Fire keydown with getModifierState mocked to return true for CapsLock:
    warning appears, onBlock('caps-lock') called
  - Fire keydown with caps lock false: warning disappears, onBlock(null) called

DO NOT
- Do not poll for Caps Lock state — only react to keyboard events on the
  bound input. Polling battery-drains and triggers false positives.
- Do not block the input from receiving characters — only block the
  submission. The user might be typing to investigate before submitting.

FINALIZE
- Run: cd frontend && npm run typecheck && npm run lint && npm test
- Commit: "feat(hmv-3): Caps Lock blocker hook and HmvsSecureInput component"
- Open PR: "HMV-3: Caps Lock submission blocker (HMVO compliance)"
```

---

### HMV-4 — Keyboard layout blocker hook + input augmentation

**Owner:** Eng A
**Branch:** `feat/hmv-4-keyboard-layout-blocker`
**Depends on:** HMV-3 (extends the same `HmvsSecureInput`)
**Effort:** 3–4 days

#### Scope
HMVO requires blocking HMVS submissions while the OS keyboard layout is not English. Browsers don't expose the OS keyboard layout directly; the workaround is to analyse typed input — if a Greek (or other non-Latin) character lands in the HMVS field, the layout is wrong, block and warn.

#### Acceptance criteria
- `frontend/src/hooks/useNonLatinInputDetector.ts` watches input value, detects presence of non-Latin characters using a regex (`/[^\x00-\x7F]/`)
- `<HmvsSecureInput>` extended to also block on non-Latin input: warning text in Greek ("Αλλάξτε τη γλώσσα πληκτρολογίου σε αγγλικά πριν συνεχίσετε"), `onBlock('keyboard-layout')` callback
- Both block conditions can be active simultaneously — both warnings shown, submission blocked until both cleared
- The screen-recording deliverable (HMV-14) will exercise this exact component

#### Claude Code prompt
```
You are extending HmvsSecureInput from HMV-3 to also block HMVS submissions
when a non-Latin keyboard layout is detected. Browsers can't read the OS
layout directly — we detect by analysing characters typed into the input.

INPUTS
- Read the HmvsSecureInput component built in HMV-3 (frontend/src/components/
  HmvsSecureInput.tsx). Extend it; do not create a new component.
- Read the i18n setup (assume HMV-6a has landed — if not, stop and tell the
  user this ticket is blocked).
- The detection regex /[^\x00-\x7F]/ matches any non-ASCII character. This
  is the cleanest signal that the user has typed a Greek (or otherwise
  non-Latin) character. Latin extended characters (ñ, é) would also flag —
  acceptable false positive for our domain (HMVS serial numbers are ASCII).

STUB CONTRACT
// frontend/src/hooks/useNonLatinInputDetector.ts
export function useNonLatinInputDetector(value: string): boolean;

// HmvsSecureInput onBlock callback now emits a union:
type BlockReason = 'caps-lock' | 'keyboard-layout' | 'both' | null;

ACCEPTANCE CRITERIA
- useNonLatinInputDetector(value) returns true if value contains any
  non-ASCII character, false otherwise. Memoised on value.
- HmvsSecureInput now blocks on EITHER caps-lock OR non-Latin input:
  - Both blockers show their respective warning, stacked
  - onBlock receives 'caps-lock', 'keyboard-layout', 'both', or null
  - Submission disabled when any blocker active
- Greek warning string: "Αλλάξτε τη γλώσσα πληκτρολογίου σε αγγλικά πριν
  συνεχίσετε" — pulled from i18n.
- Extended Vitest tests:
  - Input "ABC" (Latin): no keyboard-layout block
  - Input "ΑΒΓ" (Greek): keyboard-layout block fires, warning shown
  - Caps Lock + Greek input: both warnings shown, onBlock('both')
  - Clear the Greek chars: keyboard-layout block clears

DO NOT
- Do not try to detect via navigator.keyboard.getLayoutMap() — browser
  support is poor and HMVO's standard is OS-level. Document in a code
  comment that browser-native detection is unavailable.
- Do not block ALL inputs from receiving non-Latin chars — only HMVS
  submission. The patient name field, for example, must accept Greek.

FINALIZE
- Run: cd frontend && npm run typecheck && npm run lint && npm test
- Commit: "feat(hmv-4): non-Latin keyboard layout blocker on HmvsSecureInput"
- Open PR: "HMV-4: Keyboard layout submission blocker (HMVO compliance)"
```

---

### HMV-5 — NHRN/EOF code visibility audit (cross-cutting)

**Owner:** Eng B (works on FR-2 / FR-4 — natural overlap)
**Branch:** Folded into FR-2 + FR-3 PRs as acceptance criteria
**Depends on:** —
**Effort:** 1–2 days

#### Scope
HMVO requires that the NHRN (κωδικός ΕΟΦ — the Greek drug ID) is visible to the end user wherever a medicine is shown in a verification or dispense flow. This isn't a standalone PR; it's an acceptance criterion that gets added to FR-2 (Review screen) and FR-3 (Dispense wizard) and verified before each merges.

#### Acceptance criteria for FR-2 / FR-3 reviews to apply
- The prescription detail view (FR-2) displays the NHRN/EOF code alongside the drug name
- The dispense wizard's drug summary step (FR-3) displays the NHRN/EOF code
- The code is labelled `Κωδικός ΕΟΦ` (Greek) in the production UI
- The data source: `medicineBarcode` from the v2 search result IS the NHRN — no new endpoint needed
- Visible at glance without hover/expand

#### Claude Code prompt
```
This is a coordination item, not a standalone implementation. The NHRN
(κωδικός ΕΟΦ — Greek drug ID) must be visible to the pharmacist in the
prescription review screen (FR-2) and the dispense wizard's drug summary
step (FR-3). HMVO requires this for compliance.

INPUTS
- The NHRN value is already available in our v2 search response as
  `medicineBarcode`. Read backend/app/services/pharmapi.py
  _parse_prescription_search_json to confirm.
- The label "Κωδικός ΕΟΦ" should come from i18n (HMV-6a).

ACCEPTANCE CRITERIA
- In the FR-2 PR review, verify:
  - The prescription detail card shows the NHRN labelled "Κωδικός ΕΟΦ"
  - Visible at glance, not behind hover or expand
- In the FR-3 PR review, verify the same for the drug summary step of the
  dispense wizard
- If either FR-2 or FR-3 ships without this, block the merge and request
  the addition. This is an HMVO compliance item, not a nice-to-have.

DO NOT
- Do not open a separate PR for this. The work is two CSS / JSX additions
  inside FR-2 and FR-3.

FINALIZE
- After FR-2 and FR-3 both merge with NHRN visible, mark HMV-5 done.
- No standalone commit needed.
```

---

### HMV-6a — i18n foundation (must land in FR-0)

**Owner:** Eng A (owns FR-0)
**Branch:** Part of FR-0 — `feat/fr-0-foundation`
**Depends on:** —
**Effort:** 1 day (added to FR-0's scope)
**Critical:** This MUST land with FR-0. Retrofitting i18n after all the redesign components ship is significantly more expensive.

#### Scope
Set up `react-i18next`, an `en` and `el` namespace, the `t()` hook usage pattern, and one example translated component. Every component built in FR-1 through FR-6 then uses `t('...')` rather than hardcoded strings. The full Greek translation pass happens in HMV-6b.

#### Acceptance criteria
- `react-i18next` + `i18next` installed
- `frontend/src/lib/i18n.ts` initialises i18next with `en` (default) + `el` (Greek) namespaces
- Locale chosen via: URL query param `?lang=el` → localStorage → browser default → `el` fallback (HMVO commitment is Greek-first)
- `frontend/src/locales/en.json` + `frontend/src/locales/el.json` exist with at least one example key (`common.appName: "PharmAssist"`)
- One FR-0 foundation component (e.g. the AppShell header) uses `t('common.appName')` to demonstrate the pattern
- The redesign-tickets doc is updated to note that every subsequent FR-N ticket must use `t()` for any new string

#### Claude Code prompt
```
You are adding the i18n foundation to the FR-0 frontend foundation work.
HMVO requires the entire UI in Greek; the cheapest path is to install i18n
NOW so every redesign component uses t() from day one. Retrofitting later
is ~10x the work.

INPUTS
- Read frontend/package.json — react-i18next is not yet installed.
- Read docs/redesign-tickets.md FR-0 scope. You are extending FR-0, not
  opening a separate PR.
- Read frontend/src/main.tsx and frontend/src/App.tsx — i18n is initialised
  at app bootstrap.

INSTALL
cd frontend && npm install react-i18next i18next i18next-browser-languagedetector

STUB CONTRACT
// frontend/src/lib/i18n.ts
import i18n from 'i18next';
import LanguageDetector from 'i18next-browser-languagedetector';
import { initReactI18next } from 'react-i18next';
import en from '../locales/en.json';
import el from '../locales/el.json';

i18n.use(LanguageDetector).use(initReactI18next).init({
  resources: { en: { translation: en }, el: { translation: el } },
  fallbackLng: 'el',
  detection: {
    order: ['querystring', 'localStorage', 'navigator'],
    lookupQuerystring: 'lang',
    lookupLocalStorage: 'pharmassist_lang',
  },
  interpolation: { escapeValue: false },
});
export default i18n;

// frontend/src/locales/en.json + el.json
{
  "common": {
    "appName": "PharmAssist"
  }
}

ACCEPTANCE CRITERIA
- frontend/src/main.tsx imports './lib/i18n' before <App /> mounts.
- One existing component (suggest the AppShell header) uses
  const { t } = useTranslation(); t('common.appName').
- ?lang=el in the URL forces Greek; ?lang=en forces English. Choice
  persists in localStorage as 'pharmassist_lang'.
- npm run typecheck + npm run lint + npm run build all pass.
- Coordinate with redesign-tickets.md author to add a top-of-doc note:
  "All FR-N components must use t('...') for visible strings; never
  hardcode English."

DO NOT
- Do not translate the full UI in this ticket — that's HMV-6b. Goal here
  is plumbing + one example.
- Do not pick a fancier library (formatjs, react-intl) — react-i18next
  is the mature Greek-pharmacy-software default and keeps the bundle small.

FINALIZE
- Run: cd frontend && npm run typecheck && npm run lint && npm run build
- Commit (as part of FR-0): "feat(fr-0/hmv-6a): i18n foundation with en+el
  namespaces"
- Verify in browser: load with ?lang=el, see Greek appName; load with
  ?lang=en, see English appName.
```

---

### HMV-6b — Full Greek translation pass

**Owner:** Eng A (during FR-6 polish)
**Branch:** `feat/hmv-6b-greek-translation`
**Depends on:** HMV-6a, all FR-N tickets landed
**Effort:** 1.5–2 weeks

#### Scope
Sweep every component in the redesign, find all visible strings, externalise into `t('...')` calls if not already, and provide Greek translations in `el.json`. Includes form labels, button text, error messages, modal copy, table headers, empty states, validation messages, dates/numbers (use Intl APIs).

#### Acceptance criteria
- 100% of visible strings in the redesigned UI use `t('...')` — verified by a script that greps for hardcoded English (heuristic: any string in JSX containing 3+ ASCII alpha chars not wrapped in `t()`)
- `el.json` has Greek translations for every key
- `en.json` retained as the source-of-truth for the key inventory
- A native Greek speaker (the user, or a contractor) reviews and signs off on the translation quality before merge — clinical terminology is sensitive
- Pre-built terminology mapping in the PR description (Serial Number → Σειριακός Αριθμός, Batch → Παρτίδα, Pack → Συσκευασία, NHRN → Κωδικός ΕΟΦ, etc.)

#### Claude Code prompt
```
You are doing the full Greek translation pass for the PharmAssist frontend.
HMVO requires that the entire UI is in Greek — every visible string,
including button labels, validation errors, table headers, empty states,
and modal copy. The i18n plumbing is already in place from HMV-6a.

INPUTS
- Read frontend/src/lib/i18n.ts and frontend/src/locales/{en,el}.json —
  these exist and have an example key.
- Read every component under frontend/src/components/ and
  frontend/src/pages/ — these all need string externalisation.
- Reference glossary (use these consistently across the translation):
  Serial Number → Σειριακός Αριθμός
  Batch → Παρτίδα
  Pack → Συσκευασία
  NHRN / EOF code → Κωδικός ΕΟΦ
  Prescription → Συνταγή
  Patient → Ασθενής
  Medicine / Drug → Φάρμακο
  Pharmacist → Φαρμακοποιός
  Dispense → Διάθεση / Δοσοληψία (context-dependent — see below)
  Verify → Επαλήθευση
  Decommission → Απενεργοποίηση
  Reactivate → Επανενεργοποίηση
  Safety check → Έλεγχος ασφάλειας
  Side effect / ADR → Παρενέργεια / Ανεπιθύμητη Ενέργεια
  AMKA → ΑΜΚΑ (no translation, just transliteration)
  ΗΔΥΚΑ → ΗΔΥΚΑ (no change)
  Dosage → Δοσολογία
  Quantity → Ποσότητα
- "Dispense" is the dispense ACTION when used as a verb; "διάθεση"
  is the noun for the result. Read context, pick the right one.

WORK PLAN
1. Sweep every .tsx file under frontend/src/. For every visible string
   (any string rendered in JSX), externalise to t('key').
2. Use hierarchical keys: components.SafetyAlertsPanel.title,
   pages.Counter.scanCta, common.cancel, errors.networkFailure, etc.
3. Add the English original to en.json and the Greek translation to el.json.
4. For pluralisation, use react-i18next's count interpolation:
   t('items.count', { count: items.length })
5. For dates, use Intl.DateTimeFormat with locale 'el-GR' when current
   language is 'el'.

ACCEPTANCE CRITERIA
- A grep heuristic (provide a script in tools/check-i18n.sh) returns zero
  hardcoded English strings in JSX. The heuristic looks for: JSX text
  content matching /[A-Z][a-z]{3,}/ that isn't inside a t() call.
- el.json has 100% coverage of keys in en.json.
- The user (or a native Greek speaker they nominate) reviews and approves
  the translations before merge — flag this in the PR description as a
  required review.
- The app loads in Greek by default; ?lang=en still works.
- npm run typecheck, lint, build all pass.

DO NOT
- Do not auto-translate clinical terminology with Google Translate without
  human review. Pharmacy terms are sensitive — wrong word = wrong care.
- Do not invent Greek translations for HMVS or ΗΔΥΚΑ terms — they are used
  as-is in Greek pharmacy software.
- Do not change the i18n setup itself — extend the locale files only.

FINALIZE
- Run: cd frontend && bash tools/check-i18n.sh && npm run typecheck &&
  npm run lint && npm run build
- Commit: "feat(hmv-6b): full Greek translation pass for redesigned UI"
- PR description: include the terminology glossary used, and request
  native-speaker review explicitly.
```

---

## Layer 3 — HMVS endpoint integration

### HMV-7 — Verify endpoint (single-pack verification)

**Owner:** Eng A
**Branch:** `feat/hmv-7-verify-endpoint`
**Depends on:** HMV-2
**Effort:** 2 days

#### Scope
The `POST /pharmapi/hmvs/verify` proxy that calls HMVS `/api/medicines/lot/qr` (SINGLE VERIFY) to check whether a pack QR code is genuine, in date, not already dispensed. Returns the verification status + decoded pack details (GTIN, serial, batch, expiry).

#### Acceptance criteria
- `POST /pharmapi/hmvs/verify` accepts `{qr_code: str}` body
- Calls `hmvs_post` (HMV-2) to forward to HMVS `/api/medicines/lot/qr`
- Returns: `{status: "VERIFIED" | "DECOMMISSIONED" | "EXPIRED" | "RECALLED" | "UNKNOWN", gtin, serial, batch, expiry_date, raw_response}`
- HMVS error responses (e.g., F-code "FNS-NHRN-LOT-99" type strings) mapped to clear status
- Audit log entry written for every verify call (HMV-12 ticket — for now, leave a TODO comment if HMV-12 hasn't shipped)
- Unit test covers: VERIFIED happy path, DECOMMISSIONED rejection, EXPIRED rejection, network error

#### Claude Code prompt
```
You are building the verify endpoint — the proxy that calls HMVS single-pack
verification when a pharmacist scans a pack's 2D Data Matrix.

INPUTS
- Read backend/app/services/hmvs.py (HMV-2) — hmvs_post is your transport.
- Read backend/app/routers/pharmapi.py — the proxy router pattern. Mirror it.
- HMVS single-verify endpoint contract (from HMVO docs; if exact spec
  isn't available, document assumptions and adjust when sandbox access
  arrives):
  POST /api/medicines/lot/qr
  Body: {"qr": "<raw qr string from data matrix scanner>"}
  Response: status code per pack state. Map upstream codes to our enum.

STUB CONTRACT
# backend/app/routers/hmvs.py (new file)
router = APIRouter(prefix="/pharmapi/hmvs", tags=["hmvs"])

class VerifyRequest(BaseModel):
    qr_code: str  # raw 2D Data Matrix payload

class VerifyResponse(BaseModel):
    status: Literal["VERIFIED", "DECOMMISSIONED", "EXPIRED", "RECALLED", "UNKNOWN"]
    gtin: str | None
    serial: str | None
    batch: str | None
    expiry_date: str | None  # YYYY-MM-DD
    upstream_message: str | None

@router.post("/verify", response_model=VerifyResponse)
async def hmvs_verify(
    body: VerifyRequest,
    current: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> VerifyResponse:
    ...

ACCEPTANCE CRITERIA
- Router added to main.py app.include_router list.
- Endpoint accepts the QR string, calls hmvs_post(session, pharmacy_id,
  "/api/medicines/lot/qr", json={"qr": body.qr_code}).
- Response parsed into the VerifyResponse shape. The status mapping table:
  upstream "ACTIVE" → "VERIFIED"
  upstream "DECOMMISSIONED" → "DECOMMISSIONED"
  upstream "EXPIRED" → "EXPIRED"
  upstream "RECALLED" → "RECALLED"
  anything else → "UNKNOWN" (with upstream_message populated for debugging)
- 2D Data Matrix QR encodes: GTIN (14 digits), Serial (up to 20 alphanumeric),
  Batch (up to 20), Expiry (YYMMDD). Document the parsing in a helper.
- Audit log: write a TODO comment for now — "HMV-12 will write the audit
  row here once that ticket ships". Do not block on it.
- Test in backend/tests/test_hmvs_verify.py:
  - VERIFIED upstream → status "VERIFIED" with decoded fields
  - DECOMMISSIONED upstream → status "DECOMMISSIONED"
  - Upstream 502 → endpoint raises 502 with HMVS prefix in detail
  - HMVS_MOCK=true → returns deterministic VERIFIED stub

DO NOT
- Do not retry on failure — HMVS verify is read-only but the pharmacist
  needs to see real failures immediately.
- Do not log the full QR code (contains serial number — privacy/regulatory
  sensitive).

FINALIZE
- Run: cd backend && pytest tests/test_hmvs_verify.py -v
- Run: cd backend && ruff check . && ruff format .
- Commit: "feat(hmv-7): POST /pharmapi/hmvs/verify endpoint"
- PR: "HMV-7: HMVS single-pack verify (depends on HMV-2)"
```

---

### HMV-8 — Decommission endpoint

**Owner:** Eng A
**Branch:** `feat/hmv-8-decommission-endpoint`
**Depends on:** HMV-2, HMV-7 (same router file)
**Effort:** 2 days

#### Scope
`POST /pharmapi/hmvs/decommission` — called the moment a pack is dispensed to a patient. Removes the pack's serial number from the live HMVS registry. State-changing and non-idempotent — must NOT be called twice for the same pack.

#### Acceptance criteria
- `POST /pharmapi/hmvs/decommission` accepts `{qr_code, reason}` body where reason ∈ `DISPENSED | DESTROYED | SAMPLE | STOLEN`
- Calls `hmvs_post` to `/api/medicines/decommission`
- Returns: `{success: bool, upstream_message, decommissioned_at}`
- **Idempotency guard**: track recent decommissions in a local table (`hmvs_decommission_log`) with `(pharmacy_id, serial)` as a unique key; if the pack was decommissioned by us in the last 5 minutes, return the cached response instead of re-calling
- Audit log entry (TODO until HMV-12)

#### Claude Code prompt
```
You are building the decommission endpoint — called when a pack is dispensed
to a patient. This is a STATE-CHANGING call to HMVS that must not be made
twice for the same pack.

INPUTS
- Read backend/app/routers/hmvs.py (created in HMV-7). Extend it; do not
  create a new router file.
- Read backend/app/services/hmvs.py (HMV-2) — hmvs_post is your transport.
- HMVS decommission contract (assumed, validate when sandbox lands):
  POST /api/medicines/decommission
  Body: {"qr": "<raw>", "reason": "DISPENSED"}
  Response: {"success": true} or {"success": false, "code": "...", "message": "..."}

STUB CONTRACT
class DecommissionRequest(BaseModel):
    qr_code: str
    reason: Literal["DISPENSED", "DESTROYED", "SAMPLE", "STOLEN"] = "DISPENSED"

class DecommissionResponse(BaseModel):
    success: bool
    upstream_message: str | None
    decommissioned_at: datetime | None
    idempotent_cached: bool = False  # True if we returned a cached response

@router.post("/decommission", response_model=DecommissionResponse)
async def hmvs_decommission(
    body: DecommissionRequest,
    current: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> DecommissionResponse:
    ...

ACCEPTANCE CRITERIA
- New table hmvs_decommission_log with columns: id (PK), pharmacy_id (FK),
  serial (string, indexed), gtin (string), reason (string), upstream_response
  (JSONB), decommissioned_at (timestamptz default now()).
- Unique constraint on (pharmacy_id, serial) to prevent double-write.
- Alembic migration added.
- Endpoint logic:
  1. Parse QR to extract serial.
  2. Check hmvs_decommission_log for (pharmacy_id, serial). If found AND
     decommissioned_at is within last 5 minutes, return cached response with
     idempotent_cached=true. (Prevents accidental double-dispense from a
     pharmacist clicking twice.)
  3. Otherwise, call hmvs_post(session, pharmacy_id, "/api/medicines/decommission",
     json={"qr": body.qr_code, "reason": body.reason}).
  4. On success: insert into hmvs_decommission_log, return DecommissionResponse(
     success=True, upstream_message=..., decommissioned_at=...).
  5. On failure: return DecommissionResponse(success=False, upstream_message=...).
     DO NOT insert into the log on failure — let the pharmacist retry.
- Test in backend/tests/test_hmvs_decommission.py:
  - Happy path: success=True, log row created
  - Same pack within 5 min: returns idempotent_cached=true, upstream not called
  - Upstream failure: success=false, no log row
  - HMVS_MOCK=true returns success stub

DO NOT
- Do not retry on failure — let the pharmacist trigger retry explicitly.
  Auto-retry could double-dispense if the first call actually succeeded
  but the response was lost.
- Do not allow a hard delete from hmvs_decommission_log — append-only.
- Do not log the QR code.

FINALIZE
- Run: cd backend && alembic upgrade head && pytest tests/test_hmvs_decommission.py -v
- Run: cd backend && ruff check . && ruff format .
- Commit: "feat(hmv-8): POST /pharmapi/hmvs/decommission with idempotency guard"
- PR: "HMV-8: HMVS decommission endpoint (depends on HMV-7)"
```

---

### HMV-9 — Reactivate endpoint

**Owner:** Eng A
**Branch:** `feat/hmv-9-reactivate-endpoint`
**Depends on:** HMV-2, HMV-8 (extends same router)
**Effort:** 1 day

#### Scope
`POST /pharmapi/hmvs/reactivate` — undo a decommission. Used when a pharmacist accidentally decommissioned a pack (e.g. scanned the wrong one or the patient changed their mind before leaving). Strict time window: HMVS only allows reactivation within ~10 days of decommission.

#### Acceptance criteria
- `POST /pharmapi/hmvs/reactivate` accepts `{qr_code}` body
- Calls HMVS `/api/otcm/reactivate`
- Returns: `{success, upstream_message}`
- If reactivation succeeds, remove the row from `hmvs_decommission_log` (so the idempotency window doesn't block re-dispense to a different patient)
- Audit log entry (TODO until HMV-12)

#### Claude Code prompt
```
You are building the reactivate endpoint — the "undo" for HMV-8 decommission.
HMVS allows reactivation within a strict ~10-day window after decommission.
After that, packs are permanently retired.

INPUTS
- Read backend/app/routers/hmvs.py (HMV-7 + HMV-8). Extend; do not create
  a new file.
- HMVS reactivate contract (assumed):
  POST /api/otcm/reactivate
  Body: {"qr": "<raw>"}
  Response: {"success": true} or {"success": false, "code": "...", "message": "..."}
  Common failure: pack outside the reactivation window.

STUB CONTRACT
class ReactivateRequest(BaseModel):
    qr_code: str

class ReactivateResponse(BaseModel):
    success: bool
    upstream_message: str | None

@router.post("/reactivate", response_model=ReactivateResponse)
async def hmvs_reactivate(
    body: ReactivateRequest,
    current: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ReactivateResponse:
    ...

ACCEPTANCE CRITERIA
- Endpoint extracts serial from QR, calls hmvs_post(session, pharmacy_id,
  "/api/otcm/reactivate", json={"qr": body.qr_code}).
- On success: DELETE FROM hmvs_decommission_log WHERE pharmacy_id=... AND
  serial=...  (so the 5-minute idempotency cache doesn't block a fresh
  decommission to a different patient).
- On failure: log row stays, no DB mutation. Return upstream_message so the
  UI can show the pharmacist exactly why (most likely "outside reactivation
  window").
- Test in backend/tests/test_hmvs_reactivate.py:
  - Happy path: success=True, log row deleted
  - Upstream rejection (outside window): success=False, log row intact
  - HMVS_MOCK=true returns success stub

DO NOT
- Do not retry. Reactivation failures are usually permanent (out of window)
  and shouldn't be retried automatically.
- Do not allow reactivate without a prior decommission log row in mock
  mode — useful sanity check.

FINALIZE
- Run: cd backend && pytest tests/test_hmvs_reactivate.py -v
- Run: cd backend && ruff check . && ruff format .
- Commit: "feat(hmv-9): POST /pharmapi/hmvs/reactivate endpoint"
- PR: "HMV-9: HMVS reactivate endpoint (undo for HMV-8)"
```

---

### HMV-10 — 2D Data Matrix pack scanner component

**Owner:** Eng A or Eng B (pure frontend component)
**Branch:** `feat/hmv-10-data-matrix-scanner`
**Depends on:** —
**Effort:** 3–5 days

#### Scope
A reusable React component that uses the device camera to scan a 2D Data Matrix barcode (the format used on EU prescription drug packs under FMD). Decodes the GS1 payload to extract GTIN + serial + batch + expiry, displays a confirmation, emits `onScan(payload)`. Falls back to a manual entry field (with `HmvsSecureInput`) if camera unavailable.

#### Acceptance criteria
- `frontend/src/components/DataMatrixScanner.tsx` component
- Uses `@zxing/browser` or `quagga2` for scanning (validate library size, pick smallest viable)
- On successful scan: parse the GS1 payload (`(01)GTIN(21)serial(17)expiry(10)batch`), emit `onScan({gtin, serial, expiry, batch})`
- Camera permission UX: clear ask, fallback to manual entry if denied
- Manual entry mode uses `HmvsSecureInput` (HMV-3 + HMV-4) so Caps Lock + keyboard layout blockers still apply
- Mobile-responsive: works on tablet (iPad) — that's the likely deployment form-factor
- Vitest test for the GS1 parser

#### Claude Code prompt
```
You are building a 2D Data Matrix scanner component for EU FMD pharmacy packs.
This is what the pharmacist uses to verify a pack against HMVS before
dispensing. Format is GS1-encoded Data Matrix (DIFFERENT from the prescription
barcode — that one is 1D and 16 digits).

INPUTS
- Read frontend/src/components/HmvsSecureInput.tsx (HMV-3 + HMV-4) — the
  manual entry fallback uses this so Caps Lock + keyboard layout blockers
  apply.
- Library choice: @zxing/browser (~120kb gzipped, actively maintained,
  supports Data Matrix). Install:
  cd frontend && npm install @zxing/browser
- GS1 application identifiers in the payload:
  (01) GTIN — 14 digits
  (21) Serial — variable, ASCII
  (17) Expiry — YYMMDD (6 digits)
  (10) Batch — variable, ASCII
  GS1 uses ASCII 29 (FNC1, group separator) between variable-length fields.

STUB CONTRACT
// frontend/src/components/DataMatrixScanner.tsx
interface ScannedPack {
  gtin: string;
  serial: string;
  expiry: string;  // YYYY-MM-DD (converted from YYMMDD)
  batch: string;
  rawPayload: string;
}

interface DataMatrixScannerProps {
  onScan: (pack: ScannedPack) => void;
  onError?: (error: string) => void;
  allowManualEntry?: boolean;  // default true
}

export function DataMatrixScanner(props: DataMatrixScannerProps): JSX.Element;

// frontend/src/lib/gs1.ts
export function parseGs1Payload(raw: string): ScannedPack | null;

ACCEPTANCE CRITERIA
- DataMatrixScanner renders a <video> element with @zxing/browser bound to it.
- Asks for camera permission via getUserMedia. On denial, shows the manual
  entry fallback (HmvsSecureInput for each field).
- On successful scan: parse payload with parseGs1Payload, emit onScan.
- On scan error (unreadable, not a GS1 Data Matrix): emit onError.
- Works on iPad (validate the camera selection — prefer environment-facing).
- frontend/src/lib/gs1.test.ts covers:
  - Standard payload with all four AIs (01, 21, 17, 10)
  - Payload with FNC1 separators between variable fields
  - Malformed payload returns null
  - Expiry "260931" (invalid date) returns null
- Component test: camera permission denial → manual entry mode visible.

DO NOT
- Do not store the camera feed anywhere (no recording, no upload).
- Do not auto-submit after a single scan — show a confirmation step where
  the pharmacist sees the decoded values and confirms.
- Do not use a library that pulls in a >500kb wasm blob — the iPad
  deployment may have spotty connectivity.

FINALIZE
- Run: cd frontend && npm run typecheck && npm run lint && npm test
- Manual smoke: open the scanner on iPad, scan a real pack (or printed
  test Data Matrix), verify decoded fields match.
- Commit: "feat(hmv-10): 2D Data Matrix scanner with manual entry fallback"
- PR: "HMV-10: Pack scanner component (FMD compliance)"
```

---

### HMV-11 — Dispense wizard HMVS step (layers onto FR-3)

**Owner:** Eng A
**Branch:** `feat/hmv-11-dispense-wizard-hmvs`
**Depends on:** FR-3, HMV-7, HMV-8, HMV-10
**Effort:** 3–5 days

#### Scope
The actual user-visible HMVS integration: add a "verify each pack" step to the dispense wizard built in FR-3. For each medicine on the prescription, the pharmacist scans the pack with HMV-10, the app verifies via HMV-7, and on dispense confirm decommissions via HMV-8.

#### Acceptance criteria
- FR-3 dispense wizard gains a new step between drug summary and dispense confirm: **"Verify packs"**
- For each medicine: scanner widget (HMV-10), shows verification result (HMV-7 response), blocks progression if any pack returns DECOMMISSIONED / EXPIRED / RECALLED
- On dispense confirm: each verified pack is decommissioned (HMV-8) sequentially; UI shows progress
- If any decommission fails partway: pharmacist sees clearly which packs were decommissioned and which weren't, with reactivate (HMV-9) option for completed ones
- All copy in Greek
- E2E manual test: scan two real test packs, verify, decommission, observe HMVS state via sandbox console

#### Claude Code prompt
```
You are wiring HMVS verification into the dispense wizard (FR-3). This is
where the pharmacist's actual day-to-day FMD compliance happens — for every
prescription dispensed, every pack must be verified against HMVS before
dispense and decommissioned at dispense confirm.

INPUTS
- Read frontend/src/pages/Dispense/* (whatever FR-3 named the dispense
  wizard). Identify the step before "confirm dispense".
- Read frontend/src/components/DataMatrixScanner.tsx (HMV-10) — your scan UI.
- Read frontend/src/lib/api.ts — add hmvsVerify(qrCode) and
  hmvsDecommission(qrCode, reason) wrappers that call /pharmapi/hmvs/verify
  and /pharmapi/hmvs/decommission.

STUB CONTRACT
// frontend/src/pages/Dispense/steps/VerifyPacksStep.tsx
interface VerifyPacksStepProps {
  medicines: Array<{ nhrn: string; commercialName: string; quantity: number }>;
  onAllVerified: (verifiedPacks: VerifiedPack[]) => void;
  onCancel: () => void;
}

interface VerifiedPack {
  medicineNhrn: string;
  scannedPack: ScannedPack;  // from HMV-10
  verifyStatus: 'VERIFIED' | 'DECOMMISSIONED' | 'EXPIRED' | 'RECALLED' | 'UNKNOWN';
}

// frontend/src/pages/Dispense/steps/ConfirmDispenseStep.tsx
// (modify the existing FR-3 confirm step)
// On confirm: for each verified pack, call hmvsDecommission. Show
// per-pack progress. If any fail, show retry/reactivate options.

ACCEPTANCE CRITERIA
- A new VerifyPacksStep added between FR-3's drug-summary and confirm-dispense
  steps. Mounted in the wizard's step machine.
- For each medicine, render a scanner instance (HMV-10). Pharmacist can scan
  multiple packs if quantity > 1.
- Each scan triggers hmvsVerify; result displayed inline as
  ✅ Verified / ❌ Decommissioned / ❌ Expired / ❌ Recalled.
- Progression to confirm-dispense step is BLOCKED until:
  - Number of verified packs per medicine matches quantity prescribed
  - All packs have status VERIFIED (any other status blocks)
- Confirm step: on click, calls hmvsDecommission for each verified pack
  sequentially. Shows progress bar + per-pack status.
- Partial-failure UX: clearly show which packs were decommissioned and
  which weren't. For decommissioned packs, offer a "Reactivate" button
  that calls hmvsReactivate (the user might want to abort the dispense
  if a later pack fails).
- All copy via t() — strings include:
  steps.VerifyPacks.title: "Επαλήθευση Συσκευασιών"
  steps.VerifyPacks.scanPrompt: "Σκανάρετε τη συσκευασία"
  steps.VerifyPacks.verifyOk: "Επαληθεύτηκε"
  steps.VerifyPacks.verifyFailed: "Αποτυχία επαλήθευσης"
  steps.ConfirmDispense.decommissionProgress: "Απενεργοποίηση συσκευασιών..."
  steps.ConfirmDispense.partialFailure: "Μερική αποτυχία — δείτε λεπτομέρειες"

DO NOT
- Do not parallelise decommission calls. Sequential is safer — partial
  failure is recoverable; concurrent partial failure is much harder to
  reason about.
- Do not auto-reactivate on failure. Pharmacist decides.
- Do not allow the wizard to advance past the verify step if any pack is
  in a non-VERIFIED state, even if the pharmacist tries to "skip" it.

FINALIZE
- Run: cd frontend && npm run typecheck && npm run lint && npm test
- Manual smoke (when sandbox creds available): full flow through a 2-medicine
  prescription with 1 pack each. Verify pre-dispense, dispense, see HMVS
  state shows decommissioned in the HMVO sandbox console.
- Commit: "feat(hmv-11): HMVS verify + decommission steps in dispense wizard"
- PR: "HMV-11: Dispense wizard HMVS integration (depends on FR-3, HMV-7/8/10)"
```

---

## Layer 4 — Validation & delivery

### HMV-12 — HMVS audit log

**Owner:** Eng A
**Branch:** `feat/hmv-12-hmvs-audit`
**Depends on:** HMV-7, HMV-8, HMV-9 (extends them with audit calls)
**Effort:** 1 day

#### Scope
Use the existing `app/services/audit.py` (PR #76) pattern to append an `AuditLog` row for every HMVS verify, decommission, and reactivate call. Closes the TODOs left in those endpoints.

#### Acceptance criteria
- Each of HMV-7 / HMV-8 / HMV-9 endpoints fire `log_documentation_action` (or a new `log_hmvs_action`) on every call
- Audit action strings: `HMVS_VERIFY`, `HMVS_DECOMMISSION`, `HMVS_REACTIVATE`
- Resource type: `HMVS_PACK`, resource_id: the pack's serial number
- Fire-and-forget pattern (same as PR #76) — never blocks the user-facing response
- Failures logged at WARNING, never raised
- Shutdown drain handler added if not already (per my PR #76 review)

#### Claude Code prompt
```
You are extending the existing audit log infrastructure (PR #76) to cover
HMVS operations. Every verify, decommission, and reactivate call must
write an immutable audit row.

INPUTS
- Read backend/app/services/audit.py — log_documentation_action is the
  pattern. Either reuse it with a generic action string, or add a sibling
  log_hmvs_action that takes the same shape. Prefer the latter for clarity.
- Read backend/app/routers/hmvs.py (HMV-7, HMV-8, HMV-9). Each has a TODO
  comment for the audit call — replace those.

STUB CONTRACT
# backend/app/services/audit.py — add:
async def log_hmvs_action(
    *,
    pharmacist_id: uuid.UUID | None,
    pharmacy_id: uuid.UUID | None,
    action: Literal["HMVS_VERIFY", "HMVS_DECOMMISSION", "HMVS_REACTIVATE"],
    serial: str | None = None,
    outcome: str | None = None,  # "success" | "failure" | upstream code
) -> None:
    """Fire-and-forget audit row for HMVS operations. Never blocks the
    request. Failures log at WARNING."""

ACCEPTANCE CRITERIA
- log_hmvs_action implemented in audit.py using the same independent-session +
  background-task pattern as log_documentation_action.
- Each of HMV-7 / HMV-8 / HMV-9 endpoint handlers calls fire_audit_task(
  log_hmvs_action(...)) (or the equivalent module-level set tracking pattern
  from PR #76).
- AuditLog rows:
  - action ∈ {HMVS_VERIFY, HMVS_DECOMMISSION, HMVS_REACTIVATE}
  - resource_type = "HMVS_PACK"
  - resource_id = pack serial (NOT the full QR code — privacy)
- Shutdown drain handler exists in main.py for _background_tasks. If it
  doesn't exist yet (i.e., PR #76's follow-up never landed), add it:

  # main.py
  from app.services.audit import _background_tasks
  @app.on_event("shutdown")
  async def _drain_audit_tasks():
      if _background_tasks:
          await asyncio.gather(*_background_tasks, return_exceptions=True)

- Tests: extend test_hmvs_verify / decommission / reactivate to assert that
  an audit row was written after the response.

DO NOT
- Do not write the full QR code as the resource_id — just the serial.
- Do not store the upstream response body in the audit row — only the outcome.

FINALIZE
- Run: cd backend && pytest tests/test_hmvs_*.py -v
- Run: cd backend && ruff check . && ruff format .
- Commit: "feat(hmv-12): audit log entries for HMVS operations"
- PR: "HMV-12: HMVS audit trail (closes TODOs in HMV-7/8/9)"
```

---

### HMV-13 — Sandbox / test environment wiring

**Owner:** Eng A
**Branch:** `feat/hmv-13-sandbox-env`
**Depends on:** HMV-1, HMV-2
**Effort:** 1 day

#### Scope
Once HMVO sends the sandbox credentials + URL, wire them into our environment configuration. Create a `.env.hmvs.sandbox` template, document the setup, smoke-test the connection.

#### Acceptance criteria
- `backend/.env.example` updated with `HMVS_BASE_URL`, `HMVS_MOCK` placeholders
- `backend/.env.hmvs.sandbox.example` with HMVO sandbox URL (placeholder until real URL arrives) + instructions for getting credentials
- A `scripts/hmvs_smoke.py` script that calls verify against a known test pack and prints the response
- `docs/hmvs-setup.md` written: how to obtain HMVO sandbox creds, how to set them in the pharmacy admin UI (HMV-1), how to run the smoke script

#### Claude Code prompt
```
You are wiring the HMVS sandbox environment so engineers can test HMVS
integration locally once HMVO grants access. This is plumbing + docs, no
new product code.

INPUTS
- Read backend/.env.example — the pattern for new env vars.
- Read backend/app/config.py — HMVS_BASE_URL and HMVS_MOCK are added in HMV-2.
- Read backend/scripts/seed.py — the script style (argparse, asyncio.run).

DELIVERABLES
1. backend/.env.example — add:
   HMVS_BASE_URL=https://hmvo-sandbox.example.gr
   HMVS_MOCK=true

2. backend/.env.hmvs.sandbox.example — template:
   # Copy to .env.hmvs.sandbox and fill in real values from HMVO.
   # Obtained via the HMVO IT-suppliers portal after test book completion.
   HMVS_BASE_URL=<from HMVO email>
   HMVS_MOCK=false
   # Per-pharmacy credentials are set via the Settings admin UI (HMV-1),
   # not via env. These vars only configure transport.

3. backend/scripts/hmvs_smoke.py:
   - argparse args: --pharmacy-id, --qr-code (or --test-pack to use a
     hardcoded sample)
   - Loads HMVS_BASE_URL from env
   - Calls hmvs.hmvs_verify (or the underlying client function) for the
     given pharmacy + QR
   - Prints the full response, including status mapping
   - Exits 0 on VERIFIED, 1 on any other status

4. docs/hmvs-setup.md:
   - Section: "Getting HMVO sandbox access" — link to HMVO portal,
     summarise the test-book requirement
   - Section: "Setting credentials" — how to use the admin UI (HMV-1)
   - Section: "Smoke-testing the connection" — how to run hmvs_smoke.py
   - Section: "Going to production" — checklist (real creds, HMVS_MOCK=false,
     HMVS_BASE_URL points to production, screen recording sent to HMVO)

ACCEPTANCE CRITERIA
- All four files created.
- hmvs_smoke.py runs in mock mode without real HMVO access (HMVS_MOCK=true)
  and prints a mock response — useful for engineers without sandbox creds.
- docs/hmvs-setup.md is comprehensive enough that a new engineer can
  bootstrap without asking the team.

DO NOT
- Do not commit real HMVO credentials to the repo — even in .env.example.
- Do not write a script that mutates HMVS state (no decommission in smoke).

FINALIZE
- Run: cd backend && HMVS_MOCK=true python scripts/hmvs_smoke.py
  --pharmacy-id <any uuid> --test-pack
- Commit: "feat(hmv-13): sandbox env wiring + setup docs + smoke script"
- PR: "HMV-13: HMVS sandbox environment"
```

---

### HMV-14 — Screen recording deliverable for HMVO

**Owner:** Eng A (or designate)
**Branch:** N/A — deliverable lives outside the repo
**Depends on:** HMV-3, HMV-4 deployed to a runnable environment
**Effort:** 0.5 day

#### Scope
Record a screen capture showing the Caps Lock blocker (HMV-3) and the keyboard layout blocker (HMV-4) firing correctly when a pharmacist attempts to submit HMVS data with Caps Lock on / Greek keyboard active. Send the recording to HMVO via email per their pre-qualification requirement.

#### Acceptance criteria
- Recording shows:
  - Caps Lock turned on → attempted submission → Greek warning shown, submission blocked
  - Caps Lock turned off → submission proceeds
  - Greek keyboard active → typed Greek chars in the field → warning shown, submission blocked
  - English keyboard restored → submission proceeds
- Recording is ≤2 minutes, captioned in Greek
- Sent to the HMVO contact from the original email thread, referencing the IT-suppliers ticket number
- A copy is archived in `docs/hmvo-deliverables/screen-recording-2026-XX.mp4` (or linked in `docs/hmvo-deliverables/README.md` if git-lfs unavailable)

#### Claude Code prompt
```
This is a delivery item — record a screen capture proving HMV-3 (Caps Lock
blocker) and HMV-4 (keyboard layout blocker) work as committed in the HMVO
reply, and send it to HMVO via email.

INPUTS
- Branch with HMV-3 + HMV-4 deployed, running locally or on a staging URL
  the recorder can access.
- Reference the original HMVO email thread (the one in the IT-suppliers
  inbox you're CC'd on).

RECORDING SCRIPT
1. Open the app in a fresh browser session.
2. Navigate to a screen with an HMVS data entry field (e.g. the dispense
   wizard's pack verification step, or a dedicated demo page).
3. Type a sample HMVS serial number with Caps Lock OFF — show the field
   accepts input normally.
4. Turn Caps Lock ON — show the warning message appearing in Greek, the
   submit button disabling.
5. Turn Caps Lock OFF — show the warning clearing, submit re-enabling.
6. Switch keyboard layout to Greek (Cmd+Space on Mac, Alt+Shift on Windows).
7. Type a character — show the Greek character lands in the field, the
   warning message appears in Greek, submit disabled.
8. Switch back to English layout, clear the field — show warning clears,
   submit re-enabled.
9. End recording.

ACCEPTANCE CRITERIA
- Recording is ≤2 minutes (ideally 60-90 seconds).
- Both warnings clearly visible in Greek.
- File format: .mp4 or .mov, H.264 codec for broad compatibility.
- File size <50MB (compress if needed).
- Email to HMVO contact (from the original email thread) with:
  - Subject: "PharmAssist — Screen recording: Caps Lock & keyboard layout
    safeguards (IT supplier ticket #...)"
  - Body: brief Greek note confirming this delivers on points 5 + 6 of the
    pre-qualification requirements
  - Recording attached or linked (Google Drive / WeTransfer if too large)
- Archive in docs/hmvo-deliverables/ (create dir if needed). If the file is
  >10MB and git-lfs isn't set up, store the file elsewhere and add the link
  to docs/hmvo-deliverables/README.md.

DO NOT
- Do not record showing patient data or real prescriptions — use mock data
  only.
- Do not record any other features beyond what the script covers — focus.

FINALIZE
- Send the email.
- Add docs/hmvo-deliverables/README.md noting the recording was sent,
  with date, recipient, and link/checksum.
- Commit: "docs(hmv-14): HMVO screen recording delivery log"
```

---

### HMV-15 — Test book completion

**Owner:** Eng A + Eng B (whichever has bandwidth at that phase)
**Branch:** `feat/hmv-15-test-book`
**Depends on:** HMV-13 (sandbox access) + HMVO sending the test book
**Effort:** 3–7 days (rescope when test book arrives)

#### Scope
The HMVO test book is a structured checklist of scenarios our software must execute successfully against their sandbox to qualify for production access. Until they send it, we don't know exactly what's in scope. This ticket is a placeholder; reshape into concrete sub-tickets once the test book lands.

#### Acceptance criteria (template)
- Test book received from HMVO
- Each test scenario documented in `docs/hmvo-deliverables/test-book-results.md` with: scenario number, description, our execution log, pass/fail, screenshots/recordings
- All required scenarios pass
- Results submitted to HMVO via the IT-suppliers portal
- Production HMVS access granted

#### Claude Code prompt
```
This ticket is a placeholder pending receipt of the HMVO test book. When
the test book arrives, scope individual sub-tickets per scenario and link
them here.

EXPECTED CONTENT (typical IT-supplier test books):
- Verify scenarios: valid pack, decommissioned pack, expired pack, recalled
  pack, unknown serial
- Decommission scenarios: happy path, idempotency, partial-batch
- Reactivate scenarios: within window, outside window
- Negative scenarios: Caps Lock blocker, keyboard layout blocker
- Error scenarios: HMVS unreachable, malformed response

PLACEHOLDER WORK NOW (before test book arrives)
- Create docs/hmvo-deliverables/test-book-results.md with section headers
  for likely scenarios and a "TODO: rescope when test book arrives" note
  at the top.
- Verify all the prerequisites are in place (HMV-1 through HMV-14 all
  merged) before HMVO is told we're ready to take the test book.

WHEN TEST BOOK ARRIVES
- Read it end-to-end before writing any code or sub-tickets.
- Open one PR per scenario group (not one giant PR — easier to review and
  retry if any fail).
- Each PR includes: code changes (if any), test scenario execution log,
  screenshots / recordings as evidence.

DO NOT
- Do not start the test book until HMV-1 through HMV-14 are all merged.
- Do not assume scenario specifics — wait for the document.

FINALIZE (when complete)
- Submit results bundle to HMVO via the IT-suppliers portal.
- Wait for HMVO sign-off.
- Commit: "feat(hmv-15): HMVO test book completion + sign-off"
```

---

## Coordination notes

- **Daily rebase** for branches that touch shared files (HMV-7 / 8 / 9 / 12 all touch `routers/hmvs.py`)
- **Cross-track review**: redesign engineer reviews HMVO PRs touching frontend (HMV-3 / 4 / 10 / 11); HMVO engineer reviews redesign PRs touching FR-3 / FR-5c
- **HMVO contact protocol**: any clarification needed from HMVO goes through the user (single point of contact), not directly from engineers
- **Sandbox access timeline**: every ticket from HMV-7 onward CAN be developed in mock mode (`HMVS_MOCK=true`) but needs sandbox validation before HMV-15. Plan sandbox-access milestone before HMV-15 starts.

## Out of scope

- Production HMVS (only sandbox until HMV-15 passes)
- Multi-pharmacy HMVS credential management (single pharmacy per session in scope; chain customers come later)
- HMVS rate-limiting / quota tracking (assume HMVO sandbox doesn't enforce)
- Customer-facing pricing for HMVS feature (handled in B2B pricing doc separately)
