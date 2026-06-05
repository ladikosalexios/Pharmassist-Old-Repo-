# PharmAssist — Pricing & Packaging

**Version:** June 2026
**Market:** Greece

PharmAssist is sold through **two go-to-market motions** that share a single capability
catalog:

- **B2B API** — for companies that already run their own pharmacy software or operational
  system (pharmacy chains, cooperatives, OS vendors, healthcare platforms). Priced **per
  location / month**. API-only; no pharmacist-facing UI is provided or assumed. Prescription
  execution is an optional add-on.
- **B2C Direct** — for **individual independent pharmacies that do not run a partner OS**.
  They use PharmAssist's own pharmacist-facing app as their dispensing and safety system.
  Priced **per seat / month**, where a **seat is one pharmacist** and a single pharmacy can
  hold multiple seats. Prescription execution is included.

The same clinical intelligence stack powers both motions. The difference is the delivery
surface (API vs. app), the billing unit (location vs. seat), and how prescription execution
is packaged.

---

## Overview

PharmAssist exposes its clinical intelligence stack two ways:

1. **As a B2B API** for companies that have their own pharmacy software or operational
   systems and want to layer prescription safety, ΗΔΥΚΑ integration, and agentic clinical
   features on top — without building or maintaining any of that infrastructure themselves.
2. **As a B2C direct-to-pharmacy app** for independent pharmacies that have no such system.
   For these pharmacies PharmAssist is the front line: the pharmacist works the prescription
   queue, runs safety checks, executes the prescription, counsels the patient, and keeps the
   legal documentation trail — all inside PharmAssist.

The two motions draw from the same **Shared Capability Catalog** below.

---

## Shared Capability Catalog

Every feature is built once and delivered through both motions. B2B exposes them as API
endpoints; B2C surfaces them in the pharmacist-facing app. The tier tables in each motion
reference these capabilities.

### Pharmapi (ΗΔΥΚΑ) Proxy

- Patient lookup by AMKA or EKAA — returns demographics (name, DOB, sex, phone, address)
- Prescription search (pending + history with AMKA)
- Patient insurance details (ΕΟΠΥΥ coverage, co-pay %)
- Patient intolerances from ΗΔΥΚΑ (requires ΕΟΠΥΥ-category account)
- Patient medicine history from ΗΔΥΚΑ (requires ΕΟΠΥΥ-category account)
- Drug catalog — full national medicines list, ATC codes, active substance, GNS codes
- Pharmapi error handling (G01–G15 error codes, session management, 24h refresh)
- Boot-time version check — alerts if upstream Pharmapi version has changed

### Safety Engine

- Drug-drug interaction checking against DB-backed ruleset
- Duplicate therapy detection
- Patient condition-based contraindication alerts (e.g. metformin + diabetes + renal
  impairment)
- Safety rule severity levels (MODERATE / SEVERE / CRITICAL)
- Patient conditions CRUD — create, read, update, delete patient condition records that feed
  the safety engine

### Formulary Substitution

- Given a drug that is unavailable or uncovered, returns ranked therapeutic alternatives by
  ATC class, filtered by ΕΟΠΥΥ coverage and clinical equivalence
- Includes dose conversion notes where applicable

### Agentic SPC Contraindication Lookup

- On every prescription submitted, a background agent reads the full SPC for each drug and
  checks contraindications, special population warnings (renal, hepatic, elderly, pregnancy),
  and interaction sections against the patient's known conditions
- Returns structured findings with the exact SPC section cited before any dispensing action
  is taken
- Catches rare and newly updated contraindications that the rule-based safety engine does not
  cover
- Response includes: drug name, SPC section reference, finding text, severity classification,
  recommended action

### AI Safety Flag Explanations

- When the safety engine flags an interaction or contraindication, returns a 1–2 sentence
  plain-language clinical rationale in Greek
- Explains the mechanism, the risk level, and suggested alternatives
- Cached by rule + patient condition profile to minimise latency

### SPC Q&A (RAG)

- Accepts a free-text clinical question and a drug identifier
- Returns an answer drawn from the official SPC document for that drug, with the source
  section cited
