# Going Real: Live-Mode UX (ΗΔΥΚΑ workflow)

> Captures the architectural realization from the 2026-05 / 2026-06 "going
> real" investigation: **ΗΔΥΚΑ is event-driven, not queue-driven.** Several
> dashboard concepts that work in mock mode have no live equivalent and need
> to be reframed before the SPA can ship against real ΗΔΥΚΑ data.

## TL;DR

There is no "queue of prescriptions waiting at your pharmacy" anywhere in
the ΗΔΥΚΑ API. Prescriptions exist independent of pharmacies — any
qualifying ΕΟΠΥΥ pharmacy can dispense any prescription. The pharmacist
**reaches** a prescription one of two ways:

1. **Scan a paper barcode** → `GET /api/v1/prescriptions/get/{barcode}`
   (Accept: `application/x-hl7`) returns the full HL7 CDA.
2. **Paperless walk-in** → patient provides AMKA + an SMS-delivered PIN →
   `GET /api/v1/prescriptions/nopaper?amkaOrEkaa=...&pin=...&pharmacyId=...`.

The Pharmassist dashboard's pre-populated "Prescription Queue" is a mock
convenience that doesn't map to any live endpoint. Live mode is
fundamentally event-driven: nothing populates until a pharmacist scans
something.

## Why the pre-populated queue model breaks down

- **Not pre-assigned.** A prescription isn't bound to a pharmacy at issuance.
- **Patient privacy.** Listing what rxs a patient has requires either the
  patient's SMS PIN (`/nopaper`) or the physical paper barcode they're
  presenting (`/get/{barcode}`). The API will not enumerate them otherwise.
- **`/prescriptions/search` is pharmacist-scoped, not global.** The Greek
  summary literally reads *"Returns the pharmacist's prescriptions."*
  - `prescribed=false` → rxs this pharmacist has already engaged with but
    not finished dispensing (in-progress).
  - `prescribed=true` → rxs this pharmacist has dispensed (history).
  - Neither is a pool of "available work for any pharmacy." A test
    prescription that no one at our pharmacy has touched returns `0`
    across every filter combination (verified empirically).

## Endpoint reality (live)

| Endpoint | Returns | Trigger |
| --- | --- | --- |
| `GET /api/v1/prescriptions/get/{barcode}` (HL7 CDA) | Full prescription for any barcode the pharmacist scans | Pharmacist scans paper |
| `GET /api/v1/prescriptions/nopaper?amkaOrEkaa=...&pin=...` | Patient's paperless rxs | Patient gives AMKA + SMS PIN |
| `GET /api/v1/prescriptions/search?prescribed=false` | This pharmacist's in-progress dispenses | Populated after first touch |
| `GET /api/v1/prescriptions/search?prescribed=true&amka=...` | This pharmacist's history for that patient | Populated post-dispense |
| `POST /api/v1/prescriptions/dispense` (HL7 CDA) | — (executes dispense) | Pharmacist approves |
| `GET /api/v1/patients/{amka}/medicinehistory/full/{pharmacyId}/prescription` | Patient's clinical history across all pharmacies | Requires ΕΟΠΥΥ + `patientsConsent=true` |
| `GET /api/v1/patients/{amka}/medicinehistory/{pharmacyId}/intolerances` | Patient's intolerances | Same gating |

## Live pharmacist workflow (step-by-step)

1. **Scan paper barcode** _or_ enter **AMKA + SMS PIN** for paperless.
2. `GET /prescriptions/get/{barcode}?pharmacyId={pid}` (`Accept: application/x-hl7`)
   → ΗΔΥΚΑ returns the prescription as an HL7 CDA `<ClinicalDocument>`.
3. App parses the CDA → extracts patient AMKA, medicines (with EOF codes),
   prescriber, validity dates.
4. App runs the safety pipeline:
   - `pharmapi_get_patient_medicine_history(amka)` → real past dispensings
   - `pharmapi_get_patient_intolerances(amka)` → real contraindications
   - `conditions(session, amka, pharmacy_id)` → DB-recorded patient conditions
   - `load_active_safety_rules(session)` → rule catalogue
   - **Per medicine: look up ATC by EOF code in `drug_catalog`** (depends on
     T6 full catalog sync — see *Open follow-ups*).
   - `evaluate_safety(...)` → emits alerts.
