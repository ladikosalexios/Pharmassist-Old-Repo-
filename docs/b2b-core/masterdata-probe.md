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