- Supports Greek-language queries
- Example: "Είναι ασφαλές σε ασθενή με νεφρική ανεπάρκεια σταδίου 3;"

### Medication Adherence Signals

- Monitors refill cadence for patients on long-term medications (anticoagulants,
  antihypertensives, insulin, statins, antidepressants)
- Returns an adherence status per patient: ON_TRACK / OVERDUE / LAPSED, with days since
  expected refill
- Caller is responsible for outreach; this provides the signal only

### ADR Reporting

- Create, update, and track adverse drug reaction reports
- State machine: PENDING_REVIEW → ESCALATED → EOF_REPORTED
- Query ADR history by patient, drug, or date range

### AI ADR Narrative Drafting

- Given a structured ADR record, returns a draft clinical narrative formatted for EOF
  submission
- Always returned as a draft requiring human review — never auto-submitted
- Reduces documentation time from ~20 minutes to ~2 minutes review

### Patient Condition Inference

- Background agent reviews a patient's dispensing history and returns suggested conditions for
  confirmation
- Returns: suggested condition, confidence signal (HIGH / MEDIUM), supporting evidence (drugs
  that indicate the condition)
- Suggestions only — caller confirms before writing to patient conditions

### Patient Instructions & Documentation

- Generates patient counselling instructions per prescription (Greek / English), with optional
  side-effect and lifestyle sections, delivered by print or digital
- Writes a legal documentation/audit log entry for every dispensing action, capturing the
  safety-check snapshot, prescriber, pharmacist, and delivery method at the time of action
- Exportable audit trail (PDF / CSV), per record or full report

### Pharmacovigilance Signal Detection

- Continuously aggregates ADR reports and safety flag data across all of a customer's
  locations
- Applies statistical clustering to identify emerging safety signals: unusual reaction rates
  for a specific drug, batch, or drug combination across the network
- When a threshold is crossed, generates a structured signal report formatted for EOF
  submission
- Signals improve as network data grows — see introductory pricing note

### Drug Recall Webhook

- Monitors EOF and EMA recall feeds continuously
- When a recalled drug or batch is detected, fires a webhook to the customer's endpoint within
  minutes
- Payload includes: recalled drug/batch details, list of locations that dispensed it,
  estimated patient count, recommended patient outreach template
- On-demand check: `GET /recalls/check?gns_code=X&batch=Y`

### Reaction Network Alert Agent

- When a serious ADR is recorded at any location, the agent identifies all other locations in
  the customer's network that have dispensed the same drug to the same patient
- Fires an internal network notification to those locations immediately
- Payload: patient identifier, drug, reaction summary, locations affected, recommended action

### Insurance Pre-Authorization Agent

- Identifies at prescription intake whether a drug requires ΕΟΠΥΥ prior authorisation
- Pre-fills the authorisation request from patient data already on file
- Tracks authorisation status and fires a webhook on approval or rejection
- `POST /prescriptions/{barcode}/preauth` — submit
- `GET /prescriptions/{barcode}/preauth/status` — check status

### HMVS Medicine Verification

- `GET /api/medicines/lot/qr` — verify a medicine QR code (SINGLE VERIFY)
- `POST /api/medicines/decommission` — decommission a pack (sample / destruction)
- `POST /api/otcm/reactivate` — reactivate a QR code in case of dispensing error
- Requires the customer to be registered with HMVO (hmvo.gr/it_suppliers/) — PharmAssist
  proxies the call but cannot substitute for HMVO registration

### Prescription Execution (live ΗΔΥΚΑ dispense)

- Submits the prescription to ΗΔΥΚΑ to complete the dispense, recording the execution
  reference against the legal documentation log
- The dispensing workflow and UI (`DispenseWizard`, approve/flag, audit snapshot) are
  complete; the live ΗΔΥΚΑ dispense POST is in final wiring
- **Packaging differs by motion:** an optional **add-on for B2B** (OS companies usually
  dispense through their own system), and **included in B2C tiers** (an independent pharmacy
  has no other way to dispense)

---

## Motion A — B2B API

