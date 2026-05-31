# Claude Design Prompts — Pharmassist Redesign

A copy-paste prompt pack for using **claude.ai artifacts** to mock up every
page of Pharmassist in the new event-driven model from
[`going-real-live-mode-ux.md`](./going-real-live-mode-ux.md).

## How to use

1. Open [claude.ai](https://claude.ai), start a **new conversation** with
   the strongest available model (Opus / Sonnet 4.x).
2. **Paste the Setup prompt** below first — it establishes the design
   system, tech stack, voice, and shared rules. The reply will acknowledge.
3. Then paste **one page prompt at a time**. Each builds on the setup.
   Ask Claude to render an artifact (React + Tailwind) for that page.
4. Iterate by replying with "make X bigger / move Y / try a sidebar
   variant" — artifacts update in place.
5. When a design is locked in, drop back into this repo's `claude` CLI and
   ask it to implement the chosen mock against the real backend.

Treat Claude's first artifact for any page as a v1 — typical iteration is
3–5 turns to land on something good. Best results when you describe
*intent and constraints*, not pixels.

---

## Setup prompt (paste first)

```
You are helping me redesign Pharmassist, a B2B web app for Greek pharmacists
to verify, dispense, and document prescriptions. The integration target is
ΗΔΥΚΑ (Greek national e-prescription system).

Throughout this conversation, generate each page as a self-contained
React + Tailwind v3 artifact (no external state libraries; use useState
locally). Use realistic mock data inline. Make each artifact a complete
page (header, navigation chrome, content).

DESIGN SYSTEM (already in the codebase — match it):
- Stack: React 18 + TypeScript + Tailwind v3 + react-router. Single-page app.
- Brand color: blue scale `brand-{50,100,200,500,600,700,800}` where
  brand-600 = #2563EB. Use brand-600 for primary CTAs, brand-50/100 for
  subtle backgrounds, brand-700 for hover.
- Semantic colors:
    - amber-{50,300,600,700} for "review required" / warning
    - red-{50,300,600,700} for "block / critical" / error (use animate-pulse-red-border on critical cards)
    - emerald-{50,500,600} for "ok" / success
    - slate-{50,100,200,500,700,900} for neutral text + surfaces
- Surface: white cards with `border border-slate-200 shadow-card rounded-xl`.
  Hero/empty-state surfaces can use `shadow-cardLg`.
- Typography: system sans (Inter-ish). Headings semibold/bold, body 13–14px,
  comfortable line-height.
- Icons: lucide-react names are fine; in the real codebase they're custom
  SVGs (PillIcon, AlertCircleIcon, ShieldIcon, ClockIcon, AlertTriangleIcon,
  ChevronRightIcon, CheckIcon, FlagIcon, FileTextIcon, BarcodeIcon, UserIcon).
- Localisation: pharmacist-facing copy is English (the SPA is bilingual but
  English is the source). Patient names, drug names, insurance names can
  show in Greek where realistic.
- Tone: clinical, calm, decisive. Not playful. Pharmacists are time-pressed
  professionals.

DESIGN PRINCIPLE (this is critical — the whole redesign hinges on it):
The app is event-driven, not queue-driven. There is no pre-populated list
of "prescriptions waiting for me." Every workflow starts with a pharmacist
**scanning a paper barcode** OR **entering a patient's AMKA + SMS PIN**.
Everything else (verification, alerts, dispense, history) is a downstream
consequence of that scan. So the primary CTA on the landing page is a
scanner — not a stat-card dashboard.

LAYOUT BASELINE (use for every authenticated page):
- Left sidebar (240px on desktop, collapses to icons on tablet, drawer on
  mobile): logo, nav items, current pharmacy name + pharmacist name at the
  bottom, sign-out.
- Main content area: max-width ~1100px, generous padding (p-8), one or
  two columns depending on the page.
- Page title + brief subtitle/breadcrumb at the top of each page.
- Toast notifications for transient confirmations (top-right).

NAVIGATION ITEMS (sidebar):
1. Counter (primary workspace — was "Dashboard")
2. Patients
3. History (was "Documentation Log")
4. Reports (Side-Effect / ADR)
5. Settings

When I send a page prompt, render an artifact with realistic mock data,
including loading/empty/error variants where they meaningfully differ.
Acknowledge this setup briefly, then wait for the first page prompt.
```

---

## Page 1 — Sign in

```
Render the SIGN IN page (route /login).

Single centered card, ~420px wide, on a soft slate-50 background. Match
the established pharmaceutical/SaaS aesthetic — calm, clean, trustworthy.

Content:
- Brand mark at top: small rounded-2xl tile (56×56, bg-brand-600, white
  pill icon), "PharmAssist" wordmark below in brand-600 bold.
- Tagline below the wordmark, ~13px slate-500: "Prescription verification
  & dispensing for Greek pharmacies."
- Email field (id=email, type=email, placeholder "pharmacist@demo.gr").
- Password field with a show/hide toggle button (eye icon).
- "Forgot password?" link aligned right on the password label row.
- Primary button "Sign in" (full-width, bg-brand-600, hover bg-brand-700).
- Below the button, smaller text: "New here? Ask your pharmacy admin for
  an invite."
- Footer line at the very bottom: "© Pharmassist · privacy · terms"
  in slate-400, tiny.

States to include (use a small state-switcher at the top of the artifact
so the viewer can toggle):
- Default (empty form)
- Submitting (button shows spinner + "Signing in…")
- Error ("Invalid credentials" — inline alert above the form, red-50
  background, red-700 text, AlertCircle icon)

No social/Google sign-in. The cookie is httpOnly + Secure; that's a
backend concern, no UI flag needed.
```

---

## Page 2 — Accept invite (onboarding)

```
Render the ACCEPT INVITE page (route /accept-invite?token=…).

This is the first-run experience: a pharmacy admin sent the new pharmacist
an email invite with a tokenized link. The page reads the token, shows
context, and asks the new user to set a password.

Layout: same centered-card pattern as Sign in.

Content:
- "Welcome to PharmAssist" headline.
- Read-only context block (read from token-derived state):
    "You've been invited by ΛΑΔΙΚΟΣ ΑΛΕΞΙΟΣ-ΛΑΜΠΡΟΣ
     to join ΦΑΡΜΑΚΕΙΟ Fedra as a pharmacist."
- Full name field (pre-filled from token if available; editable).
- Password field with a strength meter (4-segment bar: weak / fair / good
  / strong) and inline requirements (≥10 chars, mixed case, a number).
- Confirm password field.
- Checkbox: "I agree to the terms of service and the GDPR data-processing
  notice." (link the words "terms" and "GDPR notice")
- Primary button "Create account" (disabled until valid + checkbox).
- Small "Already have an account? Sign in" link at the bottom.

States:
- Valid token (default render)
- Invalid/expired token: replace the form with an empty-state card —
  AlertCircle icon, "This invite is no longer valid" headline, body
  copy "Invites expire after 7 days. Ask your pharmacy admin to send a
  new one.", and a "Back to sign in" link.
- Account created (success): brief confirmation + auto-redirect intent
  ("Redirecting to your counter…"), inline spinner.
```

---

## Page 3 — Counter (was Dashboard) — THE primary workspace

```
Render the COUNTER page (route /counter, the post-login landing).

THIS IS THE PAGE THAT MOST DEPARTS FROM THE OLD DESIGN. Read carefully.

The page is a counter workspace, not a passive dashboard. The pharmacist
arrives here, scans the next patient's prescription, reviews, dispenses,
and moves on. Pre-populated queues don't exist in the real ΗΔΥΚΑ API; the
page must reflect that.

Hierarchy (top to bottom of the main column):

1. PAGE HEADER
   - Title "Counter"
   - Subtitle: today's date in Greek (e.g. "Σάββατο, 31 Μαΐου 2026"),
     pharmacy name beside it.

2. HERO INPUT — SCAN PRESCRIPTION  (occupies the most visual weight)
   A large rounded-2xl white card, ~p-8, soft brand-50 inner panel.
   Two ways to start a dispense, side by side or tabbed:

   a) "Scan paper barcode"
      - Large icon (Barcode), label "Scan or type prescription barcode"
      - Single big input, autoFocus, placeholder "e.g. 2605292031642"
      - Primary "Open" button (brand-600). Press Enter also submits.
      - Subtle helper text: "Triggers /prescriptions/get/{barcode}"

   b) "Paperless (AMKA + PIN)"
      - Icon (Shield or Key), label "Patient gave you a 6-digit PIN"
      - Two inputs: AMKA (11 digits) + PIN
      - Secondary "Look up" button

   Make the two-method UI clear without being cluttered. A pill-tab switcher
   at the top of the card works well, with the active method's inputs
   below.

3. IN PROGRESS — short list (often 0–3 items, never very many)
   Section header: "In progress" with a count chip "(2)".
   If empty: subtle slate-500 italic line: "No prescriptions in progress.
   Scan a barcode above to start." (don't make this dominate the page)
   If items: list rows with:
   - barcode (mono font)
   - patient name (truncate long ones)
   - "2 alerts" or "OK" chip (red/amber/green) summarizing safety status
   - timestamp ("Started 8 min ago")
   - ChevronRight on hover → /review/{barcode}
   - A small "✕ Abandon" link on hover

4. RECENTLY COMPLETED — last ~5 dispenses today
   Section header: "Today" with a count chip and a "Full history →" link.
   Compact list:
   - ✓ check icon (emerald-500) or ⚐ flag icon for flagged ones
   - time, barcode (mono short), patient name, medication primary name
   - Subtle hover, links to the row's record in /history.

5. SAFETY ALERTS PANEL  (right side on desktop, below on mobile)
   This is the existing concept — keep it. But the source is alerts from
   currently-in-progress scans only (it'll often be small, sometimes empty).
   When empty: green check + "No active safety alerts" message.

OPTIONAL ELEMENTS:
- Above the hero, a thin status strip showing "ΗΔΥΚΑ session active —
  refreshes 23:14" so the pharmacist knows the upstream connection is alive.
- Keyboard shortcuts hint at the bottom (subtle): "⌘K to focus scanner".

Mock data: 2 in-progress (one with a CRITICAL alert, one OK), 5 today's
dispenses, 2 active safety alerts in the panel.

States to toggle in the artifact:
- Default (with mock data above)
- First-time login: in-progress empty, today empty — show a friendly
  "Ready when you are. Scan your first prescription above." illustration
  (just an icon + copy, nothing fancy)
- ΗΔΥΚΑ session expired: a banner at the top: "Session refresh required —
  click here to re-authenticate" (amber)
```

---

## Page 4 — Review (was Verification)

```
Render the REVIEW page (route /review/:barcode).

Triggered immediately after a successful scan. The pharmacist arrives here
because they JUST scanned 2605292031642. The page is dense by necessity —
everything they need to make a dispense decision should be on one screen.

Layout: three columns on wide screens (collapse to one on mobile).

Top bar (above the columns):
- Back link "← Back to counter"
- Page title "Review prescription" + barcode in mono
- Right side: three buttons —
    [ Contact prescriber ]  (secondary, phone icon)
    [ Flag discrepancy ]    (warning style)
    [ Approve & dispense → ] (primary, brand-600)
  The Approve button is DISABLED with a tooltip when any safety check is
  status=block.

Column 1 — PATIENT  (~40% width)
- Name (bold, 18px), age, sex
- AMKA (mono), insurance ("IKA-ETAM"), participation %
- Date of birth, phone
- Address (single line, truncated)
- A "View full patient profile →" link
- Below: a colored info banner if `patientPartExceptions` has any
  exception ("Πλημμυροπαθής Θεσσαλίας 2023-06-01 →" with subtle yellow
  background — informational, not alarming).
- Below that: a separate info banner if `info` is present (public-health
  notification message from ΗΔΥΚΑ that the pharmacist should relay to
  the patient). Distinguish from safety alerts: use a soft brand-50
  background + Info icon, not red.

Column 2 — MEDICATION  (~30% width)
- Drug name (bold, 18px): "ALGOFREN F.C.TAB 600MG/TAB BTx20"
- Active substance ("Ibuprofen"), ATC code ("M01AE01"), EOF code
- Dose, form, route, frequency (in a grid)
- Treatment duration, validity dates (issued → expires)
- Prescriber: name + licence number + specialty + contact

Column 3 — AUTOMATED SAFETY CHECKS  (~30% width)
- Title "Automated Safety Checks" with a small "live" indicator (green dot)
- Status legend (small): ✓ ok / ⚠ review / ⛛ immediate action
- A vertical list, one row per check, ordered by severity (block →
  review → ok):
    ⛛ Drug-Drug Interactions  CRITICAL  red card with pulse animation
       "Active Amiodarone — over-anticoagulation risk."
       [Details ▾]
    ⚠ Contraindications  REVIEW  amber card
       "eGFR 28 mL/min — verify renal function."
       [Details ▾]
    ✓ Duplicate Therapy  OK  green-50 card, low emphasis
    ✓ Dose Validation  OK
    ⚠ SPC Alignment  REVIEW

Below the safety panel, a small footer:
- Source attribution: "Engine source: live ΗΔΥΚΑ history + intolerances +
  drug catalogue"
- Last refresh timestamp.

Mock data: use the real ΗΔΥΚΑ test prescription we found —
- barcode 2605292031642
- patient: ΟΝΟΜΑ-ΒΞ ΕΠΩΝΥΜΟ-ΒΞ, AMKA 05055505340, sex Θήλυ, born 1939
- ALGOFREN F.C.TAB 600MG, ibuprofen
- 1 CRITICAL block alert + 1 REVIEW alert + 1 review SPC + a few OK rows

States to toggle:
- Loading (skeleton placeholders in each column, ~600ms)
- No safety issues (all checks OK, Approve button is bright primary)
- Has a BLOCK alert (Approve button is disabled with tooltip "Resolve all
  critical safety alerts before approving")
- ΗΔΥΚΑ data partially missing (e.g., patient history call timed out) —
  show an inline notice in the safety column: "Could not fetch patient
  history — interaction checks may be incomplete. [Retry]"
```

---

## Page 5 — Dispense wizard (modal)

```
Render the DISPENSE WIZARD modal (opens from the Approve button on Review).

This is a new flow — it didn't exist when dispense was a 501 stub. It runs
the FMD authenticity check then sends the HL7 dispense to ΗΔΥΚΑ.

Modal: centered, white card ~560px wide, soft backdrop. Has a clear
"X" / Esc to cancel. Two steps.

STEP 1/2 — Verify medicine pack (FMD)

- Step indicator at top: ●○ (filled dot 1, empty dot 2)
- Title "Verify medicine pack"
- Subtitle: "Scan the DataMatrix on the back of the ALGOFREN box. This
  confirms the pack is genuine and decommissions it from the EU FMD registry."
- Big scanner area: dashed border, slate-50 background, ~180px tall,
  with a Barcode icon and copy "Scan or type the DataMatrix payload"
- Auto-focused text input below
- A "Skip — manual entry" link for cases where the strip is damaged (this
  branches to a small form for productCode + serialNumber + batch + expiry,
  with scheme selector GS1 / PPN)
- Footer buttons: [ Cancel ]   [ Verify pack → ] (primary)

STEP 2/2 — Confirm dispense

After verification succeeds:
- Step indicator: ●●
- Title "Confirm dispense"
- A green check banner: "Pack verified — Active in the HMVS registry"
- Summary block:
    Patient: ΟΝΟΜΑ-ΒΞ ΕΠΩΝΥΜΟ-ΒΞ
    Medicine: ALGOFREN F.C.TAB 600MG/TAB BTx20
    Patient pays: €2.40  (25% participation)
    Pack will be decommissioned on confirm.
- Optional checkbox: "Generate counseling instructions after dispense"
  (off by default)
- Footer: [ Back ]   [ Confirm dispense ] (primary)
- After click: button shows spinner, then a success state — the modal
  morphs to a final screen with a big check, "Dispensed successfully"
  + the executionNo + barcode, "Print receipt" link, and "Back to counter"
  button that closes the modal and navigates.

States to toggle:
- Step 1 idle
- Step 1 verifying (spinner)
- Step 1 verification failed — "Pack already dispensed (status 2)" with
  red icon + "Show details" expander
- Step 2 idle
- Step 2 submitting
- Step 2 success
- Step 2 failure ("ΗΔΥΚΑ rejected the dispense: G02 — already executed.
  [Show diagnostic]")
```

---

## Page 6 — Patients (list + search)

```
Render the PATIENTS page (route /patients).

This is the "browse without a prescription in hand" view. Used when a
pharmacist wants to look up a patient before counseling, or to start a
paperless flow from a patient profile.

Layout:
- Page header "Patients", subtitle "Search by AMKA, EKAA, or name."
- Search bar (big, autofocus): "Search patients" with a Search icon.
- Below the search bar: a small toggle row of recent lookups (last 5
  patients this pharmacist viewed today) as chips.
- Main area: either an empty-state illustration when no search, OR
  results list when search is active.

Empty state (no search):
- Friendly illustration (icon stack or simple SVG)
- "Search a patient to see demographics, history, and active intolerances."
- Sub-link "Or scan a prescription instead → /counter"

Results list:
- Each result row: avatar circle (initials), name (bold), AMKA (mono),
  age + sex, last visit timestamp, ChevronRight.
- "Patient not found in ΗΔΥΚΑ" empty result with a helpful message.

States:
- Empty (no search yet)
- Searching (skeleton rows)
- Results found (3 mock patients using the real test AMKAs)
- No matches
- Error (ΗΔΥΚΑ down)
```

---

## Page 7 — Patient profile

```
Render the PATIENT PROFILE page (route /patients/:amka).

The full view of a single patient. The page that combines what we already
fetch (demographics, history, intolerances, DB conditions) into one
coherent screen.

Layout: header + 3 stacked sections (or 2 columns on wide screens).

HEADER STRIP:
- Avatar (initials), name (large bold), AMKA mono, age, sex, insurance.
- Right side: [ Start paperless dispense → ] button (primary; navigates
  to /counter with the AMKA pre-filled in the paperless tab).
- Secondary buttons: [ Report side effect ] [ View documentation ]

SECTION 1 — DEMOGRAPHICS & FLAGS
- Two-column grid: DOB, sex, nationality, phone, email, address.
- Below: any `patientPartExceptions` shown as chips (Πλημμυροπαθής
  Θεσσαλίας 2023-06-01, etc.)
- Any active ΗΔΥΚΑ `info` notification shown as a brand-50 banner.

SECTION 2 — INTOLERANCES & CONDITIONS  (this is the safety-critical bit)
- Two sub-panels side by side:
  a) "Intolerances (ΗΔΥΚΑ)" — list of items (e.g., ACECLOFENAC →
     "Έλκος / Γαστρορραγία"), each row showing the active substance, the
     reaction, and (if present) treatment protocol/notes.
  b) "Conditions on file (this pharmacy)" — items recorded locally by
     pharmacists at THIS pharmacy (chronic, allergies, special protocols).
     Each row has an "Edit" / "Remove" action since these are our records.
- Below the panels: a small "Add condition" button (opens a modal).

SECTION 3 — MEDICATION HISTORY
- Header with filter chips: [All] [Last 90 days] [Last year] [By drug].
- Vertical timeline list:
    2026-05-13  ALGOFREN F.C.TAB 600MG  ✓ Dispensed at our pharmacy
    2025-11-12  Atorvastatin 20mg       ✓ Dispensed at another pharmacy
    ...
- Each row: date, drug name, dispensed-at indicator, "Details ▾" expander.

States:
- Loading (skeleton on each section)
- Patient with rich data (use AMKA 05055505340 — has 2 history entries, 8
  intolerances in real data we observed)
- Patient with no clinical data ("No medicine history on file for this
  patient.")
- Patient with consent not granted (history/intolerances panels show a
  consent gate: "This patient hasn't granted consent for clinical-data
  access. [Request consent →]")
```

---

## Page 8 — History (was Documentation Log)

```
Render the DISPENSE HISTORY page (route /history).

Compact, table-heavy. The completed dispenses log. Pharmacists use this
for audit, search, and re-printing receipts.

Layout:
- Header "Dispense history", subtitle "Filter and search past dispenses."
- Stat strip at the top:
    "Today  12   |   This week  68   |   This month  287"
- Filters row (sticky on scroll):
    - Date range picker
    - Method chips: All / Print / Digital / Both
    - Search input (patient name, AMKA, barcode, drug name)
    - "Export CSV" secondary button (right-aligned)
- Main table:
    Columns: Date/time | Barcode | Patient | Medication | Method | Status | …
    Status uses chips: green "Dispensed" / red "Flagged" / amber "Partial"
    Each row hover → row actions appear at right: [Print receipt] [Open]
- Pagination at bottom.

Mock 10 realistic rows mixing all states.

States:
- Default (with mock rows)
- Empty (no results for the filters) — friendly empty state with clear
  copy + "Reset filters" button
- Loading
```

---

## Page 9 — Reports / Side Effects (ADR)

```
Render the REPORTS / SIDE EFFECTS page (route /side-effects).

This is the post-dispense reporting workflow — pharmacists report adverse
drug reactions. It's a separate concern from the main scan→dispense flow.

Layout: two views in one page (tabbed at the top):

TAB 1 — "Report an event"
- "Report a new side effect" prominent CTA at the top
- A short wizard-style form (single page, not modal):
    Step (single column, segmented):
    1. Patient — search or pick from recent
    2. Medicine — search or scan barcode (autofills from /drug_catalog)
    3. Reaction:
       - Severity (radio: Mild / Moderate / Severe)
       - Onset (date picker + "during therapy" / "after stopping")
       - Symptoms (multiline text with a "Common symptoms" picker)
       - Suspected causality (dropdown)
    4. Submit
- Right-side helper panel: "What counts as reportable?" with short bullet
  guidance.

TAB 2 — "Previous reports"
- Table of reports filed by this pharmacist, status (Draft / Submitted /
  Acknowledged), severity, date, patient (anonymised display: AMKA last
  4 + initials).
- Filters: status, severity, date range.
- Row actions: View / Edit (if draft) / Withdraw.

Mock 3 previous reports in the table.

States:
- Default
- Form mid-fill
- Form submitted (toast + scrolls to top with success banner)
- Empty "Previous reports" tab
```

---

## Page 10 — Settings

```
Render the SETTINGS page (route /settings).

The first version of an admin/settings area — pharmacy profile + per-user
preferences + credentials.

Layout: left sub-nav within the page (vertical list of sub-pages), main
panel on the right.

SUB-PAGES:
1. Profile — name, email, eof_licence_no (read-only), language preference,
   notification preferences (in-app + email toggles).
2. ΗΔΥΚΑ credentials — Pharmapi username (read-only), "Update password"
   button (modal that POSTs to backend re-encryption flow). Last-session
   timestamp + "Refresh session now" button.
3. Pharmacy — pharmacy name (read-only from ΗΔΥΚΑ), category (e.g.,
   ΕΟΠΥΥ / non-ΕΟΠΥΥ), VAT/tax info, address. With a small explainer:
   "Category controls clinical-data access. Contact ΗΔΥΚΑ to change."
4. Team — only visible to pharmacy admins. List of pharmacists at this
   pharmacy, "Invite pharmacist" button, role per row.
5. Audit log — a paginated read-only log of every dispense, every patient
   data access, every login. Filterable. CSV export.
6. Danger zone — "Sign out everywhere" / "Delete account" (admin-only for
   delete; standard cookie wipe for sign-out everywhere).

Mock data on each sub-page should reflect what we already store.

States:
- Default (Profile selected)
- Each sub-page
- Form-save success (inline toast)
```

---

## Polish prompts (run AFTER all pages are mocked)

### Consistency pass
```
Look back at every page you've rendered so far. Identify and fix any
inconsistencies in:
- Header/sidebar chrome (should be identical across all authenticated pages)
- Button sizes and primary/secondary styling
- Typography hierarchy (heading sizes per level)
- Spacing rhythm (consistent padding/margins)
- Color usage for status (block/review/ok must be the same red/amber/green
  everywhere)
- Empty-state copy voice (clinical, calm, decisive — never apologetic)

Render a consolidated "Design tokens & components" artifact showing the
final palette, type scale, and the 6–8 most-used components (button,
input, card, alert banner, chip, table row, modal) as standalone examples.
```

### Mobile pass
```
For each page, describe what changes on mobile (≤640px). Don't re-render
each page — describe the responsive collapses and produce ONE artifact
showing the Counter page rendered at iPhone width as the canonical example.
Sidebar becomes a top hamburger; Review's 3 columns stack; the Dispense
wizard becomes full-screen instead of a modal.
```

### Dark mode (optional)
```
Render the Counter page in a dark theme (slate-900 background, slate-100
text, brand-400 accents). Confirm semantic colors (red/amber/green) still
have enough contrast at AA. Don't actually theme the whole app yet — this
is an exploration to see if dark mode is worth pursuing.
```

---

## Tips for getting good output

- **Don't over-specify pixels.** Describe *intent* ("dense but breathable",
  "scanner is the visual anchor"). Claude is better at intent than at
  pixel-perfect specs.