5. Verification view renders the rx + the alerts that just fired.
6. Pharmacist reviews. If no `block`-status alert, "Approve" is enabled.
7. Approve → `POST /api/v1/prescriptions/dispense` with an HL7 CDA body →
   the rx moves into `/search?prescribed=true` history.

## Implications for the current SPA

The mock dashboard pre-populates 9 "pending" rxs and shows their alerts
batch-style. In live mode the analogous data simply doesn't exist at start
of day — `/prescriptions/search?prescribed=false` returns `[]` until a
pharmacist starts scanning.

### Concept mapping

| Mock concept | Live equivalent |
| --- | --- |
| **"Pending Verification" stat** (currently `9`) | "In-progress" count — rxs scanned but not yet dispensed. Usually `0–3`, starts the day at `0`. |
| **"Prescription Queue" list** | Two panels: "In-progress" + "Recently dispensed" (today's history). |
| **"Critical Alerts" stat + Safety Alerts panel** | Alerts aggregated from currently-in-progress scans only. Still meaningful — a pharmacist who scanned three rxs has three sets of alerts to triage. |
| **"Completed Today"** | `/search?prescribed=true` filtered by today's date. Already a real concept. |

### Recommended UI changes

- **Primary CTA on the landing page** should be a **scanner / barcode entry**
  (and a secondary "AMKA + PIN" entry for paperless walk-ins). Without this,
  there is no way to enter the verification flow in live mode.
- Rename "Queue" → **"In progress"** (or similar) — it never holds anything
  the pharmacist hasn't already touched.
- Add **"Recent history"** panel (today's completed dispensings) as the
  always-populated context the dashboard currently lacks in live mode.
- Keep the **Safety Alerts panel** — its source becomes the union of alerts
  attached to currently-in-progress scans. Still useful: a pharmacist might
  scan, get distracted, and the panel reminds them of unresolved blockers.
- The mock dashboard can stay as-is for demos; the live build should default
  to the event-driven layout.

## What's already working live (verified 2026-05/06)

- ΕΟΠΥΥ pharmacy `70014` (TEST ΦΑΡΜΑΚΕΙΟ ΕΟΠΥΥ, `isIka=true`) is the active
  pharmacy; the existing `_start_pharmapi_session` picks it up transparently
  from `/user/me`.
- Patient lookup for all four ΗΔΥΚΑ test AMKAs (`01010003430`, `05055505340`,
  `01018022432`, `11123602283`).
- Patient medicine history and intolerances (no more `609` — ΕΟΠΥΥ category
  unlocks it; `patientsConsent=true` is sent).
- `GET /prescriptions/get/{barcode}` returns full HL7 CDA for all three test
  barcodes (`2605292031642`, `2605292023642`, `2605292016642`).

## Open follow-up tickets

The realization above implies new scope that wasn't in the original sprint:

- **HL7 CDA fetch service** — `pharmapi_get_prescription_hl7(barcode, pharmacy_id)`
  + `parse_prescription_cda(xml) -> dict` mapping to the engine-friendly
  shape (`rxId`, `patient.{id,amka}`, `medication.{name, eofCode}`, ...).
- **New route** — `GET /prescriptions/by-barcode/{barcode}` so the SPA's
  scan flow has a backend entry point.
- **T6 (already in sprint) — full `drug_catalog` seed** from
  `/api/v1/masterdata/medicines`. Without it, EOF codes (e.g. `207671102`
  for ALGOFREN) don't resolve to ATCs and the safety engine skips
  ATC-keyed checks.
- **HL7 CDA builder for dispense** — replace the 501 in
  `pharmapi_execute_prescription` with a real `<ClinicalDocument>` builder
  that POSTs to `/api/v1/prescriptions/dispense`. Bigger ticket.
- **SPA redesign** — primary scan/PIN actions, in-progress panel, recent
  history panel. Probably best done together with the HL7 fetch wiring.

## External blockers (not engineering)

- **HMVS / FMD verification** — pending HMVO approval at
  https://hmvo.gr/it_suppliers/. Independent track; QR-based pack
  verification needs it.
- **Production ΕΟΠΥΥ certification** — email `Hd@idika.gr` to onboard a
  real production pharmacy into the ΕΟΠΥΥ category.

## Reference

- Spec: `https://testeps.e-prescription.gr/pharmapiv2/documentation/manufacturers/index.html`
- ΗΔΥΚΑ support thread (2026-05): confirmed the ΕΟΠΥΥ category requirement,
  provided test AMKAs + test barcodes, pointed to HMVO for FMD.