**Billing unit:** per location / month. **Target:** enterprise / multi-location operators
(pharmacy chains, cooperatives, OS vendors, healthcare platforms). **Delivery:** API-only; no
pharmacist-facing UI is provided or assumed.

PharmAssist exposes its clinical intelligence stack as a B2B API for companies that have their
own pharmacy software and want to layer prescription safety, ΗΔΥΚΑ integration, and agentic
clinical features on top — without building or maintaining any of that infrastructure
themselves.

### Tier 1 — Core · €15 / location / month

The "cheaper than building it yourself" tier. Covers the full Pharmapi integration layer and
the safety engine — everything a company would need 3–6 months of engineering to replicate,
plus the clinical rule layer they could not build at all.

Includes: **Pharmapi Proxy**, **Safety Engine**, **Formulary Substitution**.

### Tier 2 — Clinical · €32 / location / month

Everything in Core, plus the agentic clinical intelligence layer. This is where PharmAssist's
differentiation is clearest — no Greek pharmacy software competitor offers this via API at any
price point.

Adds: **Agentic SPC Contraindication Lookup**, **AI Safety Flag Explanations**, **SPC Q&A
(RAG)**, **Medication Adherence Signals**, **ADR Reporting**, **AI ADR Narrative Drafting**,
**Patient Condition Inference**.

### Tier 3 — Platform · €52 / location / month

Everything in Clinical, plus network-scale intelligence features that are only possible at
multi-location scale. These features become more valuable as the customer's network grows.

Adds: **Pharmacovigilance Signal Detection**, **Drug Recall Webhook**, **Reaction Network
Alert Agent**, **Insurance Pre-Authorization Agent**, **HMVS Medicine Verification**.

### Add-on — Prescription Execution (live ΗΔΥΚΑ dispense) · +€8 / location / month

Available to Platform-tier customers. Exposes the live ΗΔΥΚΑ dispense endpoint so callers can
complete the dispense through PharmAssist. Optional because most OS customers execute the
dispense through their own system; offered for those who want PharmAssist to own the full
transaction. (Workflow complete; live ΗΔΥΚΑ POST in final wiring.)

### B2B Feature Matrix

| Feature | Core | Clinical | Platform |
|---|---|---|---|
| Patient lookup (AMKA / EKAA) | ✅ | ✅ | ✅ |
| Prescription search | ✅ | ✅ | ✅ |
| Patient insurance details | ✅ | ✅ | ✅ |
| Patient intolerances (ΗΔΥΚΑ) | ✅ | ✅ | ✅ |
| Patient medicine history (ΗΔΥΚΑ) | ✅ | ✅ | ✅ |
| Drug catalog / masterdata | ✅ | ✅ | ✅ |
| Pharmapi error handling & session management | ✅ | ✅ | ✅ |
| Drug-drug interaction checking | ✅ | ✅ | ✅ |
| Duplicate therapy detection | ✅ | ✅ | ✅ |
| Patient condition-based alerts | ✅ | ✅ | ✅ |
| Patient conditions CRUD | ✅ | ✅ | ✅ |
| Formulary substitution | ✅ | ✅ | ✅ |
| Agentic SPC contraindication lookup | — | ✅ | ✅ |
| AI safety flag explanations (Greek) | — | ✅ | ✅ |
| SPC Q&A / RAG | — | ✅ | ✅ |
| Medication adherence signals | — | ✅ | ✅ |
| ADR reporting endpoints | — | ✅ | ✅ |
| AI ADR narrative drafting | — | ✅ | ✅ |
| Patient condition inference | — | ✅ | ✅ |
| Pharmacovigilance signal detection | — | — | ✅ |
| Drug recall webhook | — | — | ✅ |
| Reaction network alert agent | — | — | ✅ |
| Insurance pre-auth agent (ΕΟΠΥΥ) | — | — | ✅ |
| HMVS medicine verification | — | — | ✅ |
| Prescription execution (live ΗΔΥΚΑ) | — | — | Add-on (+€8) |

### B2B Pricing Summary

