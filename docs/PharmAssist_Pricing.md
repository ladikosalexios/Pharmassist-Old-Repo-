# PharmAssist — Pricing & Packaging

**Version:** September 2026 (adds Motion A Tier 0 "Clinical-only" per D-20; supersedes the
July 2026 retrieval-only revision)
**Market:** Greece

> **What changed vs. June 2026:** PharmAssist no longer executes prescriptions.
> Dispensing stays in the pharmacy's existing software; PharmAssist is the
> **clinical safety and review layer that rides alongside it**. The Prescription
> Execution add-on and HMVS Medicine Verification were removed from the catalog
> (code preserved at git tag `hmvs-certified`), and the B2C motion was
> repositioned from "replacement dispensing system" to "counter safety
> companion". This file is the canonical version; the old PDF twin was retired.

PharmAssist is sold through **two go-to-market motions** that share a single capability
catalog:

- **B2B API** — for companies that already run their own pharmacy software or operational
  system (pharmacy chains, cooperatives, OS vendors, healthcare platforms). Priced **per
  location / month**. API-only; no pharmacist-facing UI is provided or assumed.
- **B2C Direct** — for **individual pharmacies**, regardless of which dispensing ERP they
  run. They get the PharmAssist safety companion: a **counter agent** that rides their
  existing software and surfaces safety alerts at scan time, plus the **review console**
  (web app) for deep work — prescription review, patient conditions, ADR reporting, and the
  legal documentation trail. Priced **per seat / month**, where a **seat is one pharmacist**
  and a single pharmacy can hold multiple seats.

The same clinical intelligence stack powers both motions. The difference is the delivery
surface (API vs. agent + app) and the billing unit (location vs. seat). **Neither motion
executes the dispense** — the pharmacy's own system remains the system of record for the
transaction, which means adopting PharmAssist requires no rip-and-replace, no ΗΔΥΚΑ
execution liability transfer, and no retraining of the counter workflow.

---

## Overview

PharmAssist exposes its clinical intelligence stack two ways:

1. **As a B2B API** for companies that have their own pharmacy software or operational
   systems and want to layer prescription safety, ΗΔΥΚΑ retrieval, and agentic clinical
   features on top — without building or maintaining any of that infrastructure themselves.
2. **As a B2C safety companion** for individual pharmacies. The pharmacist keeps
   dispensing in the software they already know; PharmAssist watches the counter (scan-time
   safety alerts via the local agent), and one keystroke opens the full review console for
   the hard cases — safety checks, SPC lookups, patient history and conditions, flagging a
   discrepancy to the prescriber, ADR reporting, and the exportable documentation log.

The two motions draw from the same **Shared Capability Catalog** below.

---

## Shared Capability Catalog

Every feature is built once and delivered through both motions. B2B exposes them as API
endpoints; B2C surfaces them in the counter agent and the review console. The tier tables
in each motion reference these capabilities.

### Pharmapi (ΗΔΥΚΑ) Proxy — retrieval

- Patient lookup by AMKA or EKAA — returns demographics (name, DOB, sex, phone, address)
- Prescription retrieval — barcode-direct lookup (incl. paperless/άυλη) and search
  (pending + history with AMKA)
- Patient insurance details — fund identity, ΕΟΠΥΥ-coverage flag, and patient co-pay
  exemption records; drug-level participation % via the drug catalog
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

- On every prescription reviewed, a background agent reads the full SPC for each drug and
  checks contraindications, special population warnings (renal, hepatic, elderly, pregnancy),
  and interaction sections against the patient's known conditions
- Returns structured findings with the exact SPC section cited while the prescription is
  still on the counter
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

- Background agent reviews a patient's medication history and returns suggested conditions
  for confirmation
- Returns: suggested condition, confidence signal (HIGH / MEDIUM), supporting evidence (drugs
  that indicate the condition)
- Suggestions only — caller confirms before writing to patient conditions

### Patient Instructions & Documentation

- Generates patient counselling instructions per prescription (Greek / English), with optional
  side-effect and lifestyle sections, delivered by print or digital
- Writes a legal documentation/audit log entry for every review, flag, and counselling
  action, capturing the safety-check snapshot, prescriber, pharmacist, and delivery method
  at the time of action
- Exportable audit trail (PDF / CSV), per record or full report

### Prescriber Communication (Flag Discrepancy)

- Flag a prescription discrepancy (dose error, interaction, missing info, suspected forgery)
  with structured reason + notes, recorded on the documentation log
- Optional physician notification with the flag context attached
- The prescription is never executed by PharmAssist — the flag is triage input for the
  pharmacist's decision inside their own dispensing system

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
- Payload includes: recalled drug/batch details, list of locations that handled it,
  estimated patient count, recommended patient outreach template
