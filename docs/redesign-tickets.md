# Redesign Ticket Breakdown — 2 Engineers

> Companion to [`frontend-redesign-plan.md`](./frontend-redesign-plan.md).
> That doc has the prompts. This doc has the **ticket split** (who does
> what, in what order, with what dependencies). Each ticket below
> includes its own paste-ready Claude Code prompt assembled from the
> plan's Inputs blocks + the shared Finalize scaffold.

## Engineer assignments at a glance

| Ticket | Title | Owner | Branch | Depends on | Effort |
| --- | --- | --- | --- | --- | --- |
| **FR-0** | Foundation (tokens, icons, Sidebar, Approve color) | **A** | `feat/redesign-phase-0-foundation` | — | ½d |
| **FR-0.5** | Live-mode UI awareness plumbing | **B** | `feat/redesign-phase-0-5-live-mode-awareness` | FR-0 | ¼d |
| **FR-1** | Counter (scan hero + in-progress + today + safety rail) | **A** | `feat/redesign-phase-1-counter` | FR-0, FR-0.5 | 1d |
| **FR-2** | Review (3-column verification + skeleton loaders) | **B** | `feat/redesign-phase-2-review` | FR-0 | 1d |
| **FR-3** | Dispense wizard (2-step modal + stubs) | **A** | `feat/redesign-phase-3-dispense-wizard` | FR-2 | 1–2d |
| **FR-4** | Patients (list + profile restyle) | **B** | `feat/redesign-phase-4-patients` | FR-0 | 1–1.5d |
| **FR-5a** | Reports restyle (ADR) | **B** | `feat/redesign-phase-5a-reports` | FR-0 | ½d |
| **FR-5b** | History (new, folds Documentation in) | **B** | `feat/redesign-phase-5b-history` | FR-0 | 1d |
| **FR-5c** | Settings (new) | **A** | `feat/redesign-phase-5c-settings` | FR-0 | 1–1.5d |
| **FR-6** | Polish — mobile (dark optional) | **A** | `feat/redesign-phase-6-mobile` | all above | ½–1d |

**Loaded effort:** Eng A ≈ 4.5–6.5d (FR-0, FR-1, FR-3, FR-5c, FR-6).
Eng B ≈ 3.75–5d (FR-0.5, FR-2, FR-4, FR-5a, FR-5b). Close to balanced;
A carries the wizard which is the largest single ticket, B carries the
broader spread.

## Dependency graph

```
                 ┌─────── FR-0 (Foundation) ───────┐
                 │                                  │
                 ▼                                  │
            FR-0.5 (Live-mode)                      │
                 │                                  │
                 ├─────────────────┐                │
                 ▼                 │                │
        FR-1 (Counter)             │   ┌──── FR-2 (Review) ──── FR-3 (Wizard)
                                   │   │
                                   │   ├──── FR-4 (Patients)
                                   │   ├──── FR-5a (Reports)
                                   │   ├──── FR-5b (History)
                                   │   └──── FR-5c (Settings)
                                   │
                                   ▼
                              FR-6 (Polish — needs all)
```

Key adjacencies that matter:
- **FR-0 blocks everything** — must merge first.
- **FR-0.5 blocks FR-1 and FR-3** (both consume `IS_MOCK_MODE`).
- **FR-3 must follow FR-2** — both touch `PrescriptionVerification.tsx`.
  Run sequentially on the same engineer (A) to avoid merge conflicts.
- **FR-2, FR-4, FR-5a, FR-5b, FR-5c** touch disjoint files and can be
  parallelized freely.

## Sprint sequencing

A practical 4-wave timeline assuming the two engineers can each handle
one ticket at a time:

```
Day 1                  Day 2–3                Day 4–6                Day 7
─────────────────────────────────────────────────────────────────────────
Eng A:  FR-0          → FR-1                → FR-3                → FR-5c → FR-6
Eng B:           FR-0.5 → FR-2              → FR-4 → FR-5a → FR-5b
─────────────────────────────────────────────────────────────────────────
```

