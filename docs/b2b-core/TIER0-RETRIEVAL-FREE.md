# Tier-0 "Clinical-only" — a /v1 tier that ships without production ΗΔΥΚΑ

**Status:** 🔨 **T0-1…T0-4 implemented** (2026-09-26, one PR — see §6 for what
shipped and where the ticket text below turned out to be wrong). T0-5 and T0-6
still open. Decisions D-20 / D-21 ✅ recorded
(2026-09-10, per Alex): tier is **`clinical_only` at €9/location/month**, and
`retrieval_unavailable` answers **409**. The new Motion A row is **not** yet in
`docs/PharmAssist_Pricing.md` (§6, item 9). (Sections 1–5 were written
plan-only.)
**Date:** 2026-09-10
**Baseline:** `main` @ `63e78cc` (#180).
**Driver:** production ΗΔΥΚΑ access was requested 2026-07-20 and is still pending
(`docs/OPEN-ISSUES.md`, memory `idika-production-access-pending`). Every current
`/v1` tier is unsellable until it lands, because `get_api_context` refuses any
request for a location without ΗΔΥΚΑ credentials. Four of the six `/v1` router
modules never make an upstream call at all, so that refusal is the only thing
standing between us and a sellable tier today.
**Scope driver:** `docs/PharmAssist_Pricing.md` → Motion A Tier 0 "Clinical-only",
to be added there per D-20. Core explicitly bundles Pharmapi retrieval, so this
is a new row below it — plus the orthogonal "any tier, no credentials" case D-20
records.
**Numbering:** tickets are T0-*n*; decisions continue TIER2-AUDIT's D-14…D-19 as
**D-20…D-21**.
**Constraint:** B2C stays untouched and green. Every ticket is additive or a
loosening of a `/v1`-only guard; no ticket changes a B2C code path.

---

## 1. Audit — what actually needs ΗΔΥΚΑ

Audited 2026-09-10 against `main` @ `63e78cc`. `ctx.pharmapi` counts are literal
grep counts over each module.

| `/v1` module | `ctx.pharmapi` uses | Tier gate today | Sellable with no ΗΔΥΚΑ? |
|---|---|---|---|
| `drugs.py` | 0 | none (any authenticated tenant) | ✅ yes |
| `safety.py` | 0 | none (any authenticated tenant) | ✅ yes |
| `safety_explain.py` | 0 | `require_tier("clinical")` | ✅ yes |
| `adr_reports.py` | 0 — only `is_mock_pharmapi()` for the mock/live data branch (`:160,232,266,284`) | `require_tier("clinical")` | ✅ yes |
| `prescriptions.py` | 7 | none | ❌ upstream |
| `patients.py` | 15 | none | ❌ upstream |

**The single blocker** is in `app/routers/v1/deps.py`, inside `get_api_context`,
and it fires before any router code runs:

```python
if not location.pharmapi_username or not location.pharmapi_password:
    # Server-side provisioning gap, not a caller error — but don't leak
    # tenant existence details either.
    raise HTTPException(status_code=500, detail="Location is not fully provisioned")
```

So an uncredentialed tenant gets a **500 on `/v1/safety`**, a route that never
touches upstream. `ApiContext.pharmapi` is typed `PharmapiContext` (non-optional)
and is built unconditionally, which is what forces the guard.

### Audit surprises that shaped the plan

- **The entitlement outcome comes out right by accident.** `require_tier` appears
  in only two modules (`adr_reports.py`, `safety_explain.py`); `drugs`, `safety`,
  `patients` and `prescriptions` take `get_api_context` directly and are therefore
  open to *any* authenticated tenant. Insert a tier below `core` and `safety`/`drugs`
  become reachable by it with no gate change (desired), while `patients`/`prescriptions`
  would too (not desired) — except T0-2 blocks them on the credential check instead.
  Right result, wrong mechanism. T0-3 pins it with an explicit test rather than
  leaving it resting on the absence of a decorator.
- **The 500 is a real defect, not just a tier blocker.** A provisioning gap is
  reported to the caller as a server fault, so an integrator debugging onboarding
  sees "PharmAssist is broken" rather than "this location needs credentials".
  T0-2 turns it into a documented 4xx with a stable envelope code.
- **`TIER2-AUDIT.md` is now stale on SPC** and will mislead the next session that
  reads it. See T0-6.

---

## 2. Decisions — recorded 2026-09-10

### D-20 · Name and price of the base tier — ✅ `clinical_only` at €9/location/month

Recorded 2026-09-10. The name lands in `TIER_ORDER`, in `customers.tier`, in the
`tier_required` error text and in `PharmAssist_Pricing.md`, so it is expensive to
change later; `clinical_only` says what the tenant gets rather than where it sits
in a ladder, and stays accurate if a cheaper tier is ever added underneath.

**Contents, and the ladder trap that nearly shipped.** An early draft of this doc
put the SPC citation surface, AI explanations and ADR *into* this tier. That
inverts the ladder: those are Tier-2 Clinical capabilities, so a €9 tier would
have carried what the €15 Core tier does not. Tier 0 is therefore **Core minus
retrieval minus formulary**: safety engine (with caller-supplied conditions) plus
drug catalog reads, and nothing else. Exactly the two ungated upstream-free
modules from the audit table.

**Retrieval is orthogonal to tier — this is the load-bearing consequence.** T0-2
and T0-3 implement two *independent* guards, so any tier is purchasable by a
tenant with no credentials; retrieval routes just answer 409 while the rest of the
tier works. So the buyer for the SPC-citation pitch is a **Clinical tenant without
retrieval**, not a Tier-0 tenant, since T0-5 gates at `clinical`. The pricing doc
anchors that at €26 (Clinical less the retrieval component). Do not try to solve
that SKU by moving capabilities down into Tier 0.

**Still untested:** €9 and €26 have never been quoted to a buyer.

### D-21 · Status code for `retrieval_unavailable` — ✅ 409

Recorded 2026-09-10. 403 is already spoken for by `tier_required`, and this is not
an entitlement denial: the tenant is entitled to nothing more, but their *location*
lacks credentials, which is a provisioning state they can fix. **409** with envelope
code `retrieval_unavailable`, message naming the missing credentials and pointing at
onboarding. 403 stays reserved for entitlement.

---

## 3. Tickets

### T0-1 · Optional ΗΔΥΚΑ credentials in the /v1 context — *refactor* · **hours**

`app/routers/v1/deps.py`

- `ApiContext.pharmapi: PharmapiContext | None`.
- Replace the unconditional 500 with a branch: build `PharmapiContext` when both
  credential columns are present, else `None`.
- Keep `decrypt_credential` **inside** the credentialed branch, so an uncredentialed
  tenant never reaches the AES path and a deployment serving only this tier does not
  need `CREDENTIAL_ENCRYPTION_KEY` exercised per request.
- Leave the rate-limit hit, the `request.state.v1_*` tenant stamping and the
  `last_used_at` refresh exactly where they are — all three must keep working for
  uncredentialed tenants (the access log and per-key limit are tier-independent).

**Tests:** an uncredentialed location resolves and returns 200 from `/v1/safety`
and `/v1/drugs`; the `/v1` access log still carries `customer_id`/`location_id`.

### T0-2 · `require_retrieval` guard + stable envelope — *build* · **hours** — after T0-1

`app/routers/v1/deps.py`, `app/routers/v1/errors.py`

- Dependency factory mirroring `require_tier`: resolves the full `ApiContext`, and
  raises `V1Error("retrieval_unavailable", 409, …)` (D-21) when `ctx.pharmapi is None`.
  Follow `require_tier`'s docstring pattern and `patients._require_eopyy`'s
  envelope-403 precedent.
- Apply to **every** route in `patients.py` and `prescriptions.py`.
- Deliberately **not** applied to `drugs.py`, `safety.py`, `safety_explain.py`,
  `adr_reports.py` — audited at 0 upstream uses each. Add a test that asserts this
  list, so a future route that starts calling upstream fails loudly.
- Document the new code in `docs/b2b-core/API.md` and the OpenAPI error table.

**Tests:** uncredentialed tenant gets the envelope code (not a 500) on every
`patients`/`prescriptions` route; credentialed tenant is unaffected.

### T0-3 · New base tier in `TIER_ORDER` — *build* · **hours** — after T0-1

`app/routers/v1/deps.py`, `customers.tier`, one migration

- Insert `clinical_only` below `core`: `TIER_ORDER = ("clinical_only", "core", "clinical", "platform")` (D-20).
- **Trap 1:** `_tier_rank` returns 0 for an unknown value, which after the insert
  means the new base tier. The fail-safe property survives (unknown still means
  least privilege) — assert it in a test so the next edit to `TIER_ORDER` can't
  quietly invert it.
- **Trap 2:** `get_api_context` does `tier=customer.tier or "core"`. Once `core` is
  rank 1, that default hands an unset row a **paid upgrade**. Change the default to
  the new base name in the same commit.
- Add the explicit entitlement test called for in the audit surprise above:
  a `clinical_only` tenant reaches `safety`/`drugs`, is refused `adr_reports`/
  `safety_explain` with `tier_required`, and is refused `patients`/`prescriptions`
  with `retrieval_unavailable`.

### T0-4 · Provision a location with no ΗΔΥΚΑ credentials — *build* · **hours** — after T0-1

B2B admin provisioning path (`app/routers/admin/`)

- Allow creating a customer + location + minting a key with the credential columns
  left null, so a `clinical_only` tenant can be onboarded end to end.
- `ONBOARDING.md` gets a short "clinical-only tenant" path that skips the ΗΔΥΚΑ steps.
- Keep the admin audit trail (`b2b_admin_audit`) recording the credential-less create
  distinctly, so an uncredentialed location is visibly intentional rather than a
  half-finished onboarding.

### T0-5 · Expose the SPC corpus and its provenance on /v1 — *build* · **week (1)** — after T0-1; independent of T0-2/3/4

This is the ticket that makes the commercial pitch true. Everything above only
unblocks billing.

**The gap:** `services/safety_engine.py` carries **36** SPC references (live since
#178), but `routers/v1/safety.py` carries **0**. So B2B callers receive rule-based
findings only, and none of the SPC-grounded findings or their citations. The
capability is built and the API does not expose it.

- Surface SPC-derived findings through `/v1/safety`, each carrying a provenance
  block from `spc_documents`: `source` (eof/ema/upload), `source_url`, `sha256`,
  `fetched_at`, `extraction_method` (deterministic/llm), `verified` +
  `verified_by`/`verified_at`, and the section ref the finding came from.
- `GET /v1/spc/{barcode|atc}` serving the `parsed` payload plus the same provenance
  block.
- A raw-document path that serves **our stored `raw_pdf`**, never a redirect: the
  model comment records that ΕΟΦ document URLs are JSF-session-bound and expire, so
  a redirect would rot. This is precisely what makes the citation defensible and is
  the differentiator against an editorial database (see memory
  `f-anazitisi-clinical-incumbent`).
- Gate at `require_tier("clinical")`, consistent with `safety_explain`.
- Carry the E4 honest-register convention from `TIER2-AUDIT.md`: `dataCaveats`, and
  never imply absence of a finding means safe.

**Tests:** a finding's citation round-trips to a servable document; a document whose
upstream URL is dead still serves; `extraction_method` is present on every finding.

### T0-6 · Un-stale `TIER2-AUDIT.md` — *docs* · **hours**

`TIER2-AUDIT.md` is dated 2026-06-10 at baseline #138 and two of its load-bearing
status claims are now false:

- Row 1 says `services/spc.py` is a 102-line two-drug `MOCK_SPC` fixture and that
  "the safety engine never reads SPC data (zero SPC references in
  `services/safety_engine.py`)". There are now 36, plus `spc_document`,
  `spc_fetch_state` and `spc_sync_run` models and `spc_extract` / `spc_ingest` /
  `spc_parse` / `spc_sources` services, all shipped in #177 and #178.
- **T2-8's proposed schema diverged from what shipped.** The ticket specified
  `spc_documents` + a separate `spc_sections` table. The shipped design keeps a
  `sections` JSONB map on one row and adds `raw_pdf`, `sha256`, `extraction_method`
  and the `verified_*` review fields — a better design for provenance, but it means
  **T2-9 (SPC Q&A / RAG) must be re-specced against the shipped tables** before
  anyone builds from that ticket.

Add a status banner at the top of `TIER2-AUDIT.md` recording what landed in
#176–#180, and mark T2-8 substantially delivered on the B2C side with the /v1
exposure carved out to T0-5.

---

## 4. Dependency order + sizing

```
T0-1 (hours) ─┬─ T0-2 (hours) ─┐
              ├─ T0-3 (hours) ─┼─ billable clinical_only tenant
              └─ T0-4 (hours) ─┘
T0-1 ──────────── T0-5 (week 1) ─── the pitch becomes true
T0-6 (hours, any time, do it first so nobody builds from the stale spec)
```

- **T0-1…T0-4 are one PR**, roughly 1–2 days together. They are all `/v1`-only and
  touch one file plus a migration and the admin path.
- **T0-5 is its own PR**, about a week.
- **Sell-by-date reality check:** T0-1…T0-4 make the tier *billable*; only T0-5 makes
  it the tier described in the go-to-market memo. Don't take pitch 01 to a vendor
  between those two PRs, because the demo is then rule-based findings with no
  citations, which is the one thing f-anazitisi already does better.

---

## 5. Explicitly out of scope (do not pull in)

- Every remaining Tier-2 capability: SPC Q&A / RAG (T2-9), condition inference,
  adherence signals, ADR narrative drafting. They stay on the Tier-2 plan.
- All Platform-tier features: pharmacovigilance signal detection, recall webhooks,
  reaction network alerts, pre-authorisation. None exists in `/v1` today.
- Formulary substitution. Core-tier scope, unrelated to this tier.
- Any B2C change. The B2C `/spc` router and the cookie path stay as they are.
- Re-pricing Core, Clinical or Platform. D-20 adds a row; it does not renegotiate
  the existing ones.

---

## 6. Implementation record — T0-1…T0-4 (2026-09-26)

Sections 1–5 above are left as written. This section records what shipped and
every place the ticket text had to be corrected against the code.

### What shipped

- **T0-1** — `ApiContext.pharmapi: PharmapiContext | None`; the 500 is gone.
  Credentials decrypt only inside the credentialed branch (a test fails if the
  AES path is reached for a credential-less location; a positive control shows
  the credentialed path does reach it). A row with credentials but no unit id
  resolves as uncredentialed rather than borrowing the B2C session's pharmacy
  id. Rate limit (429), tenant stamping and `last_used_at` unchanged and tested
  for credential-less tenants.
- **T0-2** — `deps.require_retrieval` → `V1Error("retrieval_unavailable", 409)`;
  enforced in mock mode too (sandbox parity). Each guarded route documents the
  409 in `openapi-v1.json`. `tests/test_v1_retrieval_free.py` asserts the exact
  guarded / unguarded inventories and has two nets for a route that reaches
  ΗΔΥΚΑ unguarded: a source scan that fails a handler whose *own* body reads
  `ctx.pharmapi` or calls a `pharmapi_*` service (blind to indirect calls), and
  a live-mode run of every upstream-free route for a credential-less tenant
  with outbound HTTP blocked and the legacy B2C session warm, asserting zero
  requests. The second net is the one that sees an indirect call — e.g. the
  safety engine fetching intolerances / history itself, which with no context
  falls back to the B2C pharmacy's credentials; a positive control pins that it
  does.
- **T0-3** — `TIER_ORDER = ("clinical_only", "core", "clinical", "platform")`;
  unset-tier fallback is `TIER_ORDER[0]` (trap 2); trap 1 pinned in
  `test_v1_tier_gate.py`. Migration `e5b1c9d47a20` widens `ck_customers_tier`.
  Retrieval is gated at `core` too (D-20: Tier 0 is Core minus retrieval):
  `require_retrieval` checks credentials first — so a credential-less Tier-0
  tenant gets `retrieval_unavailable`, as T0-3 specifies — then applies the same
  gate as `require_tier("core")`, so a `clinical_only` customer with a
  credentialed location gets `tier_required`. Every tier-gated route documents
  its 403 (with the tier it needs) in `openapi-v1.json`, pinned by a test that
  reads the minimum from the gates themselves.
- **T0-4** — `b2b_admin create-location --no-retrieval` (refuses any ΗΔΥΚΑ flag
  alongside it; without it the unit id + username stay mandatory). Audited
  under its own verb `CREATE_LOCATION_NO_RETRIEVAL`; `list` shows
  `retrieval=none`. `ONBOARDING.md` §6 is the short path. The same migration
  makes `locations.pharmapi_unit_id` nullable and adds
  `ck_locations_pharmapi_credentials` (username/password both-or-neither, a
  blank string counting as unset; set credentials require a unit id) so a
  half-provisioned row can't exist. Its downgrade refuses while Tier-0 rows
  exist; offline (`--sql`) it skips that check and only renders the DDL.

### Ticket text that was wrong

1. **T0-2 "apply to every route in `patients.py`" — no.** Four of its eight
   routes are the DB-only conditions CRUD. `V1SafetyCheckRequest` has no inline
   conditions field, so that CRUD is the *only* way to feed contraindication
   screening into `/v1/safety/check`; gating it would have made D-20's "safety
   engine (with caller-supplied conditions)" false. Guarded: the four
   upstream-backed `patients.py` routes + both `prescriptions.py` routes.
2. **The audit missed `/v1/status`.** It lives in `routers/v1/__init__.py` and
   read `ctx.pharmapi.session_key`, so after T0-1 it would have 500'd (None
   dereference) for every credential-less tenant. Fixed, and it now reports
   `location.retrievalAvailable`.