- On-demand check: `GET /recalls/check?gns_code=X&batch=Y`

### Reaction Network Alert Agent

- When a serious ADR is recorded at any location, the agent identifies all other locations in
  the customer's network that have seen the same drug for the same patient
- Fires an internal network notification to those locations immediately
- Payload: patient identifier, drug, reaction summary, locations affected, recommended action

### Insurance Pre-Authorization Agent

- Identifies at prescription intake whether a drug requires ΕΟΠΥΥ prior authorisation
- Pre-fills the authorisation request from patient data already on file
- Tracks authorisation status and fires a webhook on approval or rejection
- `POST /prescriptions/{barcode}/preauth` — submit
- `GET /prescriptions/{barcode}/preauth/status` — check status

---

## Motion A — B2B API

**Billing unit:** per location / month. **Target:** enterprise / multi-location operators
(pharmacy chains, cooperatives, OS vendors, healthcare platforms). **Delivery:** API-only; no
pharmacist-facing UI is provided or assumed.

PharmAssist exposes its clinical intelligence stack as a B2B API for companies that have their
own pharmacy software and want to layer prescription safety, ΗΔΥΚΑ retrieval, and agentic
clinical features on top — without building or maintaining any of that infrastructure
themselves. Because PharmAssist never executes the dispense, the integration carries no
transaction liability: the customer's system keeps full control of the dispensing act, and
PharmAssist is pure decision support.

### Tier 0 — Clinical-only · €9 / location / month

The tier for a customer who wants the decision layer and nothing that touches a patient.
Everything here runs on **drug codes and ATC classes alone** — no Pharmapi retrieval, so no
ΗΔΥΚΑ credentials to provision and no 609 / ΕΟΠΥΥ-category prerequisite (see Cross-cutting
Notes). Nothing in this tier can look a patient up.

Includes: **Safety Engine** (drug-drug interactions, duplicate therapy, and condition-based
alerts evaluated against **caller-supplied** conditions) and **drug catalog / masterdata
reads**.

Excludes, by construction: patient lookup, prescription retrieval, insurance details,
intolerances, medicine history, and formulary substitution — everything requiring an upstream
call. Those routes answer `409 retrieval_unavailable` (D-21).

> **Retrieval is orthogonal to tier.** Any tier is purchasable by a customer with no ΗΔΥΚΑ
> credentials on file; the retrieval routes simply answer `409 retrieval_unavailable` while the
> rest of the tier works normally. This matters commercially: the buyer for the SPC-citation
> pitch is a **Clinical tenant without retrieval**, not a Tier-0 tenant, because SPC lookup is
> a Clinical capability. Price that as Clinical less the retrieval component — **€26 /
> location / month** is the recommended anchor — rather than trying to squeeze it into Tier 0
> and inverting the ladder.

> **Implementation status (2026-09-10):** billing for credential-free tenants at any tier is
> unblocked by T0-1…T0-4; the SPC citation surface on `/v1` is T0-5 and is **not built yet**.
> See `docs/b2b-core/TIER0-RETRIEVAL-FREE.md`. Do not contract the SPC-citation capability
> before T0-5 ships. Decisions **D-20** (this tier's name and price) and **D-21** (the 409
> envelope) are recorded there.

### Tier 1 — Core · €15 / location / month

The "cheaper than building it yourself" tier. Covers the full Pharmapi retrieval layer and
the safety engine — everything a company would need 3–6 months of engineering to replicate,
plus the clinical rule layer they could not build at all.

Includes: everything in Clinical-only, plus **Pharmapi Proxy (retrieval)** and **Formulary
Substitution**.

### Tier 2 — Clinical · €32 / location / month

Everything in Core, plus the agentic clinical intelligence layer. This is where PharmAssist's
differentiation is clearest — no Greek pharmacy software competitor offers this via API at any
price point.

Adds: **Agentic SPC Contraindication Lookup**, **AI Safety Flag Explanations**, **SPC Q&A
(RAG)**, **Medication Adherence Signals**, **ADR Reporting**, **AI ADR Narrative Drafting**,
**Patient Condition Inference**.

### Tier 3 — Platform · €48 / location / month

Everything in Clinical, plus network-scale intelligence features that are only possible at
multi-location scale. These features become more valuable as the customer's network grows.

Adds: **Pharmacovigilance Signal Detection**, **Drug Recall Webhook**, **Reaction Network
Alert Agent**, **Insurance Pre-Authorization Agent**.

### B2B Feature Matrix