(Total elapsed: ~7 working days for both engineers; total engineer-days
~9–11 depending on wizard / Settings depth.)

## How to use this doc

1. Pick your ticket from the table above.
2. Open the matching section below; it has the full **Inputs** block
   (branch, files to read first, stubs, preservation) and a
   **Prompt-body pointer** to the corresponding Phase in
   [`frontend-redesign-plan.md`](./frontend-redesign-plan.md).
3. Paste the full prompt into a fresh `claude` session from the repo
   root. Each ticket = one Claude session = one PR.
4. After Claude finishes, run the **shared Finalize** block (also in
   the plan doc) — frontend checks, backend pytest, Playwright smoke,
   branch + commit + PR.
5. Land the PR, then move to the next eligible ticket per the
   dependency graph.

If you change the prompt body, do it in the plan doc (the single source
of truth) and cross-link from here — don't drift the prompts.

---

## FR-0 — Foundation

- **Owner:** Eng A
- **Branch:** `feat/redesign-phase-0-foundation`
- **Depends on:** —
- **Effort:** ½d

**Acceptance criteria**

- New Tailwind tokens (`shadow-modal`, `shimmer` keyframe + animation,
  `fontFamily.mono`) live in `tailwind.config.js`.
- `.mono` and `.sk` helpers added to `src/index.css`; `.card` is
  `rounded-xl`.
- All 10 new icons exist in `Icons.tsx` (`BarcodeIcon`, `KeyIcon`,
  `RefreshIcon`, `InfoIcon`, `ChevronDownIcon`, `ArrowLeftIcon`,
  `UserIcon`, `BuildingIcon`, `ListIcon`, `ShieldOffIcon`).