- **Iterate on layout before content.** Get the column/row structure right
  in one turn, then refine copy/microcopy/edge-cases in subsequent turns.
- **Always include states.** "Render this page + show me the empty state
  + show me the error state" yields a much more honest design.
- **Ask for one artifact per page.** Conversations get unwieldy if every
  page is in the same artifact.
- **Push back.** "That's too busy" / "the in-progress panel is fighting
  the hero for attention" → very effective.
- **Show, don't tell, when iterating.** Paste a screenshot of competitor
  software you like, or a Figma frame URL, and say "this kind of vibe."
- **End every conversation with a screenshot dump.** Once locked in, save
  PNGs of each page so you can hand them to the implementing engineer
  (or to the `claude` CLI in this repo) without context loss.

## When designs are locked in

Switch from `claude.ai` artifacts back to the `claude` CLI in this repo.
Paste the chosen artifact's React code (or just screenshots + a short
spec) and ask it to:

1. Wire each page to the real backend endpoints (the live ones, not mock).
2. Extract reusable components into `frontend/src/components/`.
3. Replace the existing pages incrementally — one PR per page is sanest.
4. Match the existing Tailwind config + icon library so the diff is
   minimal and reviewable.

The redesign is then a series of small focused PRs, not a Big-Bang rewrite.