| Tier | Per location / month | 1,000 locations / month | Annual |
|---|---|---|---|
| Core | €15 | €15,000 | €180,000 |
| Clinical | €32 | €32,000 | €384,000 |
| Platform | €52 | €52,000 | €624,000 |
| Prescription Execution add-on | +€8 | +€8,000 | +€96,000 |

### B2B One-Time Fees

| Item | Cost |
|---|---|
| Integration & onboarding | €35,000 – €60,000 |
| Custom API mapping (bespoke endpoint requirements) | €10,000 – €25,000 (T&M) |
| Dedicated sandbox environment | €5,000 setup |

### B2B Contract Terms & Discounts

| Commitment | Discount |
|---|---|
| Month-to-month | — |
| Annual | 10% |
| 3-year | 20% |

Indicative 3-year TCV — Platform tier at 1,000 locations (20% discount):
€52,000 × 12 × 3 × 0.80 = ~€1.5M + onboarding.

---

## Motion B — B2C Direct

**Billing unit:** per seat / month, where **a seat is one pharmacist**. A single pharmacy can
hold **multiple seats** — one per pharmacist who needs to log in and dispense. **Target:**
individual independent pharmacies that do not run a partner OS. **Delivery:** the full
PharmAssist pharmacist-facing app (prescription queue, verification, dispensing, patient
counselling, documentation).

For these pharmacies PharmAssist is the system of record at the counter, so **prescription
execution is included** in every tier — it is the reason an independent pharmacy adopts
PharmAssist rather than a layer on top of something else.

### How seats work

- The **first seat** activates the pharmacy account and includes ΗΔΥΚΑ onboarding and the
  pharmacy's connection setup.
- Each **additional pharmacist** is added as a seat via the in-app invite flow (the pharmacy
  admin invites a pharmacist by email; the pharmacist accepts and links to the pharmacy).
- Seats are billed monthly; a pharmacy adds or removes seats as its team changes.

### Tier 1 — Essential · €45 / seat / month

The full dispensing app. Everything an independent pharmacy needs to work the counter safely
and compliantly.

Includes:

- **Prescription queue & verification** — pending + history from ΗΔΥΚΑ, full prescription
  detail
- **Prescription Execution (included)** — the `DispenseWizard` dispensing flow with approve /
  flag-discrepancy
- **Safety Engine** — drug-drug interactions, duplicate therapy, condition-based
  contraindications, severity grading
- **Patient profile, history & conditions** — demographics, Rx history, allergies /
  intolerances, safety flags
- **Patient Instructions** — Greek / English counselling notes, print or digital
- **Documentation / legal audit log** — every dispensing action recorded with safety snapshot;
  PDF / CSV export

### Tier 2 — Clinical · €75 / seat / month

Everything in Essential, plus the AI clinical intelligence layer.

Adds:

- **SPC Q&A (RAG)** and **Agentic SPC contraindication lookup**
- **AI safety flag explanations** (plain-language Greek rationale)
- **ADR reporting** + **AI ADR narrative drafting**
- **Patient condition inference**
- **Medication adherence signals**

### Discounts & one-time fees

| Item | Terms |
|---|---|
| Seat-volume discount | Seats 4+ at −15% (a multi-pharmacist pharmacy does not pay linearly) |
| Annual prepay | −15% (≈2 months free) on the whole subscription |
| Onboarding | €390 one-time (includes ΗΔΥΚΑ setup + 4h training), **waived on annual prepay** |

### B2C Feature Matrix

| Capability | Essential | Clinical |
|---|---|---|
| Prescription queue & verification | ✅ | ✅ |
| **Prescription execution (dispense)** | ✅ included | ✅ included |
| Safety engine (interactions, duplication, contraindications) | ✅ | ✅ |
| Patient profile, history & conditions | ✅ | ✅ |
| Patient instructions (Greek / English) | ✅ | ✅ |
| Documentation / legal audit log + export | ✅ | ✅ |
| SPC Q&A / RAG · Agentic SPC lookup | — | ✅ |
| AI safety flag explanations | — | ✅ |
| ADR reporting + AI ADR narrative | — | ✅ |
| Patient condition inference | — | ✅ |
| Medication adherence signals | — | ✅ |

