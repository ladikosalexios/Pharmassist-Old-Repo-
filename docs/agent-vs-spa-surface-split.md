# Agent vs SPA — what the web app still needs (and doesn't)

Once the scan-riding **agent** (`agent/`, [`parasitic-agent-plan.md`](parasitic-agent-plan.md))
is the at-the-counter safety layer, the **web SPA**'s job changes. The pharmacist
does not live in our SPA — they live in Farmakon; the agent rides that. So the
SPA stops being the "primary workflow app" and becomes the **deep-work console
you drop into** when the agent's heads-up says "look closer" (the ⌘⌥↵ handoff to
`/prescription/:rxId`).

This doc reviews each SPA surface against that reframing.

> **Status (2026-07-15): implemented.** The Dashboard was reframed into the
> thin scan-to-review home, `/alerts/active` was deleted, and — going further
> than this doc — the whole execution path (eDispensation + HMVS/FMD, incl.
> the `/hmvs-check` demo) was removed at tag `hmvs-certified`. PharmAssist is
> retrieval-only; the pharmacist dispenses in their own software.

## The fork that decides everything

- **Parasitic-first (the thesis):** the agent + Farmakon is the product; the SPA
  is a companion. → the "queue / triage" surfaces below are redundant.
- **SPA-as-full-B2C-product:** for pharmacies that adopt our whole app *instead*
  of Farmakon, the SPA stays primary and the queue keeps a role.

The rest of this assumes **parasitic-first**, since that's the wedge we chose.

## Surface-by-surface

| SPA surface | Verdict | Why |
|---|---|---|
| **Dashboard** (`/dashboard`, `/alerts/active`) | 🔴 **Redundant** | Two independent reasons: (1) the "queue of prescriptions waiting at your pharmacy" has **no live ΗΔΥΚΑ backing** — ΗΔΥΚΑ is event-driven, no pull ([`going-real-live-mode-ux.md`](going-real-live-mode-ux.md)); (2) the agent now delivers alerts **at scan time**, which is the correct moment, not a batch list to triage later. The whole "landing = list of pending rx to review" premise dies. |
| **Prescription Verification** (`/prescription/:rxId`) | 🟢 **Keep — now central** | This IS the handoff target. All checks, SPC, override-with-reason, ADR entry, documentation — the deep review the glanceable card can't hold. Its role flips from "browse-first workflow" to "deep-dive on a specific rx you were handed." |
| **History / Documentation** (`/history`) | 🟢 Keep | Back-office / audit. The agent can't do the documentation log. |
| **Side Effects / ADR** (`/side-effects`) | 🟢 Keep | Pharmacovigilance reporting — deep-form work, off the counter path. |
| **Patients + Profile** (`/patients`, `/patients/:id`) | 🟢 Keep | Patient **conditions** power the safety engine; managing them is deep work. Arguably *more* important now — better conditions = better agent alerts. |
| **Instructions** (`/instructions`) | 🟡 Keep (review) | Counseling content — useful as reference, but check whether it's exercised in the parasitic flow or just legacy. |
| **Settings** (`/settings`) | 🟢 Keep | Session/credential/config. |
| **Login / Accept-Invite** (`/login`, `/accept-invite`) | 🟢 Keep | Auth + B2B onboarding. (The agent reuses the same login.) |
| **HMVS Check** (`/hmvs-check`) | 🔴 Removed | Went with the execution path (tag `hmvs-certified`). |

## The one clear removal

**The Dashboard as a prescription queue / active-alerts list.** It's the only
surface that is *both* unbacked live *and* superseded by the agent. Options,
lightest first:

1. **Reframe** `/dashboard` into a thin home (nav + "scan to begin" + session
   status), dropping the pending-rx list. `/alerts/active` (`routers/alerts.py`)
   becomes vestigial — it's the endpoint whose live path we just N+1-fixed;
   under parasitic-first it has no caller.
2. **Redirect** `/dashboard` → `/patients` or the verification entry, and delete
   the Dashboard page + `/alerts/active`.

I'd do (1) first — reversible, keeps a landing, and lets us watch whether anyone
misses the queue before deleting the endpoint.

## Nothing in the "brain" is redundant

The safety engine, ATC resolver, drug catalog, patient-conditions store — all
shared by both surfaces and by the agent. Only the SPA **presentation** that
*duplicates what the agent now does at the counter* (the queue/triage view) goes.
The deep-work surfaces stay and some (patient conditions) matter more.

## Net

- **Remove/reframe:** Dashboard prescription-queue + its `/alerts/active` backing. _(done)_
- **Promote:** `/prescription/:rxId` (handoff target), patient conditions.
- **Keep:** documentation, ADR, patients, settings, auth.
- **Unchanged:** the backend brain.
- **Also removed (beyond this doc):** the dispense/HMVS execution path — tag `hmvs-certified`.