| Feature | Clinical-only | Core | Clinical | Platform |
|---|---|---|---|---|
| Patient lookup (AMKA / EKAA) | — | ✅ | ✅ | ✅ |
| Prescription retrieval (barcode + search) | — | ✅ | ✅ | ✅ |
| Patient insurance details | — | ✅ | ✅ | ✅ |
| Patient intolerances (ΗΔΥΚΑ) | — | ✅ | ✅ | ✅ |
| Patient medicine history (ΗΔΥΚΑ) | — | ✅ | ✅ | ✅ |
| Drug catalog / masterdata | ✅ | ✅ | ✅ | ✅ |
| Pharmapi error handling & session management | — | ✅ | ✅ | ✅ |
| Drug-drug interaction checking | ✅ | ✅ | ✅ | ✅ |
| Duplicate therapy detection | ✅ | ✅ | ✅ | ✅ |
| Patient condition-based alerts | ✅ | ✅ | ✅ | ✅ |
| Patient conditions CRUD | ✅ | ✅ | ✅ | ✅ |
| Formulary substitution | — | ✅ | ✅ | ✅ |
| Agentic SPC contraindication lookup | — | — | ✅ | ✅ |
| AI safety flag explanations (Greek) | — | — | ✅ | ✅ |
| SPC Q&A / RAG | — | — | ✅ | ✅ |
| Medication adherence signals | — | — | ✅ | ✅ |
| ADR reporting endpoints | — | — | ✅ | ✅ |
| AI ADR narrative drafting | — | — | ✅ | ✅ |
| Patient condition inference | — | — | ✅ | ✅ |
| Pharmacovigilance signal detection | — | — | — | ✅ |
| Drug recall webhook | — | — | — | ✅ |
| Reaction network alert agent | — | — | — | ✅ |
| Insurance pre-auth agent (ΕΟΠΥΥ) | — | — | — | ✅ |

### B2B Pricing Summary

| Tier | Per location / month | 1,000 locations / month | Annual |
|---|---|---|---|
| Clinical-only | €9 | €9,000 | €108,000 |
| Core | €15 | €15,000 | €180,000 |
| Clinical | €32 | €32,000 | €384,000 |
| Platform | €48 | €48,000 | €576,000 |

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
€48,000 × 12 × 3 × 0.80 = ~€1.38M + onboarding.

---

## Motion B — B2C Direct (Counter Safety Companion)

**Billing unit:** per seat / month, where **a seat is one pharmacist**. A single pharmacy can
hold **multiple seats** — one per pharmacist who needs to log in. **Target:** individual
pharmacies of any size, **on any dispensing ERP** — PharmAssist rides alongside whatever they
already run. **Delivery:** the **counter agent** (a lightweight local app that watches
prescription scans in the pharmacy's existing software and surfaces safety alerts the moment
the barcode is read) plus the **review console** (web app: full prescription review, safety
checks, SPC lookups, patient profile & conditions, flag-discrepancy / contact-prescriber,
ADR reporting, documentation log with export).

This is the decisive difference from a dispensing-system sale: **there is nothing to
replace**. The pharmacy keeps its ERP, its workflow, and its muscle memory; PharmAssist adds
the clinical safety layer none of the incumbent ERPs provide. Adoption is an install, not a
migration — which also means the trial-to-paid path is measured in days, not quarters.

### How seats work

- The **first seat** activates the pharmacy account and includes ΗΔΥΚΑ retrieval onboarding
  and the counter-agent installation.
- Each **additional pharmacist** is added as a seat via the in-app invite flow (the pharmacy
  admin invites a pharmacist by email; the pharmacist accepts and links to the pharmacy).
- Seats are billed monthly; a pharmacy adds or removes seats as its team changes.

### Tier 1 — Essential · €29 / seat / month

The counter safety layer. Everything a pharmacy needs to catch the dangerous prescription
before it is dispensed — in their own software.

Includes:

- **Counter agent** — scan-time safety alerts riding the pharmacy's existing ERP, one-key
  handoff into the review console
- **Prescription review** — barcode / scan lookup with full prescription detail from ΗΔΥΚΑ
  (incl. paperless), pending + history search
- **Safety Engine** — drug-drug interactions, duplicate therapy, condition-based
  contraindications, severity grading
- **Patient profile, history & conditions** — demographics, Rx history, allergies /
  intolerances, safety flags
- **Flag discrepancy / contact prescriber** — structured triage with physician notification
- **Patient Instructions** — Greek / English counselling notes, print or digital
- **Documentation / legal audit log** — every review, flag, and counselling action recorded
  with safety snapshot; PDF / CSV export

### Tier 2 — Clinical · €55 / seat / month

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
| Onboarding | €290 one-time (ΗΔΥΚΑ setup + agent install + 2h training), **waived on annual prepay** |

### B2C Feature Matrix

