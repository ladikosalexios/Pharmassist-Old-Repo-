# Tier-2 B2B "Clinical" — gap audit + tickets (Core → the €32 tier, sellable on /v1)

**Status:** 📋 **Phase 0 — audit + ticket set, awaiting review.** Plan only; zero code
changes ride this doc.
**Date:** 2026-06-10
**Baseline:** `main` @ 29d74ea (#138) — Tier-1 finished through FINISH-TIER1 Batch 2;
228 backend tests green incl. the /v1 suite (`tests/test_v1_*.py`, 10 files), B2C
untouched throughout.
**Scope driver:** `docs/PharmAssist_Pricing.md` → Motion A, Tier 2 "Clinical"
(€32/location/month, `PharmAssist_Pricing.md:212-220`) + the matching Shared Capability
Catalog entries (`:75-129`) and the cross-cutting AI note (`:436-440`).
**Constraint:** B2C stays untouched and green. Every ticket below is additive — new
modules, new tables, new /v1 routes; **no ticket modifies a B2C code path** (the engine
seam `evaluate_safety(..., patient_conditions=)` built for D-3 is consumed, not changed —
`services/safety_engine.py:128-154`).
**Numbering:** tickets are T2-*n*; decisions continue FINISH-TIER1's D-8…D-13 as
**D-14…D-19**.

Audited 2026-06-10 against the live codebase (5-agent sweep, load-bearing claims
re-verified by hand); every status claim carries file:line evidence, same discipline as
the BC and FT audits.

The seven capabilities Tier-2 adds over Core (`PharmAssist_Pricing.md:218-220`):
**Agentic SPC Contraindication Lookup**, **AI Safety Flag Explanations (Greek)**,
**SPC Q&A (RAG)**, **Medication Adherence Signals**, **ADR Reporting**,
**AI ADR Narrative Drafting**, **Patient Condition Inference**.

---

## 0. What "Tier-2 complete + sellable on /v1" means

1. **All seven catalog capabilities callable on /v1**, consistent with Core: X-API-Key
   auth (`routers/v1/deps.py:52-112`), location-scoped, error-enveloped
   (`routers/v1/errors.py`), per-key rate-limited (`deps.py:71-82`), mock-paritied
   (`services/v1_mock.py` pattern), contract-tested (`tests/test_v1_*.py` patterns).
2. **Tier-gated**: a Core-only key 403s (in the envelope) on every Clinical route; the
   tier is provisionable via `b2b_admin` and visible on `GET /v1/status`. Without this
   the €32-vs-€15 delta is uncollectable — today **no tier concept exists anywhere**
   (§1/E1).
3. **AI features run against an EU-region LLM under a GDPR DPA with a hard PII
   boundary** — no AMKA/name/address ever reaches a prompt
   (`PharmAssist_Pricing.md:436-440`). Deterministic surfaces (safety check, formulary,
   ADR CRUD) never degrade when the LLM is down.
4. **SPC features answer from a real Greek ΠΧΠ corpus with exact section citations** —
   not the current two-drug fixture (§1/#1).
5. **Every AI/agentic output is structurally decision support** — draft flags,
   suggestions-only semantics, source citations, refusal over free-generation
   ("suggests, never decides"; §1/E4).
6. **B2C untouched and green**; mock mode and the FT-13 sandbox semantics keep working
   (AI features need their own deterministic mock).
7. **The paper keeps up**: `DATA-PROCESSING.md` gains the LLM subprocessor (explicitly
   deferred to Tier-2 by FT-14), `API.md`/`openapi-v1.json`/Postman cover the new
   surface.

---

## 1. Audit — Tier-2 capability vs what exists today

| # | Capability (pricing doc) | Status | Evidence |
|---|---|---|---|
| 1 | Agentic SPC Contraindication Lookup | **STUB** (UI reference fixture; nothing agentic) | `services/spc.py` is a 102-line hardcoded `MOCK_SPC` dict covering exactly **two** drugs — B01AA03 Warfarin (`spc.py:4-59`) and J01CA04 Amoxicillin (`spc.py:60-102`) — served by one B2C-cookie-authed endpoint `GET /spc/{atc_code}` (`routers/spc.py:11-17`, `get_current_user`). 100% static: no fetch from ΕΟΦ/EMA/ΗΔΥΚΑ (the `fullSpcUrl`s are decorative — `spc.py:12`, `:65`). The safety engine never reads SPC data (zero SPC references in `services/safety_engine.py`). Zero tests touch `/spc`. The pricing capability — per-prescription checks citing exact SPC sections, special-population warnings, severity + recommended action (`PharmAssist_Pricing.md:75-85`) — exists nowhere. |
| 2 | AI Safety Flag Explanations (Greek) | **MISSING** (deterministic English foundation **EXISTS**) | What exists: `_rule_to_alert` copies static DB rule text into every alert (`services/safety_engine.py:51-63`); the columns are **English-only** — `message_en` / `details_en` / `recommended_action_en` (`db/models/safety_rule.py:25-27`), no `*_gr` columns; 18 seeded rules (`scripts/seed_data.py:184-510`); the /v1 surface already returns these texts (`routers/v1/safety.py:55`, payload fields `schemas/safety.py:10-22`). What's missing: any LLM, any Greek rationale (mechanism/risk/alternatives), and the rule+condition-profile cache the catalog promises (`PharmAssist_Pricing.md:87-92`). |
| 3 | SPC Q&A (RAG) | **MISSING** | No corpus, no embeddings, no vector store, no LLM: clean greps for pgvector/vector/embedding/rag/chroma/qdrant/faiss/milvus and openai/anthropic/langchain/litellm/etc. across backend, frontend, compose and scripts (only hits: Claude Code CI workflows in `.github/`, not app code). `backend/requirements.txt` carries zero AI deps (httpx is the only HTTP client); compose runs only frontend / backend / `postgres:16-alpine` / adminer (`compose.yaml:2-64`); `app/config.py` Settings (`:105-212`) has no AI field of any kind. |
| 4 | Medication Adherence Signals | **MISSING** (and the obvious raw material is **B2C-only**) | Zero adherence/refill/MPR/PDC code anywhere. The local dispense history — `dispense_logs` (`db/models/dispense_log.py:31-55`, per-pharmacy index `:29`) and `documentation_logs` (patient_amka+dispensed_at index, `documentation_log.py:23-25`) — FKs into B2C `pharmacies`/`pharmacists`, and **/v1 has no dispense surface at all** (execution is the Tier-3 add-on). A B2B tenant therefore generates **no local dispensing data**; the only available signal source is upstream medicine history (`routers/v1/patients.py:131-164`), which is consent- **and ΕΟΠΥΥ-gated** (`:70-84`) → D-19. The catalog wants ON_TRACK/OVERDUE/LAPSED + days-since-expected-refill (`PharmAssist_Pricing.md:102-108`). |
| 5 | ADR Reporting | **EXISTS (B2C)** / **MISSING on /v1** | B2C is complete and live: service `services/side_effects.py` (275 lines — state machine `next_status` `:125-130`, live create + audit event in one transaction `:229-275`, stats `:115-122`); router `routers/side_effects.py` (GET list `:39-78`, POST 201 `:81-117`, POST `/{id}/flag` `:120-155`); vocabularies `constants.py:11-33`; models `adr_report.py` + `adr_event.py`; wired frontend (`frontend/src/pages/SideEffects.tsx`, api calls `frontend/src/lib/api.ts:443-487`). Zero /v1 footprint (no adr/side_effect/adverse match under `routers/v1/`, `services/v1_mock.py`, or `tests/test_v1_*`). Four corrections vs the quick recon: (a) a **fourth status `CLOSED`** exists (`constants.py:15`) but is unreachable from `next_status`; (b) `eof_report_ref` exists but is **never written** — `EOF_REPORTED` is a label, not an ΕΟΦ integration (`adr_report.py:41`); (c) the pricing's "query by patient, drug, or date range" (`PharmAssist_Pricing.md:114`) is not delivered **even in B2C** — the list supports free-text `q` + sort only (`routers/side_effects.py:39-78`); (d) `pharmacist_id`/`pharmacy_id` are **NOT NULL FKs** (`adr_report.py:20-24`), so B2B cannot reuse the table without touching B2C → D-3-style separate table (T2-3). Lift ≈ productize + a tenancy-table build. |
| 6 | AI ADR Narrative Drafting | **MISSING** | No narrative/draft code anywhere in the ADR flow (grep clean across service/router/models); the only free text is `symptom_description` (`adr_report.py:32`) and an unused `notes` on events (`adr_event.py:30`). Greenfield on the LLM seam (E2). Catalog: draft formatted for ΕΟΦ submission, always human-reviewed (`PharmAssist_Pricing.md:116-121`). |
| 7 | Patient Condition Inference | **MISSING** | The only "infer" matches in app code are tenant-isolation docstrings (`db/models/b2b_patient_condition.py:3`, `services/b2b_conditions.py:4`). No ATC→condition knowledge exists anywhere — `drug_catalog` rows carry ATC/class/strength/coverage but nothing condition-shaped (`db/models/drug_catalog.py:11-46`). The **write-back target already exists**: /v1 conditions CRUD (`routers/v1/patients.py:170-239`, service `services/b2b_conditions.py:27-133`) feeding the engine seam (`safety_engine.py:128-154`, condition matching `:221-239`). Catalog: suggestions + HIGH/MEDIUM confidence + drug evidence, caller confirms (`PharmAssist_Pricing.md:123-129`). |
| E1 | Tier entitlement + gating (cross-cutting, blocks everything) | **MISSING** | Zero tier/plan/entitlement columns anywhere in the tenancy models (grep clean; `db/models/api_key.py:16-30`, `customer.py:15-24`, `location.py:17-41`; tenancy migration `f2a8c4d91b03` adds none). An API key resolves to a location with no plan concept (`routers/v1/deps.py:52-112`, `ApiContext` `:39-49`). The only per-location feature gate is `is_eopyy` (`location.py:36-38`) enforced as `_require_eopyy` → 403 in the envelope (`routers/v1/patients.py:77-84`) — exactly the pattern a tier gate should mirror. Today **every active key reaches every /v1 route**. |
| E2 | LLM integration seam (EU + PII boundary) | **MISSING** | See #3. Binding constraints from the pricing doc: EU-region provider endpoint + GDPR DPA; **no patient PII (AMKA, name, address) transmitted to the LLM** — prompts from drug codes/ATC classes/rule descriptions/anonymised data only (`PharmAssist_Pricing.md:436-440`). `docs/b2b-core/DATA-PROCESSING.md` explicitly scoped LLM subprocessors out at Tier-1 ("no LLM processors at Tier-1… bites at Tier-2" — FINISH-TIER1 FT-14) — it must be amended when the first AI feature ships (T2-12). |
| E3 | SPC corpus (+ vector store for #3) | **MISSING** | See #1/#3: the only SPC "data" is the two-drug fixture; no document store, no ingestion, no embeddings, no vector extension/sidecar. #1 and #3 both die without this; #3 additionally needs embeddings + retrieval (D-16/D-17). |
| E4 | Clinical-safety framing ("suggests, never decides") | **CONVENTION EXISTS — must be encoded per feature** | The honest-decision-support register already lives in Core: `dataCaveats` + "absence of an alert ≠ safe" (`routers/v1/safety.py:42-46`; formulary `dataCaveats`). Tier-2 response schemas must carry it **structurally**: `draft: true` + disclaimer on the ADR narrative (T2-7), suggestions-only with no write side-effect on inference (T2-5), exact section citations + refusal-on-empty-retrieval on SPC Q&A (T2-9), explicit caveats on adherence heuristics (T2-4). |

**Audit surprises that shaped the plan:**

- **The adherence/inference data-source trap.** Both #4 and #7 are specified over
  "dispensing history" — but the local dispense tables are B2C-only and /v1 has no
  dispense surface (Tier-3 add-on). The only B2B source is ΗΔΥΚΑ medicine history, which
  drags in the consent attestation **and the ΕΟΠΥΥ/609 gate**
  (`routers/v1/patients.py:70-84`): **a non-ΕΟΠΥΥ location cannot be sold adherence
  signals or condition inference at all** as currently designed. That's a sellability
  constraint the pricing/onboarding docs must state (D-19, T2-4/T2-5).
- **ADR-on-/v1 is not a pure productize.** The B2C table's NOT-NULL pharmacist/pharmacy
  FKs force a D-3-style `b2b_adr_reports` table, and the catalog's promised query
  filters (patient / drug / date range) don't exist even in B2C — they're new code on
  the /v1 router (T2-3).
- **`EOF_REPORTED` is a label, not an integration** — `eof_report_ref` is never written
  and no ΕΟΦ submission call exists. The /v1 API docs must keep this honest (status
  tracking, not regulator transmission); actual ΕΟΦ submission stays out of scope (§5).
- **The tier gate is the only thing between a Core key and Tier-2 revenue** — and no
  tier concept exists in any model, migration, or dependency. E1/T2-1 is foundational
  and blocks every other ticket's "sellable" AC.
- **The agentic-lookup pricing copy assumes push.** "On every prescription submitted, a
  background agent reads the full SPC" (`PharmAssist_Pricing.md:77-78`) — on an API-only
  motion there is no "prescription submitted" event on our side; the caller invokes the
  check. T2-10 delivers it as an on-demand endpoint; the pricing line needs the same
  one-line honesty fix register as D-6 (or a webhook variant priced into Tier-3).
- **There is a no-LLM fallback for Greek explanations — but it under-delivers.** Static
  `message_gr` columns + seed translations would put Greek text on the 18 seeded rules
  without any LLM. The catalog, however, promises rationale **per rule + patient
  condition profile** (`PharmAssist_Pricing.md:92`) — context-aware text static columns
  can't produce. Noted in T2-6 as a degraded fallback, not the deliverable.

---

## 2. Tickets

Sizing vocabulary (same as FINISH-TIER1): **days** = 0.5–2 dev-days (ranges up to ~4
where noted); **week** = 3–5+ dev-days. Estimates assume one dev who knows the codebase,
tests included. Every endpoint ticket implicitly includes: tier gate (T2-1), envelope
errors, per-key rate limit (inherited from `get_api_context`), mock parity fixture,
contract + tenant-isolation tests, and an `openapi-v1`/`API.md`/Postman delta (rolled up
in T2-11).

### A — Foundations (block everything)

---

**T2-1 · Tier entitlement model + /v1 tier gate** — *build* · **days (1–2)** — blocked by D-14

- `locations.tier` (`core | clinical | platform`, server_default `'core'`) + migration
  (BEFORE-UPDATE trigger + three-place model registration per BC-1's checklist);
  backfill existing rows `core`.
- `ApiContext` gains `tier` (`routers/v1/deps.py:39-49`); a `require_tier("clinical")`
  dependency/helper mirroring `_require_eopyy` (`routers/v1/patients.py:77-84`) returns
  **403 in the envelope** — recommend a new stable code `tier_required` added to the
  code table (`routers/v1/errors.py:32-41`; additive, so the BC-5 contract holds).
- `GET /v1/status` echoes the tier (`routers/v1/__init__.py:23-39`); `b2b_admin`
  `create-location --tier` + `set-tier` (CLI pattern `scripts/b2b_admin.py`);
  `ONBOARDING.md`/`KEY-MANAGEMENT.md` gain the tier step.
- AC: a `core` key 403s with the envelope on a gated route while a `clinical` key
  passes; tier visible on `/v1/status`; existing /v1 + B2C suites green; contract test
  pins the 403 body.

**T2-2 · LLM integration seam: EU provider client, PII boundary, mock, cache** — *build* · **week (3–5)** — interface now; live provider after D-15

- `app/services/llm.py`: provider-agnostic async client (httpx, same conventions as
  `services/pharmapi.py`). Settings: `LLM_API_BASE` / `LLM_API_KEY` / `LLM_MODEL`
  (+ embeddings equivalents for T2-9). Checked **at first use** like
  `CREDENTIAL_ENCRYPTION_KEY` — not a boot fail-fast (a Tier-1-only deployment must boot
  without AI config).
- `LLM_MOCK` toggle, boot-validated alongside `PHARMAPI_MOCK` (FT-15's
  `RECOGNIZED_MOCK_TOKENS` pattern): deterministic canned outputs per prompt kind →
  contract tests, mock parity, and the FT-13 sandbox story all keep working with zero
  upstream calls.
- **Hard PII boundary**: prompts are constructed only through typed builders whose
  input schemas accept whitelisted clinical fields (ATC codes, rule text, condition
  codes, symptom text, anonymised age/sex bands) — structurally no AMKA/name/address
  field exists; plus a belt-and-braces guard test that scans every built prompt for
  AMKA-shaped (11-digit) tokens before dispatch. Caveat to document (and carry into
  T2-12): pharmacist-entered free text (e.g. `symptom_description`,
  `adr_report.py:32`) can embed identifiers — the DPA annex must state it is relayed
  as caller-supplied content, and the prompt builders should still run the digit-token
  scrub over it.
- Response cache primitive (`ai_response_cache` table: key hash, prompt kind, payload,
  created_at) — the catalog requires caching by rule + condition profile
  (`PharmAssist_Pricing.md:92`); a DB table (not in-process) survives restarts and the
  single-worker constraint, and gives T2-12 a retention line item.
- Failure semantics: LLM timeout/5xx → envelope `ai_unavailable` (new additive code) on
  AI endpoints only; deterministic endpoints never call the seam.
- AC: PII guard unit tests (a prompt assembled with an AMKA-shaped token is refused);
  mock determinism test; timeout → envelope test; grep shows zero `llm` import from any
  Tier-1 module.

### B — Productize what exists

---

**T2-3 · ADR reporting on /v1** — *productize + tenancy build* · **days (2–3)** — after T2-1

- `b2b_adr_reports` + `b2b_adr_events` tables — D-3 precedent verbatim: the B2C FKs are
  NOT NULL into `pharmacists`/`pharmacies` (`adr_report.py:20-24`), so a separate
  location-scoped pair (`location_id` FK, `created_via_api_key_id`, same
  status/severity/causality vocabularies from `constants.py:11-33`, same `next_status`
  chain semantics as `services/side_effects.py:125-130`, event row per transition
  mirroring `adr_event.py:13-34`) keeps B2C untouched. Flag at review if you want a
  shared-table refactor instead — not recommended, same reasons as D-3.
- Endpoints: `POST /v1/adr-reports` (201) · `GET /v1/adr-reports` with the
  catalog-promised filters — `amka`, `atc`/`barcode`, `from`/`to`, `status`, paginated
  (`PharmAssist_Pricing.md:114`; **new code** — B2C only has free-text `q` + sort,
  `routers/side_effects.py:39-78`) · `GET /v1/adr-reports/{id}` ·
  `POST /v1/adr-reports/{id}/transition` (state machine + event row).
- `EOF_REPORTED` stays a tracked status; `eof_report_ref` caller-supplied/optional;
  API.md states plainly that PharmAssist does not transmit to ΕΟΦ (§5).
- Mock fixtures in the `v1_mock.py` pattern; tier-gated `clinical`.
- AC: contract suite (incl. each filter), tenant isolation (location A cannot read/
  transition B's reports), state-machine test (illegal transition → 409 envelope), mock
  parity; B2C `side_effects` suite untouched and green.

### C — Deterministic clinical builds (no LLM)

---

**T2-4 · Medication adherence signals** — *build* · **days (3–4)** — after T2-1, D-19

- `GET /v1/patients/{key}/adherence?patientConsent=true` → per long-term medication:
  `{atcClass, lastDispense, expectedRefill, daysSinceExpected, status:
  ON_TRACK|OVERDUE|LAPSED, evidence, dataCaveats}` (`PharmAssist_Pricing.md:102-108`).
- Source per D-19 (recommended: upstream medicine history) — rides the existing consent
  + ΕΟΠΥΥ gates (`routers/v1/patients.py:70-84`, `:131-164`). **Consequence stated in
  API.md + ONBOARDING.md: non-ΕΟΠΥΥ locations 403 on adherence** (609 rule).
- Long-term classes = curated ATC prefix set matching the pricing list exactly
  (`PharmAssist_Pricing.md:104-105`): B01A anticoagulants, C02/C03/C07/C08/C09
  antihypertensives, A10 insulin/antidiabetics, C10 statins, N06A antidepressants.
- Expected-refill heuristic: median observed inter-dispense interval per ATC (needs ≥2
  dispenses), `package_size` (`db/models/drug_catalog.py:45`) as a secondary signal.
  **Honest by construction**: we hold no posology/supply-days data, so thin histories
  emit `dataCaveats` ("single dispense — cadence unknown") instead of a fabricated
  status.
- AC: unit tests on synthetic histories (on-track / overdue / lapsed / single-dispense
  → caveat, never a status); tier + consent + ΕΟΠΥΥ gate contract tests; mock fixture
  with a deterministic OVERDUE patient.

**T2-5 · Patient condition inference (rule-based v1)** — *build* · **days (2–4)** — after T2-1, D-18

- `GET /v1/patients/{key}/condition-suggestions?patientConsent=true` →
  `{suggestions: [{conditionCode, name, confidence: HIGH|MEDIUM, evidence: [drugs]}],
  suggestionsOnly: true, dataCaveats}` (`PharmAssist_Pricing.md:123-129`).
- New curated ATC→condition mapping (seeded table `condition_inference_rules` in the
  `seed_data.py` register — the drug catalog has no condition knowledge,
  `drug_catalog.py:11-46`). Map onto the **existing condition vocabulary** the safety
  rules consume (`safety_rule.py:22` `trigger_condition_code`: DIABETES_T2,
  RENAL_SEVERE, PREGNANCY, G6PD, …) so a confirmed suggestion immediately arms
  contraindication checks. Confidence from evidence strength (e.g. A10 ≥2 dispenses →
  DIABETES_T2 HIGH).
- Input: upstream medicine history — same consent/ΕΟΠΥΥ gates and the same non-ΕΟΠΥΥ
  sellability consequence as T2-4.
- **Never writes**: caller confirms via the existing
  `POST /v1/patients/{key}/conditions` (`routers/v1/patients.py:180-204`). E4 framing
  structural in the schema (`suggestionsOnly: true`).
- AC: deterministic tests on fixture histories; an explicit no-write assertion (DB
  unchanged after the call); tier/consent/ΕΟΠΥΥ gates; mock parity.

### D — AI builds (need T2-2)

---

**T2-6 · AI safety flag explanations (Greek)** — *build* · **days (2–3)** — after T2-1, T2-2

- `POST /v1/safety/explain`: body = `ruleCodes` (+ optional condition codes) →
  `{explanations: [{ruleCode, language: "el", rationale, mechanism, riskLevel,
  alternatives, cached}]}`. A **separate endpoint** so `POST /v1/safety/check`
  (`routers/v1/safety.py:55`) keeps its deterministic latency and never blocks on an
  LLM.
- Prompt inputs: rule fields only — `message_en`/`details_en`/`recommended_action_en`
  (`safety_rule.py:25-27`), trigger/conflicting ATCs, condition codes. Zero patient
  identity by construction (T2-2 builders). The LLM generates the Greek clinical
  rationale from the English rule text + ATC context — no schema change to
  `safety_rules` needed.
- Cached by `(rule_code, sorted condition-profile)` per the catalog
  (`PharmAssist_Pricing.md:92`) via T2-2's cache; degraded fallback noted (static
  `*_gr` seed translations) under-delivers the condition-aware promise — not the
  deliverable.
- AC: cache-hit test (second identical call makes zero LLM calls); PII guard test;
  `LLM_MOCK` canned Greek per seeded rule (mock parity); tier gate; `check` endpoint
  byte-identical before/after.

**T2-7 · AI ADR narrative drafting** — *build* · **days (2–3)** — after T2-2, T2-3

- `POST /v1/adr-reports/{id}/narrative` → `{draft: true, language, narrative,
  disclaimer, generatedAt}` — ΕΟΦ-submission-style clinical narrative, **always a
  draft** (`PharmAssist_Pricing.md:116-121`): no status transition, no persistence as
  the report's text (regenerate on demand; the report row is untouched).
- Prompt from the structured ADR fields **minus** `patient_name`/`patient_amka`
  (`adr_report.py:26-27`): drug/ATC, symptom, onset, severity, causality.
  `symptom_description` free text rides the T2-2 scrub + DPA caveat.
- AC: response always carries `draft: true` + disclaimer; report status/row unchanged
  after the call; PII guard test; mock parity; tier gate.

### E — SPC corpus + features

---

**T2-8 · SPC corpus: sourcing, ingestion, structured sections** — *build* · **week (1–2, format-dependent)** — after D-16

- Real Greek ΠΧΠ source per D-16 (ΕΟΦ's SPC repository — the fixture already points at
  `eof.gr` URLs, `spc.py:12` — plus EMA for centrally-authorised products);
  licensing/ToS cleared **before** any scraping.
- `spc_documents` (barcode/ATC link, version, source URL, fetched_at) +
  `spc_sections` (doc FK, `section_ref`, title, text). SPC sections are standardised
  (4.3 contraindications, 4.4 special warnings/populations, 4.5 interactions, 4.6
  pregnancy/lactation) — which is exactly what makes #1's "exact SPC section cited"
  deliverable.
- Ingestion script + sync-status row (FT-4's `catalog_sync_runs` pattern); update
  cadence documented in OPERATIONS.md.
- B2C `/spc` keeps serving the fixture (`services/spc.py`) — migrating it onto the
  corpus is a separate, later B2C ticket (out of scope here, §5).
- Sizing honesty: a week if a clean structured source exists; 2+ if it's heterogeneous
  PDF scraping. D-16 decides which world we're in.
- AC: N real drugs ingested with all four key sections segmented; re-ingest is
  idempotent; sync failures surface in the status row.

**T2-9 · SPC Q&A (RAG) on /v1** — *build* · **week (3–5)** — after T2-2, T2-8, D-17

- Embeddings over `spc_sections` chunks (corpus is non-PII, but stay EU per D-15);
  pgvector per D-17 (compose has no sidecar today, `compose.yaml:2-64` — the
  `postgres:16-alpine` image swaps to a pgvector-enabled build in dev + prod compose, an
  operational note for the ticket).
- `POST /v1/spc/qa` `{barcode|atc, question}` → `{answer, language, sources:
  [{sectionRef, excerpt}], disclaimer}` — Greek queries supported
  (`PharmAssist_Pricing.md:94-100`). Retrieval scoped to the named drug's document
  (structural guard against cross-drug answers); **empty retrieval → explicit "not
  addressed in the SPC" refusal**, never free generation (E4).
- AC: grounding test (answer cites a real ingested section); empty-retrieval refusal
  test; Greek query fixture; mock parity (`LLM_MOCK` + fixture corpus); tier gate.

**T2-10 · Agentic SPC contraindication lookup on /v1** — *build* · **week (3–5)** — after T2-2, T2-8

- `POST /v1/spc/contraindication-check` `{medications: [{barcode|atc}], patientKey? |
  conditions?: [...]}` → `{findings: [{drug, sectionRef, findingText, severity,
  recommendedAction}], dataCaveats}` — the catalog's response contract verbatim
  (`PharmAssist_Pricing.md:75-85`).
- Pipeline: load the location's conditions for the patient (`b2b_patient_conditions`,
  location-scoped) → pull sections 4.3/4.4/4.5/4.6 per drug from the corpus → LLM
  extracts and matches contraindications + special-population warnings against the
  condition set → structured findings with exact section refs. Delivered **on-demand**
  (caller-invoked) — the pricing copy's push framing ("on every prescription submitted,
  a background agent") gets the D-6-register one-line reword, or a webhook variant
  priced later (§5).
- Complements, never replaces, the deterministic engine: response carries the
  absence-≠-safe caveat in the `routers/v1/safety.py:42-46` register.
- AC: a known seeded case (warfarin + PREGNANCY condition) surfaces a 4.3/4.6 finding
  with section ref; drug absent from corpus → explicit caveat finding, not silence; PII
  guard; mock parity; tier gate.

### F — Shell

---

**T2-11 · Tier-2 contract/docs/Postman shell** — *build* · **days (2–3 total, rides each batch)**

- Contract tests per the `tests/test_v1_*.py` conventions (env-before-import preamble,
  fake sessions for contract tier, real-DB isolation tests): per-endpoint shape +
  envelope, tier-gate matrix (core vs clinical key across every new route), tenant
  isolation incl. `b2b_adr_reports`, mock parity pinned for every new endpoint
  (AI endpoints pin `LLM_MOCK` outputs).
- `scripts/export_openapi_v1.py` picks up the new paths (verify the transitive schema
  pruning still excludes B2C); `API.md` gains: the tier model + `tier_required` code,
  AI failure modes (`ai_unavailable`), the consent/ΕΟΠΥΥ implications for
  adherence/inference, the draft/suggestions-only semantics; Postman collection +
  fixtures extended.
- AC: CI DB-less selection includes the new contract tier; an integrator can exercise
  every Tier-2 endpoint from Postman against the mock stack.

**T2-12 · DPA/data-processing annex: AI amendment** — *write* · **days (0.5–1)** — after D-15

- `DATA-PROCESSING.md` amendments FT-14 explicitly deferred to Tier-2: the LLM provider
  as subprocessor (EU region + DPA per D-15), the prompt PII boundary as a security
  measure (with the free-text caveat from T2-2), `ai_response_cache` contents +
  retention stance, `b2b_adr_reports` in the data inventory (stores patient_amka +
  patient_name + clinical narrative — a **larger stored-PHI surface than conditions**;
  set a retention stance).
- AC: annex matches the shipped code paths; handed to the D-13 legal owner (still TBD).

---

## 3. Decisions — needs Alex / the business

> Numbering continues FINISH-TIER1 (D-8…D-13). Each entry: technical context from this
> audit, a recommendation, and exactly what's needed.

### D-14 · Tier entitlement shape

**Context:** no tier/plan concept exists anywhere (§1/E1). Billing is per location
(`PharmAssist_Pricing.md:204-228`), and the codebase precedent for per-location gates is
a column + dependency check (`is_eopyy`, `location.py:36-38` →
`routers/v1/patients.py:77-84`).
**Recommendation:** a single `locations.tier` enum column (`core|clinical|platform`,
default `core`) + a `require_tier()` gate + a new `tier_required` envelope code. No
entitlement-matrix table until a customer actually needs per-feature grants — the tier
bundles are fixed in the pricing doc, and a column is a 30-minute migration away from a
matrix if that day comes. Customer-level tier rejected: pricing bills per location and
mixed estates (flagship locations on Clinical, rest on Core) are a plausible sale.
**Needed from you:** confirm location-level tier column + the new envelope code.

### D-15 · EU LLM provider + GDPR DPA — procurement

**Context:** zero AI deps/config/code today (§1/#3). The pricing doc binds us: EU-region
endpoint, GDPR DPA, no patient PII in prompts (`PharmAssist_Pricing.md:436-440`).
Engineering requirements on the pick: Greek output quality, JSON/structured output
support, an embeddings model (T2-9 — may be a second provider), EU data residency for
both. The seam (T2-2) is provider-agnostic, so interface work starts before the pick —
but **go-live of every AI feature gates on this**, and like D-13 the paper turnaround is
the long pole.
**Needed from you:** provider choice (e.g. Anthropic/OpenAI EU endpoints, Azure
OpenAI EU, Mistral) + who signs the DPA. This and D-16 are the two external clocks —
both can start today at zero engineering cost.

### D-16 · SPC corpus sourcing/licensing

**Context:** the only SPC data is a two-drug fixture whose `eof.gr` URLs are decorative
(`spc.py:12`, `:65`). #1 and #3 (and their tickets T2-8/9/10) need the real Greek ΠΧΠ
corpus. Candidate sources: ΕΟΦ's SPC repository (coverage of nationally-authorised
products; format/ToS/scraping permission unverified), EMA (centrally-authorised, public,
structured). Unknowns that set T2-8's size: format (HTML vs PDF), bulk access, update
cadence, redistribution/licensing terms.
**Recommendation:** a timeboxed probe (BC-13a register, ~0.5 day) of ΕΟΦ's portal
format + an explicit licensing question to ΕΟΦ in parallel; EMA ingestion as the
fallback start (legally clean, partial coverage).
**Needed from you:** approval to approach ΕΟΦ / accept the licensing risk posture.

### D-17 · Vector store: pgvector vs sidecar

**Context:** compose runs a single `postgres:16-alpine` (`compose.yaml:44-54`); no
vector infrastructure exists. Corpus scale is small (thousands of SPC documents ×
~10-20 sections → low tens of thousands of chunks) — far below where a dedicated vector
DB earns its operational cost.
**Recommendation:** **pgvector.** One database, Alembic-managed schema, no new service
in compose/prod, trivially inside the existing backup/restore story
(pilot-runbook cron). Cost: the postgres image swaps to a pgvector-enabled build (dev +
prod compose + a one-line migration `CREATE EXTENSION`). A sidecar (Qdrant et al.) only
if retrieval quality at scale demands it — revisit-trigger, not default.
**Needed from you:** confirm pgvector (affects the base image, so worth an explicit
yes).

### D-18 · Condition inference: rule-based or AI for v1

**Context:** the catalog promises suggested conditions + HIGH/MEDIUM confidence +
drug evidence (`PharmAssist_Pricing.md:123-129`). A curated ATC→condition map over
upstream medicine history delivers exactly that shape deterministically: explainable
evidence (the drug list **is** the evidence), zero PII exposure, zero LLM dependency,
testable, and it feeds the existing condition vocabulary so confirmed suggestions
immediately arm the safety engine (`safety_rule.py:22`).
**Recommendation:** **rule-based for v1** (T2-5). An LLM adds nothing to the response
contract here — the mapping is medical-reference knowledge, better curated than
generated. Revisit AI assist only if coverage of the curated map becomes the bottleneck.
**Needed from you:** confirm rule-based v1 (this also moves T2-5 off the T2-2/D-15
critical path entirely).

### D-19 · Adherence signal source: upstream history vs caller-pushed events

**Context:** §1/#4's trap — B2B tenants generate no local dispense data (dispense
tables are B2C-only, `/v1` has no dispense surface). Two candidate sources:
(a) **upstream ΗΔΥΚΑ medicine history** (`routers/v1/patients.py:131-164`) — complete
across all pharmacies the patient visits, but consent-gated per call and **unavailable
to non-ΕΟΠΥΥ locations** (609); (b) **caller-pushed dispense events**
(`POST /v1/dispense-events`) — works for any location and OS vendors who dispense in
their own system anyway, but only sees that customer's network and is a heavier
integration ask with data-quality risk.
**Recommendation:** **upstream history for v1** (T2-4) — it's the truthful,
whole-market signal and reuses gates that already exist. Document the non-ΕΟΠΥΥ
limitation in API.md/ONBOARDING.md and the pricing conversation. Caller-push becomes a
fast-follow if a non-ΕΟΠΥΥ or volume-sensitive customer needs it.
**Needed from you:** confirm source (a), and that the non-ΕΟΠΥΥ limitation is
acceptable to sell against.

---

## 4. Dependency order + sizing

```
Wave 0 (now, parallel):
  T2-1 tier model + gate (1-2d)        [after D-14 — a one-line confirm]
  [D-15 LLM procurement starts — external clock]
  [D-16 corpus probe + licensing ask — external clock; 0.5d probe]
  T2-2 LLM seam interface + mock (3-5d) [live provider wiring lands after D-15]

Wave 1 (deterministic, after T2-1 — no LLM, no corpus):
  T2-3 ADR on /v1 (2-3d)
  T2-4 adherence signals (3-4d)        [after D-19]
  T2-5 condition inference (2-4d)      [after D-18]

Wave 2 (AI on the seam, after T2-2 + D-15):
  T2-6 Greek safety explanations (2-3d)
  T2-7 ADR narrative drafting (2-3d)   [after T2-3]
  T2-12 DPA AI amendment (0.5-1d)

Wave 3 (corpus features, after D-16):
  T2-8 SPC corpus + ingestion (1-2w)
    └─→ T2-9 SPC Q&A RAG (3-5d)        [after D-17 + T2-2]
    └─→ T2-10 agentic SPC lookup (3-5d) [after T2-2]

Continuous: T2-11 contract/docs/Postman shell (2-3d total, rides each batch)
```

| Ticket | Size | Blocked by |
|---|---|---|
| T2-1 tier model + gate | days (1–2) | D-14 |
| T2-2 LLM seam | **week (3–5)** | D-15 for live wiring (interface unblocked) |
| T2-3 ADR on /v1 | days (2–3) | T2-1 |
| T2-4 adherence signals | days (3–4) | T2-1, D-19 |
| T2-5 condition inference | days (2–4) | T2-1, D-18 |
| T2-6 Greek explanations | days (2–3) | T2-1, T2-2 |
| T2-7 ADR narrative | days (2–3) | T2-2, T2-3 |
| T2-8 SPC corpus | **week (1–2)** | D-16 |
| T2-9 SPC Q&A (RAG) | **week (3–5d)** | T2-2, T2-8, D-17 |
| T2-10 agentic SPC lookup | **week (3–5d)** | T2-2, T2-8 |
| T2-11 tests/docs/Postman | days (2–3 total) | rides each batch |
| T2-12 DPA AI amendment | days (0.5–1) | D-15 |

**Roll-up total: ≈ 29–49 dev-days (~6–10 weeks single-dev) to complete Tier-2.** The
spread is dominated by T2-8 (corpus format unknown until the D-16 probe). As with
Tier-1, the real long poles are external: **D-15 (LLM DPA) and D-16 (corpus licence)
gate the differentiated half of the tier and both can start today at zero engineering
cost.**

### Minimal trial slice — the smallest credible Clinical demo

The audit **confirms the hypothesis (ADR-on-/v1 + AI Safety Explanations), with one
addition**:

> **T2-1 + T2-3 + T2-2 + T2-6** (+ their T2-11/T2-12 slices) ≈ **10–14 dev-days
> (~2–3 weeks)**, gated externally only by D-14 (a confirm) and D-15 (the DPA).

What that demos to a business: tier provisioning + a Core key bouncing off a Clinical
route (the commercial story), a complete clinical workflow with state machine, audit
events, and history filters (ADR), and a visible, Greek, AI capability layered on the
already-live `POST /v1/safety/check`. It is deliberately corpus-free — the SPC trio is
the long pole and D-16 is unresolved.

**Best optional extension (+2–4d): T2-5 rule-based condition inference** — zero LLM
dependency, high demo value ("we suggested DIABETES_T2 from the dispensing history; one
confirm call armed the metformin/renal contraindication"), closes a fourth matrix row.

Honesty note for the pricing conversation: the trial slice delivers **3 (4 with T2-5) of
the 7 Clinical matrix rows** (`PharmAssist_Pricing.md:253-259`). The B2C pricing page
already carries a rolling-out caveat (`:372-376`); Motion A's table has no equivalent —
add one, or gate Clinical contracts on the remaining waves.

---

## 5. Explicitly out of scope

- **Tier-3 / Platform**: pharmacovigilance signal detection, drug recall webhook,
  reaction network alert agent, insurance pre-auth agent, HMVS
  (`PharmAssist_Pricing.md:222-228`) — including any webhook/push infrastructure (which
  is also why T2-10 ships pull-only).
- **Prescription execution / dispense** in any form (Tier-3 add-on), including a
  /v1 dispense surface as an adherence data source (D-19 fallback is a fast-follow, not
  this plan).
- **Live ΕΟΦ submission** of ADR reports or narratives — `EOF_REPORTED` stays a tracked
  status, the narrative stays a draft; no regulator transmission is built or implied.
- **B2C (Motion B) surfaces** of the Tier-2 features — the LLM seam, corpus, and
  inference map are deliberately reusable, but B2C UI/UX work (incl. migrating B2C
  `/spc` off the fixture) is separate scope.
- **Redis / multi-worker** — D-8's triggers stand; the AI cache (T2-2) is a DB table
  precisely so it doesn't reopen that decision.
- **Legal text** — T2-12 produces the engineering annex amendment; DPA/ToS authorship
  remains D-13 (owner still TBD, now more urgent: Tier-2 stores more PHI and adds an AI
  subprocessor).

## 6. Phase gate

**Phase 0** (this audit + ticket set): ✅ written 2026-06-10 — **pausing here for
review.** Suggested batch shape mirrors FINISH-TIER1: Batch 1 = decisions D-14…D-19
recorded + the trial slice (T2-1/T2-2/T2-3/T2-6 + shell slices); Batch 2 = the
deterministic remainder (T2-4/T2-5); Batch 3 = the corpus wave (T2-8/9/10) once D-16
lands.