3. **D-20 contradicts itself on formulary.** "Core minus retrieval minus
   formulary" (and §5 "Formulary substitution. Core-tier scope") vs "exactly the
   two ungated upstream-free modules" — `drugs.py` contains
   `/drugs/{barcode}/alternatives`. Resolved for the explicit decision:
   `/alternatives` is gated at `require_tier("core")`; catalogue search stays open
   to every tier. An integrator that needs alternatives must be provisioned at
   `core` or above.
4. **T0-4 points at `app/routers/admin/`.** That path doesn't exist, and
   `app/routers/admin.py` is the B2C cookie-auth admin router. B2B provisioning
   is the `backend/scripts/b2b_admin.py` CLI.
5. **T0-4 needs schema work the plan didn't list.** `locations.pharmapi_unit_id`
   was `NOT NULL`; it rides the same migration as T0-3's tier constraint.
6. **§1 grep counts.** Literal `ctx.pharmapi` counts are 4 (`patients.py`) and
   2 (`prescriptions.py`), not 15 and 7, plus 1 in `__init__.py` (item 2).
7. **"The OpenAPI error table" doesn't exist.** `openapi-v1.json` is generated
   from the app and declared no error responses; the code table lives in
   `API.md` §3 (updated). The committed spec was also stale since #138 (missing
   `/v1/safety/explain` and the three `/v1/adr-reports` paths); regenerating
   restored them.
8. **"Dependency factory mirroring `require_tier`."** `require_retrieval` takes
   no parameter, so it is a plain dependency: `Depends(require_retrieval)`.
9. **Header claim.** `docs/PharmAssist_Pricing.md` on `main` does not carry a
   `clinical_only` / €9 row, and this doc was not committed before this PR.
10. **D-20 "Retrieval is orthogonal to tier."** Only *credentials* are. With the
    two guards independent and no tier check on retrieval, a `clinical_only`
    customer given a credentialed location read patients and prescriptions —
    Core scope (D-20's own "Core minus retrieval"; the pricing doc's Core tier
    includes the Pharmapi proxy). Retrieval is now gated at `core` as well
    (T0-3 above); any tier can still be bought without credentials.

### Still open (not in T0-1…T0-4)

- **No CLI command adds credentials to an existing location.** Provision a new
  credentialed location instead (it comes with a new API key; the 409 message
  and API.md §3 say so).
