---
name: screen-convert
description: Use this skill when the user asks to redesign / restyle / convert a page to match one of the reference mockups in frontend/redesign-reference/*.html (e.g. "match 01-sign-in.html", "redesign Dashboard per 03-counter.html"). Encodes the lessons from the FR-1 Counter, FR-2 Review, Login, and AcceptInvite conversions — preserve API wiring, reuse Icons + i18n, never port the mockup's StateSwitcher, always run typecheck + lint + format, smoke against the running compose stack. (The dispense wizard was removed at tag hmvs-certified; 05-dispense-wizard.html is historical.)
---

# screen-convert — HTML reference → React/TSX page

## When to use

The user names a file under `frontend/redesign-reference/` and a target React
page or component, and asks to make the target match the reference visually
while keeping all existing API wiring. Examples:

- "Redesign frontend/src/pages/Dashboard.tsx to match 03-counter.html"
- "Restyle Login.tsx to match 01-sign-in.html, keep login() + redirect"
- "Match PrescriptionVerification to 04-review.html"

## Inputs the agent MUST gather before writing code

1. **Read the reference HTML end-to-end.** Inline `<script>` blocks contain
   the design system, icons, state machine, and component decomposition.
2. **Read the target React component end-to-end.** Identify which props /
   contexts / API calls MUST be preserved — these are "the wiring".
3. **Read `frontend/src/components/Icons.tsx`.** The mockup defines icons
   inline; they map to existing exports here. Never copy SVG markup — import.
4. **Read `frontend/src/lib/i18n.ts` + locale files.** Check which strings
   already exist and where to add new keys.
5. **Read `frontend/tailwind.config.js` + `frontend/src/index.css`** for the
   declared tokens (`brand-*`, `shadow-card`, `shadow-cardLg`,
   `animate-fade-in`, `animate-alert-in`, `animate-pulse-red-border`,
   `animate-modal-in`, `animate-pop`, `animate-shimmer`, `animate-slide-in-right`).
6. **Search recent merged PRs in the same area** to spot patterns already
   accepted (e.g. how FR-2 handled the NHRN badge — apply the same approach
   instead of inventing one).

## Conversion rules

### Wiring & navigation
- `<a href="#">` in the mockup → `<Link to="…">` from `react-router-dom`.
  Never leave fake hrefs.
- Existing `useAuth`, API calls (`listPrescriptions`, `getActiveAlerts`,
  `apiGetInviteInfo`, `apiAcceptInvite`, `approvePrescription`, etc.) MUST
  be preserved. The mockup's mock data is for visuals — it's not the
  contract.

### Mockup chrome we do not port
- **`StateSwitcher`** — used by designers to preview Default / Submitting /
  Error states. At runtime, state comes from props / hooks / API. Never copy.
- **Inline SVG icons** — import from `../components/Icons`. If the mockup
  uses an icon not yet exported, add it to `Icons.tsx` instead of inlining.
- **`MOCK_*` seed arrays** at the top of the mockup — these illustrate what
  shapes the section should render; the runtime data shape comes from the
  TypeScript types in `frontend/src/types/index.ts`.

### Strings & locale
- All visible strings via `t("namespace.key")`. Keys go in BOTH
  `frontend/src/locales/en.json` and `el.json`. Greek-first per HMVO.
- Date formatting:
  `new Date().toLocaleDateString(i18n.language?.startsWith("en") ? "en-GB" : "el-GR", …)`
- Use `<Trans i18nKey=... components={[…]}>` for translations with embedded
  markup, and remember to put `key="x"` on every component in the array
  (ESLint will catch this otherwise — see PR #99).
- Place generic UI strings (`showPassword`, `hidePassword`) under `common.*`,
  not page-specific namespaces — keeps them reusable across pages. (PR #106
  bot review caught cross-namespace reads.)

### Colour semantics (strict)
- **`brand-600`** — primary action, headers, links. Never green for primary.
- **emerald** — success / OK state only.
- **amber** — review / warning state.
- **red** — block / critical state. `animate-pulse-red-border` on block rows.
- The Counter (`StatusChip`) is the canonical example — see how it maps
  `PENDING` (amber + ClockIcon) vs `FLAGGED` (red + AlertCircleIcon).

### Shared components — propose a `title` prop, don't fork
If the target page uses a shared component (`SafetyAlertsPanel`,
`StatusChip`, `Sidebar`) and the mockup shows a slightly different label /
title / colour for that component, **add an optional prop with a sensible
default — don't fork the component or override styles from outside**.
Example from PR #99 + Nick's review:

```tsx
// before — Counter rail showed "Safety Alerts" but reference wanted
// "Active safety alerts"
export function SafetyAlertsPanel() {
  return <h2>Safety Alerts</h2>;   // hardcoded
}

// after — optional title prop, default preserves all other callers
export function SafetyAlertsPanel({ title = "Safety Alerts" }) {
  return <h2>{title}</h2>;
}
// Counter callsite:
<SafetyAlertsPanel title={t("counter.safety.title")} />
```

The reference HTML also tends to use a different visual scale for the same
component (smaller h3, less padding) — restyle the component in place ONLY
if it has a single caller. Otherwise add a `variant?: "compact"` prop.

### Wiring to preserve, by page
- `Login.tsx` → `useAuth().signIn()`, post-login `navigate("/dashboard")`,
  `location.state.notice` for post-redirect messages.
- `Dashboard.tsx` → `listPrescriptions`, the `SafetyAlertsPanel`
  (which fetches `getActiveAlerts` itself), `useAuth()` for pharmacy name.
- `PrescriptionVerification.tsx` → `getPrescription`, `approvePrescription`,
  `patchPrescription`, the safety check derivation, the `c` / `f` keyboard
  shortcuts, ApproveConfirmModal / FlagDiscrepancyModal / ContactPrescriberDrawer.
- `AcceptInvite.tsx` → `apiGetInviteInfo`, `apiAcceptInvite`, the
  loading / invalid / valid state split.
- `Documentation`, `SideEffects`, `Patients/:id`, `Instructions` →
  consult their service modules (`listDocumentation`, `listSideEffects`,
  `getPatient`, `generateInstructions`) before restyling.

### Keyboard & accessibility
- ⌘K / Ctrl+K hints must use a platform-aware label
  (`isAppleHost() ? "⌘K" : "Ctrl+K"`). PR #99 bot review caught this.
- Tab panels: every `role="tablist"` button needs `id` + `aria-controls`,
  every panel needs `role="tabpanel"` + `id` + `aria-labelledby`.
- ARIA `aria-controls` must point to a DOM node that actually exists
  (use `hidden` instead of conditional render, or remove the attribute when
  collapsed). PR #101 bot review.

### Data-shape limitations (be honest, comment them)
- `QueueItem` has no `alertCount` — hardcoding `count: 1` is wrong, but the
  fix is a backend payload change. Leave a `// TODO(data): ...` comment.
- Mock `MOCK_PRESCRIPTIONS` flips status to COMPLETED in-memory on
  `approve` — smoke tests need a backend restart between runs.

## Finalize block (always run before commit)

```bash
cd frontend && npm run typecheck && npm run lint && npm run format:check
```

If any fail, fix before claiming done. When enabled, both providers' Stop hooks
delegate to `scripts/agent_hooks.py` and run these checks through
`python3 scripts/verify.py --quick`. A missing or disabled hook is not a pass;
run the checks yourself before claiming completion.

Then drive a Playwright smoke against the running compose stack:

```bash
# Login as ladikosalexios@gmail.com / test1234
# Open the converted page in both locales:
http://localhost:5173/<route>?lng=el
http://localhost:5173/<route>?lng=en
```

Attach screenshots from both locales to the PR description.

## DO NOT

- Do not port the mockup's `StateSwitcher`.
- Do not inline SVG icons — import from `Icons.tsx`.
- Do not hardcode strings — every visible string goes through `t()`.
- Do not change the API contract. New form fields go to local state
  until the backend changes ship.
- Do not commit fake hrefs (`href="#"`). Use Link or remove.
- Do not run `npm install` unless `package.json` changes — the frontend
  container has deps baked in.
- Do not call cross-namespace i18n keys (e.g. `t("login.showPassword")`
  from inside AcceptInvite). Move generic keys to `common.*`.
- Do not assume the page's smoke test can reuse a Rx already flagged in
  an earlier run — restart the backend container to reset mock state.

## Output

Open a PR with:
- Title: short imperative ("FR-1: Counter — scan-driven Dashboard")
- Body: Summary / Wiring preserved / Spec notes / Test plan checkboxes —
  mirror the FR-1 / FR-2 / FR-3 / PR #106 style.
