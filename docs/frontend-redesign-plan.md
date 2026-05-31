# PharmAssist Frontend Redesign — Plan & Claude Code Prompts

**Goal:** transform the existing frontend so it matches the `pages/`
mockups (the "Counter / Review / Dispense / Patients / History / Reports
/ Settings" redesign).

**How to use this doc:** it is split into (1) a gap analysis,
(2) open decisions to confirm, (3) the foundation token changes, and
(4) a sequence of ready-to-paste **Claude Code prompts**. Run the prompts
in order from inside the repo. This doc makes no edits to the project
itself.

> **Companion docs:**
> [`going-real-live-mode-ux.md`](./going-real-live-mode-ux.md) (why the IA
> changes), [`going-real-production-readiness.md`](./going-real-production-readiness.md)
> (what the redesign does *not* cover), and
> [`claude-design-prompts.md`](./claude-design-prompts.md) (the upstream
> claude.ai design prompts).

---

## TL;DR — the gap is small

The current frontend is **the same stack as the mockups**: React 18 +
TypeScript + Vite + react-router v6 + Tailwind 3.4. There is **no
framework migration** and **no design-token rebuild** — the mockups were
clearly derived from this repo. `tailwind.config.js` already defines the
`brand` palette, `shadow-card` / `shadow-cardLg`, and the `alert-in` /
`pulse-red-border` / `slide-in-right` / `fade-in` animations exactly as
the mockups use them.

So the work is three buckets:

- **A. Foundation** — add three missing tokens (`.mono` font class,
  `shadow-modal`, `shimmer` animation) + the icons the mockups use,
  restyle the shared `Sidebar`, and apply one design-system rule
  (semantic colors are reserved for safety state only).
- **B. Restyle existing screens** — Counter (Dashboard), Review
  (PrescriptionVerification), Sign-in (Login), Accept-invite, Reports
  (Side Effects), Patient profile.
- **C. Build new screens** — Patients **list**, Dispense **wizard**,
  **History**, **Settings**. These don't exist yet.

**Honesty flag (read before scoping):** parts of the redesign imply
backend endpoints that **do not exist today**. Specifically the Counter
"Paperless (AMKA + PIN)" lookup and the Dispense wizard's pack
**verify + decommission** (EU FMD) steps. `lib/api.ts` has no functions
for them and `backend/app/routers/prescriptions.py` has no routes.
Barcode scanning, however, can reuse the existing `getPrescription(rxId)`
(in live mode `rxId` *is* the ΗΔΥΚΑ barcode). The prompts below build
these UIs against clearly-marked stubs with disabled states, so the
frontend can ship without waiting on the backend.

**Rough effort:** ~7–10 engineer-days end-to-end for light-mode parity
with no backend work. Per-phase breakdown:

| Phase | Effort |
| --- | --- |
| 0 — Foundation | ½ d |
| 0.5 — Live-mode awareness | ¼ d |
| 1 — Counter | 1 d |
| 2 — Review | 1 d |
| 3 — Dispense wizard | 1–2 d |
| 4 — Patients (list + profile) | 1–1.5 d |
| 5 — History, Reports, Settings | 2–3 d |
| 6 — Polish (mobile, opt. dark) | ½–1 d |

---

## Mockup → code mapping

| Mockup (`pages/`) | Current file | Action |
|---|---|---|
| `00-design-system` | `tailwind.config.js`, `src/index.css` | Add `.mono`, `shadow-modal`, `shimmer`; align `.card` radius. Foundation. |
| `01-sign-in` | `pages/Login.tsx` | Restyle to match. |
| `02-accept-invite` | `pages/AcceptInvite.tsx` | Restyle to match. |
| `03-counter` | `pages/Dashboard.tsx` | **Major restyle** — add scan hero, In-progress / Today lists, Active-safety rail, session strip. |
| `04-review` | `pages/PrescriptionVerification.tsx` | Restyle to 3-column layout, severity check rows, skeleton loaders. |
| `05-dispense-wizard` | `components/ApproveConfirmModal.tsx` → new wizard | **New** 2-step wizard (verify pack → confirm/decommission). Needs backend. |
| `06-patients` | *(none — only `/patients/:id` exists)* | **New** search/list page. |
| `07-patient-profile` | `pages/PatientProfile.tsx` | Restyle (avatar header, conditions, add-condition modal). |
| `08-history` | *(closest: `pages/Documentation.tsx`)* | **New** "Dispense history" (filter/search/table). See decision #1. |
| `09-reports` | `pages/SideEffects.tsx` | Restyle + rename to "Reports" (ADR). |
| `10-settings` | *(none)* | **New** Profile / Credentials / Pharmacy / Team / Audit / Danger zone. |
| `11-counter-mobile` | `pages/Dashboard.tsx` (responsive) | Polish pass. |
| `12-counter-dark` | global | Dark mode. See decision #2. |

**Sidebar IA change:** today's nav is `Dashboard · Documentation Log ·
Side Effect Reports`. The mockups' nav is `Counter · Patients · History ·
Reports · Settings`.

---

## Open decisions (confirm before Phase 0)

1. **Where do "Documentation Log" and "Instructions" go?** The new nav
   has no "Documentation" item. Recommended: fold the Documentation/Legal
   log into **History** (or the Settings → **Audit log** section), and
   keep **Instructions** as a contextual route (launched from the Counter
   quick action and from a completed prescription), not a sidebar item.
   Confirm or tell me otherwise.
   See **Documentation → History parity checklist** under Phase 5.
2. **Dark mode (`12-counter-dark`): in scope now or later?** It roughly
   doubles the styling surface (needs a `darkMode: "class"` strategy +
   `dark:` variants everywhere). Recommended: ship light-mode parity
   first, treat dark as a fast-follow.
3. **Route paths:** recommend **keeping** existing route paths
   (`/dashboard`, `/prescription/:rxId`, …) and only changing the
   *labels* and UI — renaming `/dashboard`→`/counter` touches every
   redirect, the `d` keyboard shortcut, and several `navigate()` calls
   for no user-visible gain. Confirm you're OK keeping paths stable.
4. **Approve button color: brand-blue or keep emerald?** The design rule
   ("semantic colors are reserved for safety state only") implies
   Approve becomes `brand-600`. Green-for-go is muscle memory for
   pharmacists, though, so the change can be a small UX regression for
   experienced users. Two options:
   - **Strict design rule:** Approve = `brand-600`. Clean theory,
     short-term retraining cost.
   - **Compromise:** Approve = `brand-600` *with an emerald check icon
     prefix* — keeps the action signal recognizable while complying with
     the rule.

   Recommended: **compromise**.

I've assumed the **recommended** option for each in the prompts below;
adjust if you disagree.

---

## Foundation token changes (exact)

These are the only changes to the design foundation. The prompt in
Phase 0 applies them; shown here so you can eyeball them.

**`tailwind.config.js`** — add to `theme.extend`:
```js
boxShadow: {
  card: "0 1px 2px rgba(15, 23, 42, 0.04)",      // existing
  cardLg: "0 4px 16px rgba(15, 23, 42, 0.06)",   // existing
  modal: "0 24px 60px rgba(15, 23, 42, 0.22)",   // ADD
},
keyframes: {
  /* …existing… */
  shimmer: { "0%": { backgroundPosition: "-400px 0" }, "100%": { backgroundPosition: "400px 0" } }, // ADD
},
animation: {
  /* …existing… */
  shimmer: "shimmer 1.3s linear infinite", // ADD
},
fontFamily: { // ADD
  mono: ['ui-monospace','"SF Mono"','"JetBrains Mono"','Menlo','Consolas','monospace'],
},
```

**`src/index.css`** — add a `.mono` helper and a skeleton base, and align
the card radius:
```css
@layer components {
  /* change .card from rounded-2xl to rounded-xl to match the mockups' cards
     (the hero/modal surfaces use rounded-2xl explicitly where needed) */
  .mono { font-family: theme('fontFamily.mono'); }
  .sk { background: linear-gradient(90deg,#f1f5f9 25%,#e2e8f0 37%,#f1f5f9 63%); background-size: 800px 100%; }
}
```

**Design-system rule to enforce repo-wide:** red / amber / emerald are
reserved **strictly for safety state** (block / review / ok) and never
decorate. Concretely this means the **Approve action becomes `brand-600`
(blue), not emerald** — today `.btn-success` (emerald) is used for
"Approve Prescription", which violates the rule. The Phase 0 prompt
fixes this. (See decision #4 above for the recommended compromise.)

**Icons to add to `src/components/Icons.tsx`** (mockups use these; repo
is missing them): `BarcodeIcon`, `KeyIcon`, `RefreshIcon`, `InfoIcon`,
`ChevronDownIcon`, `ArrowLeftIcon`, and for Settings: `UserIcon`,
`BuildingIcon`, `ListIcon`, `ShieldOffIcon`. (Already present:
`PillIcon`, `ShieldIcon`, `GridIcon`, `UsersIcon`, `ClipboardIcon`,
`SettingsIcon`, `SearchIcon`, `FilterIcon`, `XIcon`, etc.)

---

## Before you run the prompts

1. **Make the mockups visible to Claude Code.** Copy the `pages/`
   folder into the repo so prompts can reference it, e.g.
   `frontend/redesign-reference/` (and add that path to `.gitignore`).
   The prompts below assume mockups live at
   `frontend/redesign-reference/NN-name.html`.
2. **Guardrails baked into every prompt** (so they're not repeated each
   time):
   - **Scope:** work only under `frontend/src`. **Do not touch `backend/`**.
   - **Data wiring:** keep every existing `lib/api.ts` call, every
     `types/index.ts` type, every react-router route, and every event
     handler / state-machine in the existing pages **verbatim**. The
     redesign is JSX + Tailwind + layout structure only. If a handler's
     shape needs to change, call that out explicitly in the prompt — never
     silently rewrite one.
   - **Mockup hygiene:** mirror the *visual layout* of the referenced
     mockup but **do not** copy its mock data, Greek placeholder strings,
     or the dev-only `StateSwitcher` component. Mockups are visual ground
     truth, not data ground truth.
   - **Mockup-vs-design-rule conflicts:** if the mockup uses a semantic
     color (red / amber / emerald) for a non-safety purpose, substitute a
     `slate-*` or `brand-*` variant and leave a one-line code comment
     explaining the substitution. Semantic colors are reserved for safety
     state (block / review / ok) and never decorate.
   - **Tokens:** use only existing Tailwind tokens. **No new hex literals.**
   - **TypeScript:** keep strict.
   - **Component extraction:** any sub-section of a page that's >80 lines
     of JSX should be extracted into its own component under
     `frontend/src/components/`. Don't leave 600-line pages.
   - **Branching + PR:** each phase ships as its own PR — branch
     `feat/redesign-phase-<N>-<slug>` off `main`, commit incrementally,
     open the PR at the end with the prompt body as the description.

### Per-phase template (every Phase prompt below assumes this scaffold)

Each Phase prompt below carries a small **Inputs** block before the
prompt body that fills in:

- **Branch** — explicit branch name to create first.
- **First read** — the files Claude should load *before* writing anything.
  Without this Claude burns a turn on discovery; with it the first
  response is implementation.
- **Stubs** — if the phase needs `lib/api.ts` stubs for endpoints that
  don't exist yet, the **exact signature and rejection shape** is
  specified — not just "stub it." (Otherwise the UI's error-handling
  is incompatible with whatever Claude picks.)
- **Preservation** — anything in the touched files that must NOT change
  (handlers, state machines, types, route definitions). The default
  guardrail above says "preserve everything"; this section spells out
  the specific contract for the touched files.

And every phase ends with the same **Finalize** block (don't repeat it
in each prompt — it applies to all):

```
Finalize (run after the phase's work is done):
1. `cd frontend && npm run typecheck && npm run lint && npm run format`
   — fix anything that fails.
2. `docker compose exec -T backend python -m pytest`
   — backend should be untouched, so this must stay green. If it fails,
   something in this phase regressed the backend (shouldn't happen) and
   needs reverting.
3. Write the phase's Playwright smoke test per the matrix above,
   under `frontend/tests/phase-<N>-<slug>.spec.ts`. Local-only for now;
   don't add to CI.
4. `git add -A && git commit -m "feat(redesign): Phase <N> — <name>"`
   `git push -u origin feat/redesign-phase-<N>-<slug>`
5. `gh pr create --base main --title "feat(redesign): Phase <N> — <name>" --body "<paste the Inputs + prompt body for traceability>"`
```

### PR / branch strategy

- **One PR per phase minimum.** Phase 0 ships alone (foundational, every
  later phase rebases off it). Phase 1 (Counter) ships alone — big
  visual surface, deserves its own review window.
- **Phase 5 should split into 3 PRs** (Reports restyle, History new,
  Settings new). They touch disjoint files and review better separately.
- **Phases 3–4 can be parallel branches** once Phase 2 is in.
- For each phase: branch → run the prompt → review → PR → land →
  next phase rebases from main. Don't stack branches deeper than two
  unless you have to.

### Per-phase Playwright smoke

There's no frontend test suite today, but Playwright is already proven
working in this repo (`frontend/node_modules/playwright` was installed
during the redesign-discovery probes). Add **one happy-path Playwright
test per phase** to lock in behavior and catch cross-phase regressions
cheaply. Suggested coverage:

| Phase | Smoke test |
| --- | --- |
| 1 — Counter | Login → land on Counter → scanner input is autofocused → submit barcode → navigates to `/prescription/:barcode` |
| 2 — Review | Visit `/prescription/RX2024-005` in mock → three columns render → Approve disabled when a `block` check is present |
| 3 — Dispense wizard | Open wizard from Review → step 1 visible → step 2 reachable after stubbed verify → success screen returns to Counter |
| 4 — Patients | `/patients` empty state → type AMKA → result row → click → `/patients/:amka` profile renders |
| 5 — History/Settings | `/history` table renders + filters work; `/settings` sub-nav switches |

Drop these in `frontend/tests/` (new folder; matches existing test
locations). They don't go in CI yet (CI is ruff + eslint only) — they're
for the engineer running each phase to verify locally.

### Live-mode awareness during the redesign

The redesign happens entirely in mock mode (`PHARMAPI_MOCK=true`). Spot-
check **once per phase** that the new screens still render against live
mode (`PHARMAPI_MOCK=false` after `docker compose up --force-recreate
backend`). For most phases this just means "scanner still submits and
returns the right shape"; for Phase 2 (Review) the live shape is
different because there's no HL7 parser yet — that's expected and is
tracked under **Follow-ups** below.

---

## Phase 0 — Foundation

**Inputs**
- **Branch:** `feat/redesign-phase-0-foundation`
- **First read:** `frontend/tailwind.config.js`, `frontend/src/index.css`,
  `frontend/src/components/Icons.tsx`, `frontend/src/components/Sidebar.tsx`,
  `frontend/src/pages/PrescriptionVerification.tsx` (for the
  `.btn-success` Approve usage), `frontend/src/lib/auth.tsx` (for the
  `useAuth` shape the sidebar uses), and
  `frontend/redesign-reference/00-design-system.html`.
- **Stubs:** none.
- **Preservation:** the existing user/sign-out footer wiring in
  `Sidebar.tsx` (the `useAuth` hook call and its consumer). Don't
  refactor the Approve button's *handler* — only its visual styling.
- **Routes:** **do not** add new routes in this phase. Later phases add
  `/patients`, `/history`, `/settings`.

> **Prompt:**
> In `frontend/`, apply the PharmAssist design-system foundation.
> Reference `frontend/redesign-reference/00-design-system.html`.
> 1. In `tailwind.config.js` add to `theme.extend`:
>    `boxShadow.modal: "0 24px 60px rgba(15,23,42,0.22)"`; a `shimmer`
>    keyframe (`0%{background-position:-400px 0} 100%{background-position:400px 0}`)
>    and `animation.shimmer: "shimmer 1.3s linear infinite"`; and
>    `fontFamily.mono` = `['ui-monospace','"SF Mono"','"JetBrains Mono"','Menlo','Consolas','monospace']`.
> 2. In `src/index.css` add a `.mono { font-family: theme('fontFamily.mono'); }`
>    helper and a `.sk` skeleton-gradient class (see the `.sk` rule in
>    the mockup). Change the `.card` component from `rounded-2xl` to
>    `rounded-xl` to match the mockups.
> 3. In `src/components/Icons.tsx` add these icons in the same style as
>    the existing ones (16px viewBox, `currentColor` stroke):
>    `BarcodeIcon, KeyIcon, RefreshIcon, InfoIcon, ChevronDownIcon,
>    ArrowLeftIcon, UserIcon, BuildingIcon, ListIcon, ShieldOffIcon`.
>    Copy the exact SVG paths from the mockups in
>    `frontend/redesign-reference/`.
> 4. Enforce the semantic-color rule: replace the emerald "Approve"
>    button styling with `brand-600`, paired with an emerald check icon
>    prefix to keep the action signal recognizable (per decision #4).
>    Update `.btn-success` usages for the approve action in
>    `pages/PrescriptionVerification.tsx`. Leave emerald only for "ok"
>    safety states.
> 5. Update `src/components/Sidebar.tsx` to the mockup: width `w-60`,
>    `PillIcon` logo, and nav items `Counter (/dashboard), Patients
>    (/patients), History (/history), Reports (/side-effects), Settings
>    (/settings)` using `GridIcon, UsersIcon, ClipboardIcon,
>    AlertTriangleIcon, SettingsIcon`. Keep the existing user/sign-out
>    footer wiring (`useAuth`).
> Then run `npm run typecheck && npm run lint && npm run format` and fix
> any issues. Do not add new routes yet (later phases add the
> `/patients` list, `/history`, `/settings` pages).

## Phase 0.5 — Live-mode UI awareness

**Inputs**
- **Branch:** `feat/redesign-phase-0-5-live-mode-awareness`
- **First read:** `frontend/vite.config.ts`, `frontend/.env.example` (if
  it exists; create if not), `frontend/src/components/Sidebar.tsx`.
- **Stubs:** none — this phase is plumbing only.
- **Preservation:** Sidebar's footer (auth/sign-out) untouched; only add
  the `DevModeBadge` above it.

> **Why this phase exists:** the production-readiness doc calls out that
> some demo affordances should be hidden when `PHARMAPI_MOCK=false`
> (notably the seeded mock prescriptions in the queue and the "Generate
> Instructions" quick action which assumes mock data). Without this, the
> new Counter looks the same in both modes — which is misleading once
> live mode is real.
>
> **Prompt:**
> In `frontend/`:
> 1. Add a `frontend/src/lib/env.ts` exporting `useIsMockMode()` and
>    `IS_MOCK_MODE` constants. Source from a build-time Vite env var
>    `VITE_PHARMAPI_MOCK` (defaults to `true` so existing dev workflows
>    keep working). Document the var in `frontend/.env.example`.
> 2. In `vite.config.ts`, wire the env var so the SPA bundle knows
>    whether it's pointed at a live or mock backend at build time.
>    (Backend's `PHARMAPI_MOCK` and frontend's `VITE_PHARMAPI_MOCK` are
>    separate concerns; keep them aligned via the compose file.)
> 3. Add a tiny `<DevModeBadge>` component (subtle slate chip in the
>    sidebar footer) that reads "Mock data" when `IS_MOCK_MODE` is
>    true. Hides entirely in live mode.
> Do not yet branch any specific UI on `IS_MOCK_MODE` — later phases
> reference it (e.g., Phase 1 hides the Instructions quick action in
> live mode). This phase only sets up the plumbing.
> Then run `npm run typecheck && npm run lint && npm run format`.

## Phase 1 — Counter (Dashboard)

**Inputs**
- **Branch:** `feat/redesign-phase-1-counter`
- **First read:** `frontend/src/pages/Dashboard.tsx` (current), the
  keyboard library (search: `find frontend/src/lib -name 'keyboard*'`;
  also check `frontend/src/hooks/` and `frontend/src/pages/PrescriptionVerification.tsx`
  for the `c`/`f` shortcut wiring to confirm the API), `frontend/src/components/SafetyAlertsPanel.tsx`,
  `frontend/src/lib/api.ts` (functions `listPrescriptions`, `getActiveAlerts`,
  and the existing `ApiError` class), `frontend/src/types/index.ts` for
  `QueueItem`, `ActiveAlert`, `CheckStatus`, `frontend/src/lib/auth.tsx`
  for `useAuth`, `frontend/src/lib/env.ts` (from Phase 0.5) for
  `IS_MOCK_MODE`, and `frontend/redesign-reference/03-counter.html`.
- **Stubs:**
  - `paperlessLookup(amka: string, pin: string): Promise<never>` in
    `lib/api.ts`. Always rejects with
    `new ApiError(501, 'Paperless lookup not yet implemented')`. UI shows
    that message as a small disabled-button tooltip.
- **Preservation:** all existing imports/types that aren't being deleted
  must remain pointing at the same modules. The `c`/`f` shortcuts are
  registered elsewhere and untouched.
- **Dead code to delete (don't leave orphan imports):** the
  4-stat-card grid and its derived state — `criticalCount`, the
  `alerts` state in `Dashboard.tsx`, the `getActiveAlerts` *page-level*
  import (the Safety panel still uses it internally), `STATUS_CHIP` /
  `STATUS_LABEL` if the new layout doesn't reuse them. Run `grep` after
  to verify no unused imports remain.

> **Pre-flight (do this before running the prompt):**
> Check what `frontend/src/lib/keyboard.ts` (or wherever the keyboard
> system lives — earlier `c` / `f` shortcuts in
> `PrescriptionVerification.tsx` imply it exists) exposes. The prompt
> below assumes `register(shortcut, handler)` or similar — if the API
> differs, adjust the prompt to match. Two-minute audit; saves a
> rework loop.
>
> **Acknowledge dead code from PRs #82–#84:** the Counter prompt
> removes the 4-stat-card grid that PRs #82, #83, and #84 just
> stabilized (Critical Alerts derivation, semantic-color fix, etc.).
> This is intentional — the stat cards don't map to live mode — but it
> means the `criticalCount`, `alerts` state, `getActiveAlerts` import
> at the page level, and the `STATUS_CHIP`/`STATUS_LABEL` re-exports
> become dead in `Dashboard.tsx`. Delete them as part of the phase;
> don't leave orphan imports for the next refactor to trip over.
>
> **Prompt:**
> Redesign `frontend/src/pages/Dashboard.tsx` to match
> `frontend/redesign-reference/03-counter.html`. Keep the route at
> `/dashboard` and keep all existing data wiring (`listPrescriptions`,
> `getActiveAlerts`).
> Build these sections: (a) a page header "Counter" with today's date +
> pharmacy name (from `useAuth`); (b) a **"Start a dispense"** hero
> card with two pill-tabs — **Scan barcode** and **Paperless (AMKA +
> PIN)**. The barcode form should, on submit, navigate to
> `/prescription/{barcode}` (reuse the existing `getPrescription`
> flow). (c) an **"In progress"** list and a **"Today"** list built
> from the prescription queue (map `QueueItem.status`
> PENDING→in-progress, COMPLETED→today; use the existing `STATUS_CHIP`
> semantics); (d) a right rail reusing the existing `SafetyAlertsPanel`
> titled "Active safety alerts"; (e) the `⌘K` hint to focus the
> scanner — wire it through the existing keyboard system
> (`lib/keyboard`) and a ref on the scanner input.
>
> **Live-mode awareness:** wire the "Generate Instructions" quick
> action (header secondary link to `/instructions`) behind
> `IS_MOCK_MODE` — hide it in live mode since `/instructions`
> currently assumes mock prescriptions.
>
> **Instructions entry points:** make `/instructions` reachable from
> (a) a small secondary link in the Counter header (mock-only, see
> above), and (b) post-dispense success screen in the wizard (Phase 3).
> Don't orphan it just because the sidebar item went away.
>
> **G14 / session banner:** the mockup shows a "Session refresh
> required" amber banner at the top. The backend already auto-retries
> G14 (PR #72), so this banner should only appear if a 401 returns
> *after* a previously-OK session. Wire it conservatively: only show
> when `getActiveAlerts` or `listPrescriptions` returns a 401. Don't
> show it as a permanent fixture.
>
> For the **Paperless (AMKA + PIN)** tab: there is no backend endpoint
> yet. Render the form fully but disable submit with a small "Coming
> soon" note, and add a stub `paperlessLookup` in `lib/api.ts` marked
> `// TODO: backend endpoint /prescriptions/paperless not implemented`.
> Do not invent backend calls.
>
> Replace the old 4-stat-card grid and "Quick Actions"/"Generate
> Instructions" block — keep a link to `/instructions` as described
> above. **Delete the now-dead `criticalCount` / `alerts` state and
> their imports** — don't leave them as orphans.
> Then run the **Finalize** block (see "Per-phase template" at the top of this doc): frontend checks, backend pytest, Playwright smoke, branch + commit + PR.

## Phase 2 — Review (Prescription Verification)

**Inputs**
- **Branch:** `feat/redesign-phase-2-review`
- **First read:** `frontend/src/pages/PrescriptionVerification.tsx`
  (current — long file, read the whole thing), the three modals/drawer
  it uses (`frontend/src/components/ApproveConfirmModal.tsx`,
  `FlagDiscrepancyModal.tsx`, `ContactPrescriberDrawer.tsx`), the
  `SafetyChecksPanel` it composes, `frontend/src/types/index.ts` for
  `SafetyCheck`, `Prescription`, `PatientCondition`,
  `frontend/src/lib/api.ts` for `getPrescription`, `approvePrescription`,
  `getPatientConditions`, and `frontend/redesign-reference/04-review.html`.
- **Stubs:** none. All data flows are already wired.
- **Preservation (verbatim):** every event handler
  (`onClickApprove`, `onConfirmApprove`, the flag and contact handlers),
  the blocker logic (`blockers = (rx.safetyChecks ?? []).filter(c => c.status === 'block')`),
  the `c` / `f` keyboard shortcut registration, the modal/drawer open
  state machines, every `useEffect`, every API call. Restyle = JSX +
  Tailwind + layout only. If you find yourself editing logic outside
  the render tree, stop and ask.

> **Prompt:**
> Restyle `frontend/src/pages/PrescriptionVerification.tsx` to match
> `frontend/redesign-reference/04-review.html`, keeping the route, all
> data fetching, the three modals/drawer (`ApproveConfirmModal`,
> `FlagDiscrepancyModal`, `ContactPrescriberDrawer`), and the `c`/`f`
> keyboard shortcuts.
> Layout: a back-to-counter link, a header with the barcode in `.mono`
> and the action buttons (Contact prescriber, Flag discrepancy,
> **Approve & dispense** as `brand-600` with the emerald-check prefix,
> disabled with a tooltip when any safety check is `block`). Below, a
> **three-column grid** (`lg:grid-cols-[1.35fr_1fr_1.05fr]`):
> Patient / Medication / Automated Safety Checks. Use the existing
> `SafetyChecksPanel` content but render each check as a severity row
> (block=red+`pulse-red-border`, review=amber, ok=emerald) with an
> expandable "Details" disclosure for non-ok rows.
> Add **skeleton loading** using the `.sk animate-shimmer` classes
> while `loading` is true (mirror the mockup's skeleton cards).
> Preserve the "Resolve all critical safety alerts before approving"
> blocked state. Then run the **Finalize** block (see "Per-phase template" at the top of this doc): frontend checks, backend pytest, Playwright smoke, branch + commit + PR.

## Phase 3 — Dispense wizard

**Inputs**
- **Branch:** `feat/redesign-phase-3-dispense-wizard`
- **First read:** `frontend/src/components/ApproveConfirmModal.tsx`
  (the thing being replaced), `frontend/src/pages/PrescriptionVerification.tsx`
  (to see how the modal is currently mounted),
  `frontend/src/lib/api.ts` for `approvePrescription` + the existing
  `ApiError` shape, `frontend/src/lib/env.ts` for `IS_MOCK_MODE`,
  and `frontend/redesign-reference/05-dispense-wizard.html`.
- **Stubs (add to `lib/api.ts` with TODO comments):**
  - `verifyPack(packCode: string, scheme: 'GS1' | 'PPN', batch?: string, expiry?: string): Promise<never>` — always rejects with `new ApiError(501, 'HMVS pack verification not yet implemented')`.
  - `decommissionPack(packCode: string): Promise<never>` — always rejects with `new ApiError(501, 'HMVS pack decommission not yet implemented')`.
- **Preservation:** the `approvePrescription(rxId)` call signature and
  the existing success → `toast` → `navigate('/dashboard')` flow.
- **State machine (explicit — don't invent these transitions):**
  ```
  step1: idle → verifying → (success → goto step2) | (failed → idle with retry)
                          → skip-manual → step2 (with a banner that pack-verify was skipped)
  step2: idle → submitting → (success → success-view) | (failed → idle with retry)
  success-view: terminal — single CTA "Back to counter" closes the modal
                + optional secondary CTA "Generate counseling instructions"
                (mock-mode-only via IS_MOCK_MODE)
  ```
  Any failed verify in step1 is **not** a hard block; the user can click
  "Skip — manual entry" to proceed to step2 with a clear notice.
  Cancel / Esc / scrim-click closes the modal at any step *except* during
  an in-flight submit (block close until the request resolves).
- **Backend-gap behavior:** because verify + decommission both reject
  today, the practical flow in mock mode is: step1 always shows the
  failed state on submit → user clicks "Skip — manual entry" → step2
  → `approvePrescription` succeeds → success view. Make sure that
  user journey is smooth and the "skipped pack verification" banner in
  step2 is clear, not alarming.

> **Prompt:**
> Create a new `frontend/src/components/DispenseWizard.tsx` matching
> `frontend/redesign-reference/05-dispense-wizard.html`: a 2-step
> modal — **Step 1 "Verify medicine pack"** (scan/enter pack barcode;
> states idle/verifying/failed) and **Step 2 "Confirm dispense"**
> (decommission the pack; states idle/submitting/success/failure), plus
> a "Dispensed successfully" success view. Use `shadow-modal`,
> `rounded-2xl`, the slate-900/40 scrim.
> Replace `ApproveConfirmModal` usage in
> `PrescriptionVerification.tsx` with this wizard on the Approve &
> dispense action. **Backend note:** pack verify + decommission
> endpoints do not exist. Wire Step 2's final confirm to the existing
> `approvePrescription(rxId)`; for the pack-verify and decommission
> calls add stubs in `lib/api.ts` (`verifyPack`, `decommissionPack`)
> marked TODO and have the UI surface a clear "pack verification not
> yet available — proceeding on approval only" state rather than
> faking success.
> **Success screen wiring:** include a "Generate counseling
> instructions" CTA on the success view, behind `IS_MOCK_MODE` for now
> (live HL7 dispense + counseling generation lives in a later track).
> Then run the **Finalize** block (see "Per-phase template" at the top of this doc): frontend checks, backend pytest, Playwright smoke, branch + commit + PR.

## Phase 4 — Patients (list + profile)

**Inputs**
- **Branch:** `feat/redesign-phase-4-patients`
- **First read:** `frontend/src/App.tsx` (to see where `/patients/:id`
  is registered), `frontend/src/pages/PatientProfile.tsx` (current),
  `frontend/src/lib/api.ts` (`getPatient`, `getPatientConditions`,
  `getPatientPrescriptions`, `getPatientSideEffects`),
  `frontend/src/types/index.ts` for `Patient` / `PatientCondition`,
  `frontend/vite.config.ts` to confirm the `/patients` SPA-proxy
  bypass exists, and the two mockups
  `frontend/redesign-reference/06-patients.html` +
  `07-patient-profile.html`.
- **Stubs (add to `lib/api.ts`):**
  - `searchPatients(query: string): Promise<never>` — always rejects
    with `new ApiError(501, 'Patient search not yet implemented')`.
- **Preservation (verbatim):** every API call signature in
  `PatientProfile.tsx`; the existing "Add condition" modal logic
  (restyle the JSX, don't replace the component); the `/patients/:id`
  route registration (don't accidentally remove it when adding the
  index route above it).
- **Critical wiring detail:** **do not** iterate `getPatient` over a
  guessed list of AMKAs to fake a name search. For non-AMKA inputs,
  surface the "search not yet available" empty state instead. (The
  existing prompt body already specifies the dual-path; this note
  exists to make sure Claude doesn't get clever.)

> **Prompt:**
> (a) Create a new page `frontend/src/pages/Patients.tsx` matching
> `frontend/redesign-reference/06-patients.html`: a "Patients" header,
> a search box (by AMKA / EKAA / name), and a results list; states
> empty / searching / results / no-matches / error. Wire results to
> the existing patient APIs where possible (`getPatient`); if there's
> no search endpoint, add a TODO stub `searchPatients` in `lib/api.ts`
> and drive the UI from it. For AMKA-shaped inputs (11 digits)
> short-circuit to `getPatient(amka)` directly so the page is useful
> *today*. Each result links to `/patients/{amka}`.
> (b) Register the route `/patients` (index) in `App.tsx` inside the
> `AppShell` tree, above the existing `/patients/:id`.
> (c) Restyle `frontend/src/pages/PatientProfile.tsx` to match
> `07-patient-profile.html`: avatar with initials, name + AMKA header,
> conditions/exceptions cards, and the "Add condition" modal (keep
> existing `getPatient`, `getPatientConditions`,
> `getPatientPrescriptions`, `getPatientSideEffects` wiring).
> Note: `/patients` already has a Vite `spaProxy` bypass, so the new
> index route needs no proxy change. Then run typecheck/lint/format
> and fix everything.

## Phase 5 — History, Reports, Settings

**Inputs (apply per-sub-PR; the three sub-phases are independent)**

**5a — Reports**
- **Branch:** `feat/redesign-phase-5a-reports`
- **First read:** `frontend/src/pages/SideEffects.tsx` (current),
  `frontend/src/lib/api.ts` (`listSideEffects`, `flagSideEffect`),
  `frontend/src/types/index.ts` for `SideEffect`,
  `frontend/redesign-reference/09-reports.html`.
- **Stubs:** none.
- **Preservation:** every API call signature; the route remains
  `/side-effects`; the page filename stays `SideEffects.tsx` (only
  the heading text and styling change).

**5b — History**
- **Branch:** `feat/redesign-phase-5b-history`
- **First read:** `frontend/src/pages/Documentation.tsx` (current — to
  see what's being folded in), `frontend/src/App.tsx` (to add the new
  route + the redirect), `frontend/src/components/Sidebar.tsx` (to
  remove the old "Documentation Log" item if still present),
  `frontend/src/lib/api.ts` (`listDocumentation`, `exportDocumentation`,
  any per-row export call), `frontend/src/types/index.ts` for
  `DocumentationLog`, and `frontend/redesign-reference/08-history.html`.
- **Stubs:** none — wire the History page entirely to the existing
  documentation endpoints.
- **Preservation (parity checklist — see the section above this phase):**
  every filter (`q`, `method`, `limit`, `offset`); both export endpoints
  (`GET /documentation/export` and per-row `GET /documentation/{id}/export`);
  the `<Navigate to="/history" replace />` redirect from `/documentation`
  must work for old bookmarks.

**5c — Settings**
- **Branch:** `feat/redesign-phase-5c-settings`
- **First read:** `frontend/src/App.tsx` (to add the new route),
  `frontend/src/lib/api.ts` for `me` / current-user endpoints,
  `frontend/src/lib/auth.tsx` for `useAuth`,
  `frontend/redesign-reference/10-settings.html`.
- **Stubs (add to `lib/api.ts`, all reject with 501):**
  - `updatePharmapiPassword(currentPw: string, newPw: string): Promise<never>`
    — `new ApiError(501, 'Credential rotation not yet implemented')`.
  - `inviteTeamMember(email: string, role: 'pharmacist' | 'admin'): Promise<never>`
    — `new ApiError(501, 'Team management not yet implemented')`.
  - `removeTeamMember(pharmacistId: string): Promise<never>` — same.
  - `getAuditLog(page: number, pageSize: number): Promise<never>` —
    `new ApiError(501, 'Audit log read not yet implemented')`.
  - `signOutEverywhere(): Promise<never>` —
    `new ApiError(501, 'Sign-out-everywhere not yet implemented')`.
- **Preservation:** the `useAuth` hook usage and any existing
  read-only "me" endpoint calls — wire them into Profile.

> **PR strategy:** split into three PRs (Reports / History / Settings).
> They touch disjoint files and review better separately.
>
> ### Documentation → History parity checklist
>
> Per decision #1, the existing Documentation/Legal log folds into
> the new History page. To avoid losing functionality, the History
> implementation MUST preserve:
> - the `q` (free-text search) filter
> - the `method` filter (PRINT / DIGITAL / BOTH / ALL)
> - `limit` / `offset` pagination
> - the bulk `GET /documentation/export` CSV endpoint
> - the per-row `GET /documentation/{id}/export` action
> - any existing audit-log read paths
>
> Also: add a **301-style redirect** from `/documentation` →
> `/history` (a tiny `<Navigate to="/history" replace />` route) so
> old bookmarks and in-app links don't 404. Grep the repo for
> `/documentation` references before merging — there's at least one
> sidebar link, possibly more in copy.
>
> ### Prompt:
> (a) **Reports** — restyle `frontend/src/pages/SideEffects.tsx` to
> match `09-reports.html`; relabel the page heading to "ADR Reports"
> (Adverse-Drug-Reaction reporting). Keep `listSideEffects` /
> `flagSideEffect` wiring and the route `/side-effects`. *("Reports"
> alone is ambiguous — could read as financial or regulatory; "ADR
> Reports" preserves the existing meaning.)*
> (b) **History** — create `frontend/src/pages/History.tsx` matching
> `08-history.html` ("Dispense history": stats row, filters,
> searchable table). Per decision #1, fold the existing
> Documentation/Legal log data into it (reuse `listDocumentation` /
> `exportDocumentation`) and satisfy the **parity checklist** above.
> Add route `/history` in `App.tsx`, plus a `<Navigate to="/history">`
> redirect from `/documentation`.
> (c) **Settings** — create `frontend/src/pages/Settings.tsx` matching
> `10-settings.html` with sections Profile / ΗΔΥΚΑ credentials /
> Pharmacy / Team (admin-only) / Audit log / Danger zone, plus the
> "Update ΗΔΥΚΑ password" modal. Wire what exists (`me`,
> admin/credentials endpoints); stub the rest in `lib/api.ts` with
> TODOs. Add route `/settings` in `App.tsx`.
> **Routing note:** `/history` and `/settings` are not backend API
> prefixes, so Vite's SPA fallback serves them — no `vite.config.ts`
> change needed. Only add a `spaProxy` entry if you later create
> backend routes at those exact paths. Then run typecheck/lint/format
> and fix everything.

## Phase 6 — Polish: mobile + (optional) dark mode

**Inputs**
- **Branch (mobile):** `feat/redesign-phase-6-mobile`
- **Branch (dark, if in scope):** `feat/redesign-phase-6b-dark-mode`
- **First read (mobile):** the now-landed `Sidebar.tsx`, `Dashboard.tsx`
  (Counter), `PrescriptionVerification.tsx` (Review), `Patients.tsx`,
  the design-system mockup `00-design-system.html`,
  `frontend/redesign-reference/11-counter-mobile.html`.
- **First read (dark, if in scope):** `frontend/tailwind.config.js`,
  `frontend/src/index.css`, the same page files as above, and
  `frontend/redesign-reference/12-counter-dark.html`.
- **Stubs:** none.
- **Preservation:** the mobile reflow must not change any behavior —
  same handlers, same data, same routing. Only viewport-class additions
  (`md:` etc.) and rearrangement.

> **Prompt (mobile):**
> Make the Counter responsive per `11-counter-mobile.html`: collapse
> the sidebar into a top bar / drawer under `md`, stack the hero and
> rail, and verify the Review and Patients pages reflow cleanly on a
> 380px viewport. Touch targets ≥ 40px. Then run the **Finalize** block at the top of this doc.
>
> **Prompt (dark mode — only if decision #2 = now):**
> Add `darkMode: "class"` to `tailwind.config.js`, a theme toggle in
> the sidebar footer, and `dark:` variants across the shared
> components and Counter to match `12-counter-dark.html`. Keep
> semantic safety colors legible in both themes. Then run the **Finalize** block at the top of this doc.

---

## Verification (do this after each phase)

From `frontend/`:

```
npm run typecheck
npm run lint
npm run format:check
npm run build
```

There is no frontend test suite in CI, so also:
- Click through the affected screen in `npm run dev` (login at
  `/login`; the repo's seeded credentials are in `README.md`).
- Run the **Phase's Playwright smoke test** locally (see the table in
  "Before you run the prompts").
- Spot-check the page in live mode (`PHARMAPI_MOCK=false`) — at
  minimum, log in and confirm the page renders without errors against
  the real backend.

The pre-commit hook runs ruff + prettier; CI runs lint + format check —
keep both green.

---

## What needs the backend (track separately)

- `POST /prescriptions/paperless` — AMKA + PIN lookup (Counter
  paperless tab).
- Pack **verify** + **decommission** endpoints (Dispense wizard, EU
  FMD via HMVS — see [`going-real-production-readiness.md`](./going-real-production-readiness.md)).
- Patient **search** endpoint (Patients list), if not already covered
  by `/patients`.
- Any Settings write endpoints (credentials rotation, team management,
  audit log) not already present.

Until these land, the prompts above keep the UI present but
stubbed/disabled rather than faking calls — consistent with the repo's
mock-vs-live bridge pattern in `CLAUDE.md`.

## Follow-ups (post-redesign tickets)

These aren't part of the redesign itself but should be queued so the
redesign actually pays off once they're done.

- **Wire Counter scan → HL7 backend route.** The redesign uses the
  existing `getPrescription(rxId)` which works in mock and today's
  live JSON path. The bigger live unblock is the HL7-CDA `/get/{barcode}`
  endpoint (see `going-real-live-mode-ux.md`). Once
  `pharmapi_get_prescription_hl7` lands, swap the scan handler to
  call the new HL7-aware route. Small swap; do it as its own PR.
- **T6 full `drug_catalog` sync.** Without it, the new Counter renders
  scans against real prescriptions but ATC-keyed safety alerts won't
  fire (EOF codes won't resolve to ATCs). Sequence T6 close to the
  redesign so live alerts are meaningful when the dashboard launches.
- **Frontend Playwright suite in CI.** Per-phase smokes give us
  coverage now; promote them to a CI job once the redesign settles.
  Needs a Postgres service in CI plus a mock-mode bootstrap (the same
  pattern `tests/test_endpoints_integration.py` uses on the backend).
- **Approve button UX check** (per decision #4). Once a friendly
  pharmacist has used the brand-blue Approve in anger, decide whether
  the emerald-check-prefix compromise is enough or whether the rule
  needs a carve-out for primary "go" actions.

---

## Related docs

- [`going-real-live-mode-ux.md`](./going-real-live-mode-ux.md) — the
  architectural realization that justifies the new IA.
- [`going-real-production-readiness.md`](./going-real-production-readiness.md) —
  what the redesign does *not* cover (FMD/HMVS, secrets, observability,
  regulatory paperwork).
- [`claude-design-prompts.md`](./claude-design-prompts.md) — upstream
  claude.ai design prompts that generated the mockups this plan
  implements.
