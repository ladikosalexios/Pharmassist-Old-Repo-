# BC-13a — Live masterdata probe findings

**Date:** 2026-06-10 · **Against:** `GET /api/v1/masterdata/medicines` on
`testeps.e-prescription.gr/pharmapiv2` (live call, `PHARMAPI_MOCK=false` one-off; test-env
rows carry dummy values — the *field set* is what matters).

## Verdict

Pharmapi masterdata supplies **everything the formulary ticket needs**. No external
ΕΟΦ/ΕΟΠΥΥ price-bulletin import is required for Tier-1.

## Field mapping adopted (BC-13)

| drug_catalog column | masterdata field | Notes |
|---|---|---|
| `eopyy_coverage` | `positiveList` (bool) | the ΕΟΠΥΥ positive list — the coverage filter; `negativeList` also exists |
| `retail_price` | `retailPrice` | ranking; `retailReducedPrice` exists too |
| `reference_price` | `referencePrice` | `referenceReducedPrice` exists |
| `participation_pct` | `participationPercentage` | drug-level co-pay % — partially answers D-7 |
| `form_code` | `formCode` | pharmaceutical form code — same-form constraint for substitution |
| `strength_raw` | `content` | free text (e.g. "500MG/TAB"); parsed into the two columns below |
| `strength_value` / `strength_unit` | parsed from `content` | best-effort parser; NULL when unparseable |
| `substance_code` | `activeSubstances[mainActiveSubstance].activeSubstance.code` | exact generic-equivalence key |
| `package_size` | `piecesPerPackage` | informational |

Other fields observed and deliberately not stored yet: `clusterCode` /
`inClusterWithGeneric` (ΕΟΠΥΥ generic clusters — a better equivalence key long-term),
`withdrawn`, `eofCode`, `producer`, `vat`, `hospitalMedicine`, `eopyyPreapproval` (Tier-3
pre-auth signal), `isAntibiotic`, `dailyDose`/`doseUnit`/`dosePerPackage`.

Full key set (79 keys) captured from a 3-item page:
activeSubstances, atcCode, barcode, clusterCode, commercialNameOnly, content,
contentInternal, dailyDose, defaultPercentage, dosePerPackage, doseUnit, drug, eofCode,
eopyyPreapproval, formCode, highCost, hospitalMedicine, hospitalPrice, id, ifet,
inCirculation, inClusterWithGeneric, insertDate, isAntibiotic, negativeList,
nonPrescriptable, packageForm, participationPercentage, piecesPerPackage, positiveList,
producer, referencePrice, referenceReducedPrice, retailPrice, retailReducedPrice,
updateDate, vat, withdrawn, … (plus ~40 niche flags: n3816, ivf, vaccine, specialImport,
onlyByProtocol, limitedExecution, etc.)

## Caveats

- Test-environment rows are placeholder data ("1", 1.0, 25.0) — field *presence* is
  verified, value *quality* must be re-checked against production masterdata at first
  production sync.
- `eopyy_coverage` stays nullable (tri-state): rows synced before this migration and the
  20 seed rows have no upstream value until the next full sync; the formulary endpoint
  reports `dataCaveats` when candidates have unknown coverage.

---

# BC-13b — First full-sync dry-run (test env)

**Date:** 2026-07-11 · **Against:** same test env, `PHARMAPI_MOCK=false` one-off ·
full `run_sync(None)` end-to-end (paginate → upsert → coverage).

## Volume & duration

- **11,135 active rows**, `totalPages`/`totalEntries` returned on every page (so
  volume is knowable up front for a progress bar / scheduler budget).
- **Full sync ≈ 64s** at 500 rows/page. A nightly full re-sync is cheap; the
  `/updates?since=` incremental path only matters for latency, not load.
- Non-destructive: matched on `barcode`/`gns_code`, so the existing seed rows
  persist alongside synced rows.

## Resolver-readiness (services/substance_resolver — the new coverage triad)

Over the 11,135 rows:

| field | populated | % | resolver use |
|---|---|---|---|
| `atc_code` (non-blank) | 11,016 | **98.9%** | resolution target + rx-side ATC |
| `name_en` (INN) | 9,807 | **88.1%** | Pass 2 (INN-name match) |
| `substance_code` | 7,955 | **71.4%** | Pass 1 (exact substance) |

So intolerance / co-medication resolution has strong headroom: 71% resolve by
exact substance code, and INN-name (88%) backfills most of the rest. The ~1% with
no ATC can never match a rule regardless — an upstream data gap, not a resolver one.

## Caveats specific to this run

- **Values are still test-grade.** The first rows are literal placeholders
  (`atcCode="1"`, `commercialNameOnly="1"`, INN `"TESTING ACTIVE SUBSTANCE"`). The
  ~99%/88% fill rates prove the *fields are populated at realistic scale*, but they
  do NOT validate value *correctness* (e.g. that "Amoxicillin" → `J01CA04`). That
  can only be checked against a **production** sync — the BC-13a caveat stands.
- **Brand→ATC matching (resolver Pass 3) is unproven here** — it needs the real
  `medicineCommercialName` ↔ `name_gr` formats from production history to know its
  true hit rate. This remains the weakest pass and the clearest target for the
  future AI-enrichment step.
- The dry-run leaves ~11k test rows in the dev `drug_catalog`; `python -m
  scripts.seed` restores the curated 20-row dev set.