| Capability | Essential | Clinical |
|---|---|---|
| Counter agent (scan-time alerts in the pharmacy's own ERP) | ✅ | ✅ |
| Prescription review (barcode + search, incl. paperless) | ✅ | ✅ |
| Safety engine (interactions, duplication, contraindications) | ✅ | ✅ |
| Patient profile, history & conditions | ✅ | ✅ |
| Flag discrepancy / contact prescriber | ✅ | ✅ |
| Patient instructions (Greek / English) | ✅ | ✅ |
| Documentation / legal audit log + export | ✅ | ✅ |
| SPC Q&A / RAG · Agentic SPC lookup | — | ✅ |
| AI safety flag explanations | — | ✅ |
| ADR reporting + AI ADR narrative | — | ✅ |
| Patient condition inference | — | ✅ |
| Medication adherence signals | — | ✅ |

> **Implementation note (B2C):** the review console (prescription review, safety engine,
> patient/ADR/documentation and instructions surfaces) is live today; the counter agent is
> in pilot. Several Clinical-tier AI capabilities are rolling out — confirm current
> availability with the customer before contracting the Clinical tier.

### B2C Worked Examples

Monthly figures are before the annual-prepay discount. The seats-4+ volume break applies
−15% to the per-seat rate from seat 4 onward; the **Annual** column then applies a further
−15% to the resulting 12-month total.

**Essential — €29 / seat / month** (seats 4+ at €24.65)

| Pharmacy size | Seats | Monthly | Annual (−15%) |
|---|---|---|---|
| Solo | 1 | €29.00 | €295.80 |
| Small team | 3 | €87.00 | €887.40 |
| Larger team | 5 | €136.30 (3×€29 + 2×€24.65) | €1,390.26 |

**Clinical — €55 / seat / month** (seats 4+ at €46.75)

| Pharmacy size | Seats | Monthly | Annual (−15%) |
|---|---|---|---|
| Solo | 1 | €55.00 | €561.00 |
| Small team | 3 | €165.00 | €1,683.00 |
| Larger team | 5 | €258.50 (3×€55 + 2×€46.75) | €2,636.70 |

### Competitive positioning (vs. incumbent ERP — e.g. PYLON Farmakon)

A Greek pharmacy ERP today is sold as a perpetual licence (≈€950 core including **one** user,
**+€150 per extra seat**, ≈€264–340/yr support, +€130 install). PharmAssist B2C is **not a
competitor to that purchase** — it is the layer the ERP does not have:

- **Complements, never replaces** — the pharmacy keeps its ERP for dispensing, inventory,
  POS, and accounting. PharmAssist adds what no incumbent offers: scan-time clinical safety,
  AI clinical intelligence, and a compliance-grade documentation trail.
- **Zero switching cost** — no data migration, no workflow change, no ΗΔΥΚΑ re-registration.
  Install the agent, sign in, done.
- **SaaS, no upfront capEx** — monthly per-seat, cancel or scale seats anytime; priced so a
  solo pharmacy pays less than a phone bill for a second pair of clinical eyes on every scan.

---

## Cross-cutting Notes

**On the 609 / ΗΔΥΚΑ permission requirement:** Patient intolerances and medicine history
require the pharmacy's ΗΔΥΚΑ accounts to be in the ΕΟΠΥΥ category (`isIka = true`). Pharmacy
70466 in the current test environment is not ΕΟΠΥΥ. For production, customers must obtain this
category through ΗΔΥΚΑ (Hd@idika.gr). PharmAssist cannot grant this permission. (Applies to
both motions.)

**On prescription execution (why it is not in the catalog):** PharmAssist deliberately does
not execute/dispense prescriptions. The pharmacy's own dispensing system remains the system
of record for the transaction and its regulatory obligations (eDispensation, EU-FMD/HMVS
decommissioning). This keeps PharmAssist's integration liability-free for the customer and
its adoption friction near zero. A complete, previously HMVO-reviewed execution
implementation is preserved at git tag `hmvs-certified` should the packaging ever change.

**On pharmacovigilance signal detection (B2B Platform tier):** Signal quality is directly
proportional to network data volume. For the first 6 months of a Platform contract, an
introductory rate of €40/location/month is recommended, stepping automatically to the full
€48 rate at month 7. This should be written into the contract rather than offered as a
negotiated concession.

**On AI features (B2B Clinical/Platform and B2C Clinical):** AI features (safety
explanations, SPC Q&A, ADR narrative drafting, condition inference) depend on an EU-region LLM
provider endpoint with a GDPR Data Processing Agreement in place. No patient PII (AMKA, name,
address) is transmitted to the LLM — prompts are constructed from clinical data only (drug
codes, ATC classes, rule descriptions, anonymised demographics).
