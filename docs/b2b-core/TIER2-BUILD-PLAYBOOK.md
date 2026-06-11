# PharmAssist Tier-2 (Clinical) — Build Playbook

The ordered set of Claude Code prompts that take Tier-2 from the approved audit
(`docs/b2b-core/TIER2-AUDIT.md`) to a complete, sellable `/v1` Clinical tier — broken into
small, single-session batches **by feature**, so no session ever tries to build the whole tier
at once.

Each prompt references its `T2-*` ticket in `TIER2-AUDIT.md` (that's the full spec) and adds the
batch-level guardrails + the gotchas that are easy to miss.

---

## How to run this

- **One batch = one fresh Claude Code session.** Run them in order within a feature; respect the
  cross-feature dependencies noted on each batch.
- **Review → merge → next.** After each batch: review the diff, confirm tests green, merge to
  main, *then* start the next batch in a clean session. Never combine batches.
- **The audit doc is the spec.** Each prompt says "per its ticket in `TIER2-AUDIT.md`" — Claude
  Code reads the ticket for full detail. If the spec looks wrong, it flags and pauses; it does
  not silently deviate.
- **Model/effort:** high-context model, medium–high effort for the builds (especially F2 and the
  SPC suite). The spike (SPC0) is light. The shell is medium.

### Trial slice — stop here for a business demo

**F1 + F2 + ADR1 + EXPL ≈ 10–14 dev-days.** That's a demoable Clinical tier — tier provisioning,
a complete ADR workflow, and a visible Greek AI capability — and it runs end-to-end on
`LLM_MOCK`, so it is **not** gated on the Mistral DPA. Everything after EXPL is "finish the tier."

### Order at a glance

```
Foundations:   F1 tier gate → F2 LLM seam            (block everything)
ADR:           ADR1 reports → ADR2 narrative          (ADR2 needs F2)
Explanations:  EXPL                                   (needs F2)        ── trial slice ends here
Adherence:     ADH                                    (needs F1)
Inference:     INF                                    (needs F1+F2)
SPC suite:     SPC0 spike → SPC1 corpus → SPC2 lookup / SPC3 Q&A   (SPC2/3 need F2; SPC3 needs pgvector)
Shell:         SHELL  (contract/docs/Postman + DPA annex)          (after all features)
```

---

## Standing rules — apply to EVERY build batch

Each prompt below assumes these; they're stated once here.

1. **Read the named `T2-*` ticket(s) in `docs/b2b-core/TIER2-AUDIT.md` and build to it.** If the
   spec looks wrong, flag it and pause — don't silently deviate.
2. **Additive only.** B2C (Motion B) code paths and tests stay untouched and green. New `/v1`
   routes, new modules, new tables — nothing modifies a B2C path.
3. **Tier-gated.** Every new `/v1` route sits behind the T2-1 `require_tier("clinical")` ordinal
   gate (a `core` key gets `403 tier_required`; `platform` passes a `clinical` route).
4. **Standard `/v1` plumbing.** Per-key rate limit (inherited from `get_api_context`), the error
   envelope, `request_id`, and the pagination envelope on any list.
5. **Mock parity.** Every new endpoint gets a `services/v1_mock.py` fixture; AI endpoints pin
   deterministic `LLM_MOCK` outputs. Mock and live shapes identical.
6. **Tests every batch.** Contract test (shape + envelope), tenant-isolation test (tenant A
   can't see/touch B), the tier-gate matrix (core 403 / clinical 200 / platform 200), mock
   parity — plus the `openapi-v1`/`API.md`/Postman delta for the new endpoints (T2-11 rides each
   batch, consolidated at the end).
7. **AI batches only.** Every prompt goes through T2-2's typed builders — **no patient identity
   (AMKA / name / address) in any prompt** — the digit-token scrub runs on any free text, and
   "suggests, never decides" is structural (draft flags, suggestions-only, source citations,
   refusal-on-empty). One PII-guard test per AI endpoint.
8. **One batch, one fresh session, one branch** (`feat/tier2-<name>`). Run typecheck + lint + the
   test suite. **Pause for review. Do NOT start the next batch.**

---

## 0 · Foundations (block everything)

### Batch F1 — Tier gate · `T2-1` · ~1–2 d · no deps

```
Build T2-1 (tier entitlement + /v1 tier gate) per its ticket in docs/b2b-core/TIER2-AUDIT.md.
Key points:
- `tier` column on the `customers` table (core|clinical|platform, server_default 'core'),
  migration registered in the three places (alembic/env.py, models/__init__, main.py), backfill
  existing rows → core.
- ApiContext gains `tier`; a `require_tier("clinical")` dependency that is ORDINAL
  (platform ≥ clinical ≥ core), NOT exact-match.
- New stable envelope code `tier_required` (403), added to the code table (additive).
- GET /v1/status echoes the tier; b2b_admin gains `create-customer --tier` + `set-tier`;
  ONBOARDING.md/KEY-MANAGEMENT.md gain the tier step.
AC: a core key 403s `tier_required` on a gated route, a clinical key passes, a platform key ALSO
passes a clinical route (ordinal); tier visible on /v1/status; existing /v1 + B2C suites green.
Branch feat/tier2-tier-gate. Standing rules apply. Pause for review.
```

### Batch F2 — LLM seam · `T2-2` · ~3–5 d · no deps (live wiring needs the Mistral key)

```
Build T2-2 (LLM integration seam) per its ticket in docs/b2b-core/TIER2-AUDIT.md.
Key points:
- app/services/llm.py — provider-agnostic async client (httpx, services/pharmapi.py conventions);
  target = Mistral's EU STANDARD API. Settings LLM_API_BASE/KEY/MODEL (+ embeddings) checked at
  FIRST USE, not boot fail-fast (a Tier-1-only deploy must still boot without AI config).
- LLM_MOCK toggle, boot-validated like PHARMAPI_MOCK (FT-15 RECOGNIZED_MOCK_TOKENS pattern), with
  deterministic canned outputs per prompt-kind.
- HARD PII BOUNDARY: typed prompt builders whose schemas accept only whitelisted clinical fields
  (ATC codes, rule text, condition codes, symptom text, anonymised age/sex bands) — no AMKA/name/
  address field exists structurally — PLUS a guard test that scans every built prompt for
  AMKA-shaped (11-digit) tokens before dispatch.
- ai_response_cache table (DB-backed, survives restart). Failure → `ai_unavailable` envelope code,
  AI endpoints only.
CRITICAL: no Tier-1 module imports the seam (add a grep-assert test). Deterministic endpoints
(safety check, formulary, ADR CRUD) never call it.
AC: PII-guard test (a prompt with an AMKA-token is refused), mock determinism test, timeout →
envelope test, the no-import grep.
Branch feat/tier2-llm-seam. Standing rules apply. Pause for review.
```

---

## 1 · ADR — reporting + AI narrative

### Batch ADR1 — ADR on /v1 · `T2-3` · ~2–3 d · needs F1

```
Build T2-3 (ADR reporting on /v1) per its ticket in docs/b2b-core/TIER2-AUDIT.md. Needs F1 merged.
Key points:
- NEW location-scoped tables b2b_adr_reports + b2b_adr_events. Do NOT reuse the B2C adr_report —
  its pharmacist_id/pharmacy_id are NOT NULL FKs (D-3 precedent); the new pair is location_id +
  created_via_api_key_id, same status/severity/causality vocabularies + next_status semantics.
- Endpoints: POST /v1/adr-reports (201) · GET /v1/adr-reports with the catalog filters
  amka / atc|barcode / from / to / status + pagination (NEW code — B2C only has free-text q+sort) ·
  GET /v1/adr-reports/{id} · POST /v1/adr-reports/{id}/transition (state machine + event row).
- EOF_REPORTED stays a tracked status label (NO ΕΟΦ submission); eof_report_ref optional/
  caller-supplied; API.md states plainly that PharmAssist does not transmit to ΕΟΦ.
AC: contract suite incl. each filter; tenant isolation (location A cannot read/transition B's);
illegal transition → 409 envelope; mock parity; B2C side_effects suite untouched and green.
Branch feat/tier2-adr. Standing rules apply. Pause for review.
```

### Batch ADR2 — AI ADR narrative · `T2-7` · ~2–3 d · needs F2 + ADR1

```
Build T2-7 (AI ADR narrative drafting) per its ticket. Needs F2 + ADR1 merged.
Key points:
- POST /v1/adr-reports/{id}/narrative → {draft:true, language, narrative, disclaimer, generatedAt}.
  ALWAYS a draft: no status transition, no persistence as the report's text (regenerate on demand;
  the report row is untouched).
- Prompt from the structured ADR fields MINUS patient_name/patient_amka; symptom_description free
  text rides the T2-2 scrub + the DPA caveat.
AC: response always carries draft:true + disclaimer; report row/status unchanged after the call;
PII-guard test; mock parity; tier gate.
Branch feat/tier2-adr-narrative. Standing rules apply. Pause for review.
```

---

## 2 · AI Safety Explanations

### Batch EXPL — Greek safety explanations · `T2-6` · ~2–3 d · needs F2  *(last trial-slice batch)*

```
Build T2-6 (AI safety flag explanations, Greek) per its ticket. Needs F2 merged.
Key points:
- SEPARATE endpoint POST /v1/safety/explain — so POST /v1/safety/check keeps its deterministic
  latency and never calls the LLM. Body = ruleCodes (+ optional condition codes) →
  {explanations:[{ruleCode, language:"el", rationale, mechanism, riskLevel, alternatives, cached}]}.
- Prompt inputs = rule fields only (message_en/details_en/recommended_action_en + trigger/
  conflicting ATCs + condition codes). Zero patient identity by construction.
- Cached by (rule_code, sorted condition-profile) via T2-2's cache. The static *_gr seed-translation
  fallback under-delivers the condition-aware promise — note it, don't ship it as the deliverable.
AC: cache-hit test (2nd identical call → 0 LLM calls); PII-guard; LLM_MOCK canned Greek per seeded
rule (mock parity); tier gate; /v1/safety/check byte-identical before/after.
Branch feat/tier2-safety-explain. Standing rules apply. Pause for review.
```

> **Trial slice complete after this batch.** Stop here for a business demo (on `LLM_MOCK`), or
> continue to finish the tier.

---

## 3 · Medication Adherence

### Batch ADH — adherence, dual-source · `T2-4` · ~4–6 d · needs F1

```
Build T2-4 (medication adherence signals, dual-source) per its ticket. Needs F1 merged.
Key points:
- GET /v1/patients/{key}/adherence?patientConsent=true → per long-term medication {atcClass,
  lastDispense, expectedRefill, daysSinceExpected, status ON_TRACK|OVERDUE|LAPSED, evidence,
  dataCaveats}.
- TWO sources merged per D-19: (a) upstream ΗΔΥΚΑ medicine history (consent + ΕΟΠΥΥ gated;
  non-ΕΟΠΥΥ 403s on the upstream path), and (b) caller-pushed events via a NEW
  POST /v1/dispense-events ingest endpoint + a pushed-events store. Merge + DEDUP (the same
  dispense via both paths counts once); the response says which sources fed it; caller-push is
  what covers non-ΕΟΠΥΥ locations.
- Long-term ATC set = the pricing list exactly (B01A, C02/C03/C07/C08/C09, A10, C10, N06A).
- Honest by construction: thin history → dataCaveats ("single dispense — cadence unknown"), never
  a fabricated status.
AC: synthetic-history tests (on-track / overdue / lapsed / single → caveat); merge/dedup test;
tier + consent + ΕΟΠΥΥ gate contract tests; deterministic OVERDUE mock fixture.
Branch feat/tier2-adherence. Standing rules apply. Pause for review.
```

---

## 4 · Condition Inference

### Batch INF — AI condition inference · `T2-5` · ~3–4 d · needs F1 + F2

```
Build T2-5 (patient condition inference, AI) per its ticket. Needs F1 + F2 merged.
Key points:
- GET /v1/patients/{key}/condition-suggestions?patientConsent=true → {suggestions:[{conditionCode,
  name, confidence HIGH|MEDIUM, evidence:[drugs]}], suggestionsOnly:true, dataCaveats}.
- AI on the T2-2 seam, but the LLM output MUST be constrained (structured output / enum) to the
  EXISTING safety-rule condition vocabulary (safety_rule.trigger_condition_code: DIABETES_T2,
  RENAL_SEVERE, PREGNANCY, G6PD, …) — so a confirmed suggestion immediately arms the engine. No
  free-form conditions.
- Input = upstream medicine history (reuse T2-4's source handling, incl. the dual-source path);
  same consent / ΕΟΠΥΥ gates and the non-ΕΟΠΥΥ consequence.
- NEVER writes — the caller confirms via the existing POST /v1/patients/{key}/conditions.
AC: deterministic LLM_MOCK tests; explicit no-write assertion (DB unchanged after the call);
out-of-vocabulary output rejected; tier/consent/ΕΟΠΥΥ gates; PII-guard.
Branch feat/tier2-condition-inference. Standing rules apply. Pause for review.
```

---

## 5 · SPC suite (spike → corpus → features)

### Batch SPC0 — extraction spike · `T2-8a` · ~0.5–1 d · independent (run early)

```
Run T2-8a (SPC extraction spike) per its ticket. THIS IS A THROWAWAY MEASUREMENT — NOT app code.
Do:
- Pull ~30–50 real ΕΟΦ SmPC PDFs from the OFFICIAL register, across the seeded drug set.
- Run Mistral OCR over them (Azure Document Intelligence as a control on a handful).
- Produce docs/b2b-core/spc-extraction-spike.md reporting: native-text vs scanned split; Greek
  character accuracy (spot-check N); and the SmPC section-parse success rate — can you reliably
  segment 4.3 / 4.4 / 4.5 / 4.6 from the OCR markdown?
Throwaway script under scripts/ (mark it throwaway). Do NOT build the corpus, tables, or any /v1
surface. This sizes T2-8 and confirms Greek on Mistral OCR.
Branch spike/tier2-spc-extraction. Pause with the findings.
```

### Batch SPC1 — SPC corpus · `T2-8` · ~1–2 wk (size per SPC0) · after SPC0

```
Build T2-8 (SPC corpus: sourcing, ingestion, structured sections) per its ticket. After SPC0
(use its findings to size/shape). Key points:
- OFFICIAL sources only (ΕΟΦ register + EMA, NO third-party aggregators).
- spc_documents (barcode/ATC link, version, source URL, fetched_at) + spc_sections (doc FK,
  section_ref, title, text). Ingestion via Mistral OCR → parse into the standardized sections
  (4.3/4.4/4.5/4.6).
- Sync-status row (FT-4 catalog_sync_runs pattern); idempotent re-ingest; update cadence in
  OPERATIONS.md. B2C /spc keeps the fixture (don't migrate it — out of scope).
- Prioritise the seeded / most-dispensed set first; long tail can lazy-load later.
- Parse-quality gate: flag docs that don't segment cleanly rather than serving garbage.
AC: N real drugs ingested with all four key sections segmented; re-ingest idempotent; sync
failures surface in the status row.
Branch feat/tier2-spc-corpus. Standing rules apply. Pause for review.
```

### Batch SPC2 — agentic SPC lookup · `T2-10` · ~3–5 d · after SPC1 + F2  *(no embeddings)*

```
Build T2-10 (agentic SPC contraindication lookup) per its ticket. After T2-8 + F2. NO embeddings
needed — structured section retrieval, not RAG. Key points:
- POST /v1/spc/contraindication-check {medications:[{barcode|atc}], patientKey? | conditions?:[...]}
  → {findings:[{drug, sectionRef, findingText, severity, recommendedAction}], dataCaveats}.
- Pipeline: load the location's conditions for the patient (b2b_patient_conditions, location-scoped)
  → pull sections 4.3/4.4/4.5/4.6 per drug from the corpus → LLM matches contraindications +
  special-population warnings against the condition set → structured findings with exact section refs.
- ON-DEMAND (caller-invoked; no push — that's Tier-3). Carries the absence-≠-safe caveat; complements,
  never replaces, the deterministic engine.
AC: a seeded case (e.g. warfarin + PREGNANCY) surfaces a 4.3/4.6 finding with section ref; a drug
absent from the corpus → explicit caveat finding, not silence; PII-guard; mock parity; tier gate.
Branch feat/tier2-spc-lookup. Standing rules apply. Pause for review.
```

### Batch SPC3 — SPC Q&A (RAG) · `T2-9` · ~3–5 d · after SPC1 + F2 + pgvector

```
Build T2-9 (SPC Q&A / RAG on /v1) per its ticket. After T2-8 + F2 + pgvector (D-17). Key points:
- Swap the postgres image to a pgvector-enabled build (dev + prod compose) + a one-line
  CREATE EXTENSION migration.
- Embeddings over spc_sections chunks via mistral-embed (stay EU). POST /v1/spc/qa {barcode|atc,
  question} → {answer, language, sources:[{sectionRef, excerpt}], disclaimer}; Greek queries supported.
- Retrieval SCOPED to the named drug's document (structural guard against cross-drug answers).
- EMPTY retrieval → explicit "not addressed in the SPC" refusal — NEVER free generation.
AC: grounding test (answer cites a real ingested section); empty-retrieval refusal test; Greek
query fixture; mock parity (LLM_MOCK + fixture corpus); tier gate.
Branch feat/tier2-spc-qa. Standing rules apply. Pause for review.
```

---

## 6 · Shell & paper

### Batch SHELL — contract/docs/Postman + DPA annex · `T2-11` + `T2-12` · ~2.5–4 d · after all features

```
Build T2-11 (Tier-2 contract/docs/Postman consolidation) then T2-12 (DPA annex) per their tickets.
After all feature batches.
T2-11:
- Consolidation pass: confirm the tier-gate matrix is tested across EVERY new route (core 403 /
  clinical 200 / platform 200), tenant isolation incl. b2b_adr_reports, and mock parity on every
  endpoint (AI ones pin LLM_MOCK).
- scripts/export_openapi_v1.py picks up all new paths (verify the transitive B2C-exclusion still
  holds). API.md gains: the tier model + tier_required, AI failure mode (ai_unavailable), the
  consent/ΕΟΠΥΥ implications for adherence/inference, the draft/suggestions-only semantics. Postman
  collection + fixtures extended.
T2-12:
- DATA-PROCESSING.md amendment: the LLM provider as subprocessor (Mistral EU + standard DPA per
  D-15 / owner Rekas), the prompt PII boundary + the free-text caveat, ai_response_cache contents +
  retention stance, and b2b_adr_reports as a larger stored-PHI surface (AMKA + name + narrative) —
  set a retention stance. Mark "ready for legal author (Rekas)."
AC: CI DB-less selection includes the new contract tier; an integrator can exercise every Tier-2
endpoint from Postman against the mock; the annex matches the shipped code paths.
Branch feat/tier2-shell. Standing rules apply. Pause for review.
```

---

## Completion checklist

- [ ] F1 tier gate · [ ] F2 LLM seam  → **foundations**
- [ ] ADR1 reports · [ ] EXPL explanations  → **trial slice demoable (on LLM_MOCK)**
- [ ] ADR2 narrative · [ ] ADH adherence · [ ] INF inference  → **deterministic + AI features**
- [ ] SPC0 spike · [ ] SPC1 corpus · [ ] SPC2 lookup · [ ] SPC3 Q&A  → **SPC suite**
- [ ] SHELL contract/docs/Postman + DPA annex  → **tier complete**
- [ ] Rekas: Mistral DPA accepted + ΕΟΦ posture  → **AI features go-live-able in production**

*Total ≈ 31–51 dev-days. Trial slice ≈ 10–14. The DPA (Rekas) gates production go-live of the AI
features, not the build or the demo.*