- Approve button in `PrescriptionVerification.tsx` is `brand-600`
  (with optional emerald check icon prefix per the doc's open
  decision #4).
- Sidebar matches the mockup: `w-60`, `PillIcon` logo, nav items
  Counter / Patients / History / Reports / Settings; existing
  `useAuth` footer wiring preserved.
- No new routes added.
- `npm run typecheck && npm run lint && npm run format:check` pass;
  `pytest` still green.

**Prompt to paste**

> See [Phase 0 in `frontend-redesign-plan.md`](./frontend-redesign-plan.md#phase-0--foundation).
> Use the **Inputs** block and the **Prompt** body from that section.
> Conclude with the shared **Finalize** block at the top of the plan doc.

---

## FR-0.5 — Live-mode UI awareness

- **Owner:** Eng B
- **Branch:** `feat/redesign-phase-0-5-live-mode-awareness`
- **Depends on:** FR-0 (touches `Sidebar.tsx` again — wait for the
  Phase 0 restyle to land to avoid merge conflicts).
- **Effort:** ¼d

**Acceptance criteria**

- `frontend/src/lib/env.ts` exports `useIsMockMode()` and `IS_MOCK_MODE`
  driven by `import.meta.env.VITE_PHARMAPI_MOCK` (default `true`).
- `frontend/.env.example` documents `VITE_PHARMAPI_MOCK`.
- `vite.config.ts` wires the env var into the build.
- `<DevModeBadge>` (subtle slate chip) renders in the Sidebar footer
  when `IS_MOCK_MODE` is true and hides in live mode.
- No specific feature branches on `IS_MOCK_MODE` yet — that's FR-1
  and FR-3 territory.

**Prompt to paste**

> See [Phase 0.5 in `frontend-redesign-plan.md`](./frontend-redesign-plan.md#phase-05--live-mode-ui-awareness).

---

## FR-1 — Counter (Dashboard restyle)

- **Owner:** Eng A
- **Branch:** `feat/redesign-phase-1-counter`
- **Depends on:** FR-0, FR-0.5
- **Effort:** 1d

**Acceptance criteria**

- `Dashboard.tsx` matches `03-counter.html` layout: header, scan-hero
  with Barcode / Paperless pill-tabs, In-progress list, Today list,
  right-rail SafetyAlertsPanel.
- Scan submit → `navigate('/prescription/' + barcode)` (no inventing
  backend calls).
- Paperless tab: form rendered, submit disabled, `paperlessLookup`
  stub added to `lib/api.ts` rejecting with `ApiError(501)`.
- `⌘K` shortcut focuses the scanner input via the existing keyboard
  lib (verify the lib's API first — see the Phase 1 pre-flight note).
- "Generate Instructions" quick action is gated behind `IS_MOCK_MODE`
  (hidden in live).
- G14 / session banner only appears when an API call returns 401.
- Old 4-stat-card grid + Quick Actions block removed; `criticalCount`,
  page-level `alerts` state, and page-level `getActiveAlerts` import
  deleted; no orphan imports remain (`grep -n "criticalCount\|STATUS_CHIP"
  src/pages/Dashboard.tsx` returns nothing).
- Phase 1 Playwright smoke (login → land on Counter → scanner is
  autofocused → submit barcode → navigates to `/prescription/:barcode`)
  written under `frontend/tests/phase-1-counter.spec.ts`.

**Prompt to paste**

> See [Phase 1 in `frontend-redesign-plan.md`](./frontend-redesign-plan.md#phase-1--counter-dashboard).
> Includes the pre-flight (`lib/keyboard` audit), the Inputs block,
> the dead-code cleanup list, and the prompt body.

---

## FR-2 — Review (Prescription Verification restyle)

- **Owner:** Eng B
- **Branch:** `feat/redesign-phase-2-review`
- **Depends on:** FR-0
- **Effort:** 1d

**Acceptance criteria**

- `PrescriptionVerification.tsx` matches `04-review.html` layout:
  back-to-counter link, header with `.mono` barcode and action
  buttons, three-column grid
  (`lg:grid-cols-[1.35fr_1fr_1.05fr]`), severity-rowed safety panel.
- Approve & dispense uses `brand-600`, disabled with tooltip when a
  `block` check exists.
- Skeleton loading via `.sk animate-shimmer` while loading.
- **Every event handler and state machine preserved verbatim** —
  `onClickApprove`, `onConfirmApprove`, blocker filter, `c`/`f`
  shortcut wiring, modal/drawer open state.
- The three child modals (`ApproveConfirmModal`,
  `FlagDiscrepancyModal`, `ContactPrescriberDrawer`) are still mounted
  unchanged (FR-3 will replace `ApproveConfirmModal`).
- Phase 2 Playwright smoke (visit `/prescription/RX2024-005` in mock →
  three columns render → Approve disabled when a block check is
  present) under `frontend/tests/phase-2-review.spec.ts`.

**Prompt to paste**

> See [Phase 2 in `frontend-redesign-plan.md`](./frontend-redesign-plan.md#phase-2--review-prescription-verification).

---

## FR-3 — Dispense wizard

- **Owner:** Eng A
- **Branch:** `feat/redesign-phase-3-dispense-wizard`
- **Depends on:** FR-2 (both touch `PrescriptionVerification.tsx` — do
  NOT run in parallel; FR-3 starts only after FR-2 merges).
- **Effort:** 1–2d

**Acceptance criteria**

- New `components/DispenseWizard.tsx` matches `05-dispense-wizard.html`
  with the explicit state machine in the Phase 3 Inputs block:
  - step1: idle → verifying → (success → step2) | (failed → idle) | (skip-manual → step2)
  - step2: idle → submitting → (success → success-view) | (failed → idle)
  - success-view: terminal; CTAs "Back to counter" + "Generate
    counseling instructions" (mock-only).
  - Esc / scrim-click blocked during in-flight submit.
- `ApproveConfirmModal` usage in `PrescriptionVerification.tsx`
  replaced with the wizard.
- `verifyPack` and `decommissionPack` stubs in `lib/api.ts` reject
  with `ApiError(501)` per the contracts in the Phase 3 Inputs block.
- Real flow today (with stubs in place): step1 fails → "Skip — manual
  entry" → step2 → `approvePrescription` succeeds → success view.
  Verify this user journey is clear, not alarming.
- `approvePrescription(rxId)` signature + success toast + navigate to
  `/dashboard` preserved.
- Phase 3 Playwright smoke (open wizard → step 1 visible → skip-manual
  → step 2 succeeds → success → close → back on Counter) under
  `frontend/tests/phase-3-dispense.spec.ts`.

**Prompt to paste**

> See [Phase 3 in `frontend-redesign-plan.md`](./frontend-redesign-plan.md#phase-3--dispense-wizard).

---

## FR-4 — Patients (list + profile)

- **Owner:** Eng B
- **Branch:** `feat/redesign-phase-4-patients`
- **Depends on:** FR-0
- **Effort:** 1–1.5d

**Acceptance criteria**

- New `pages/Patients.tsx` matches `06-patients.html`.
- Dual-path search: 11-digit AMKA → `getPatient(amka)` directly;
  anything else → `searchPatients` stub (rejects 501) → empty state
  "search by name not yet available — try an AMKA". **Do not** iterate
  `getPatient` to fake a search.
- `searchPatients(query)` stub added to `lib/api.ts`.
- `/patients` index route registered in `App.tsx` **above** the
  existing `/patients/:id` route.
- `PatientProfile.tsx` matches `07-patient-profile.html` (avatar
  header, conditions/exceptions cards, Add condition modal).
- Every existing API call signature in `PatientProfile.tsx` preserved
  verbatim.
- Phase 4 Playwright smoke (`/patients` empty state → type AMKA →
  result row → click → profile renders) under
  `frontend/tests/phase-4-patients.spec.ts`.

**Prompt to paste**

> See [Phase 4 in `frontend-redesign-plan.md`](./frontend-redesign-plan.md#phase-4--patients-list--profile).

---

## FR-5a — Reports restyle (ADR)

- **Owner:** Eng B
- **Branch:** `feat/redesign-phase-5a-reports`
- **Depends on:** FR-0
- **Effort:** ½d

**Acceptance criteria**

- `SideEffects.tsx` matches `09-reports.html`.
- Page heading reads **"ADR Reports"** (not just "Reports" — see open
  decision in the plan doc).
- Route stays at `/side-effects`; file name stays `SideEffects.tsx`.
- `listSideEffects` and `flagSideEffect` calls preserved verbatim.

**Prompt to paste**

> See [Phase 5 / 5a in `frontend-redesign-plan.md`](./frontend-redesign-plan.md#phase-5--history-reports-settings)
> (the 5a sub-Inputs block + prompt section).

---

## FR-5b — History (new page, folds Documentation in)

- **Owner:** Eng B
- **Branch:** `feat/redesign-phase-5b-history`
- **Depends on:** FR-0
- **Effort:** 1d

**Acceptance criteria**

- New `pages/History.tsx` matches `08-history.html` (stats row,
  filters, searchable table).
- **Documentation → History parity (all of these must work in History):**
  - `q` free-text search filter
  - `method` filter (PRINT / DIGITAL / BOTH / ALL)
  - `limit` / `offset` pagination
  - `GET /documentation/export` (bulk CSV)
  - `GET /documentation/{id}/export` (per-row)
- `/history` route registered in `App.tsx`.
- `<Navigate to="/history" replace />` redirect from `/documentation`
  so old bookmarks don't 404.
- Sidebar's "Documentation Log" item removed (was in the old IA, gone
  in the new one).
- `grep -rn "/documentation" frontend/src` returns only the redirect
  registration and intentional historical references (not dead links).
- Phase 5 Playwright smoke (visit `/history` → table renders → filter
  by method → CSV export button visible; `/documentation` redirects
  to `/history`) under `frontend/tests/phase-5b-history.spec.ts`.

**Prompt to paste**

> See [Phase 5 / 5b in `frontend-redesign-plan.md`](./frontend-redesign-plan.md#phase-5--history-reports-settings).

---

## FR-5c — Settings (new page)

- **Owner:** Eng A
- **Branch:** `feat/redesign-phase-5c-settings`
- **Depends on:** FR-0
- **Effort:** 1–1.5d

**Acceptance criteria**

- New `pages/Settings.tsx` matches `10-settings.html` with sub-pages
  Profile / ΗΔΥΚΑ credentials / Pharmacy / Team / Audit log / Danger
  zone.
- All 5 settings stubs added to `lib/api.ts` per Phase 5c Inputs:
  `updatePharmapiPassword`, `inviteTeamMember`, `removeTeamMember`,
  `getAuditLog`, `signOutEverywhere` — each rejects with
  `ApiError(501)`.
- "Update ΗΔΥΚΑ password" modal renders the form and surfaces the
  501 response in a clear error banner.
- Team sub-page hidden / disabled for non-admin users (use `useAuth`).
- `/settings` route registered in `App.tsx`.
- Phase 5 Playwright smoke (visit `/settings` → sub-nav switches →
  attempt password change → 501 banner appears) under
  `frontend/tests/phase-5c-settings.spec.ts`.

**Prompt to paste**

> See [Phase 5 / 5c in `frontend-redesign-plan.md`](./frontend-redesign-plan.md#phase-5--history-reports-settings).

---

## FR-6 — Polish (mobile + optional dark mode)

- **Owner:** Eng A
- **Branch:** `feat/redesign-phase-6-mobile` (and `…-6b-dark-mode` if
  decision #2 = now)
- **Depends on:** every prior ticket (this is a polish pass over the
  whole redesigned app)
- **Effort:** ½–1d (mobile only); +1d if dark mode is in scope

**Acceptance criteria (mobile)**

- Sidebar collapses to a top bar / drawer under `md`.
- Counter hero + rail stack vertically at <640px.
- Review's three columns stack at <640px.
- Patients list and Patient profile reflow cleanly at 380px.
- All touch targets ≥40px.
- No behavior changes — same handlers, same routing, same data.

**Acceptance criteria (dark, if in scope)**

- `darkMode: "class"` added to `tailwind.config.js`.
- Theme toggle in sidebar footer.
- `dark:` variants across Counter + shared components match
  `12-counter-dark.html`.
- Semantic safety colors (red / amber / emerald) maintain AA contrast
  in dark theme.

**Prompt to paste**

> See [Phase 6 in `frontend-redesign-plan.md`](./frontend-redesign-plan.md#phase-6--polish-mobile--optional-dark-mode).

---

## Coordination notes

- **Daily integration:** each engineer rebases their in-flight branch
  off `main` once per day (especially after FR-0 / FR-2 land, since
  those touch shared files).
- **PR review:** cross-review across engineers (Eng A reviews Eng B's
  PRs and vice versa). Catches design-system drift early.
- **Mockups in repo:** before starting FR-0, copy the design mockups
  into `frontend/redesign-reference/` and add that path to
  `.gitignore`. All later tickets assume the files are there.
- **Per-ticket Playwright smoke:** required for FR-1 through FR-5c;
  the matrix is in the plan doc under "Per-phase Playwright smoke".
  These tests are local-only for now — not in CI.
- **If anyone goes off the prompt:** prefer asking on the PR rather
  than improvising. The prompts are tight on purpose; ad-hoc edits
  during the redesign create style drift that's hard to claw back.

## Related docs

- [`frontend-redesign-plan.md`](./frontend-redesign-plan.md) — the
  prompts, the foundation tokens, the open decisions, the per-phase
  template.
- [`going-real-live-mode-ux.md`](./going-real-live-mode-ux.md) — why
  the IA changes the way it does.
- [`going-real-production-readiness.md`](./going-real-production-readiness.md) —
  what the redesign does *not* cover (FMD/HMVS, secrets, CI, ops).
- [`claude-design-prompts.md`](./claude-design-prompts.md) — the
  upstream claude.ai prompts that generated the mockups this redesign
  implements.