> **Implementation note (B2C):** the dispensing workflow, safety engine, patient/ADR/
> documentation and instructions surfaces are live in the app today; live ΗΔΥΚΑ dispense
> submission is in final wiring (see notes). Several Clinical-tier AI capabilities are
> rolling out — confirm current availability with the customer before contracting the
> Clinical tier.

### B2C Worked Examples

Monthly figures are before the annual-prepay discount. The seats-4+ volume break applies
−15% to the per-seat rate from seat 4 onward; the **Annual** column then applies a further
−15% to the resulting 12-month total.

**Essential — €45 / seat / month** (seats 4+ at €38.25)

| Pharmacy size | Seats | Monthly | Annual (−15%) |
|---|---|---|---|
| Solo | 1 | €45.00 | €459.00 |
| Small team | 3 | €135.00 | €1,377.00 |
| Larger team | 5 | €211.50 (3×€45 + 2×€38.25) | €2,157.30 |

**Clinical — €75 / seat / month** (seats 4+ at €63.75)

| Pharmacy size | Seats | Monthly | Annual (−15%) |
|---|---|---|---|
| Solo | 1 | €75.00 | €765.00 |
| Small team | 3 | €225.00 | €2,295.00 |
| Larger team | 5 | €352.50 (3×€75 + 2×€63.75) | €3,595.50 |

### Competitive positioning (vs. incumbent ERP — e.g. PYLON Farmakon)

A Greek pharmacy ERP today is sold as a perpetual licence (≈€950 core including **one** user,
**+€150 per extra seat**, ≈€264–340/yr support, +€130 install). PharmAssist B2C is
positioned differently:

- **SaaS, no upfront capEx** — monthly per-seat, cancel or scale seats anytime.
- **AI clinical intelligence + compliance** the incumbent ERP does not offer — SPC Q&A, AI
  safety explanations, ADR narrative drafting, condition inference, and a built-in legal
  documentation/audit trail.
- **Included prescription execution** — dispensing is part of the app, not a bolt-on.
- PharmAssist is a **clinical-grade dispensing and safety system, not a full inventory / POS /
  accounting ERP** — it complements or replaces the dispensing side of a pharmacy's stack
  rather than its back office.

---

## Cross-cutting Notes

**On the 609 / ΗΔΥΚΑ permission requirement:** Patient intolerances and medicine history
require the pharmacy's ΗΔΥΚΑ accounts to be in the ΕΟΠΥΥ category (`isIka = true`). Pharmacy
70466 in the current test environment is not ΕΟΠΥΥ. For production, customers must obtain this
category through ΗΔΥΚΑ (Hd@idika.gr). PharmAssist cannot grant this permission. (Applies to
both motions.)

**On HMVS (B2B Platform tier):** HMVS endpoints proxy calls to the Hellenic Medicines
Verification System. Each customer must independently register with HMVO
(hmvo.gr/it_suppliers/) — PharmAssist provides the integration layer but cannot substitute
for HMVO registration.

**On pharmacovigilance signal detection (B2B Platform tier):** Signal quality is directly
proportional to network data volume. For the first 6 months of a Platform contract, an
introductory rate of €42/location/month is recommended, stepping automatically to the full
€52 rate at month 7. This should be written into the contract rather than offered as a
negotiated concession.

**On AI features (B2B Clinical/Platform and B2C Clinical):** AI features (safety
explanations, SPC Q&A, ADR narrative drafting, condition inference) depend on an EU-region LLM
provider endpoint with a GDPR Data Processing Agreement in place. No patient PII (AMKA, name,
address) is transmitted to the LLM — prompts are constructed from clinical data only (drug
codes, ATC classes, rule descriptions, anonymised demographics).

**On prescription execution:** Prescription execution submits the dispense to ΗΔΥΚΑ
(HL7 CDA format). The PharmAssist dispensing workflow, UI, approve/flag actions, and audit
snapshot are complete; the live ΗΔΥΚΑ dispense POST is in final wiring. It is packaged as an
**optional add-on for B2B** (Platform tier, +€8/location/month) and is **included in all B2C
tiers**.
