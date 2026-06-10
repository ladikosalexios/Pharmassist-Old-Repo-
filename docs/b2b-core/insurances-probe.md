# FT-2 — Insurances / co-pay raw key-set probe findings (settles D-9)

**Date:** 2026-06-10 · **Against:** `testeps.e-prescription.gr/pharmapiv2` (read-only live
calls via `scripts/insurances_probe.py`, `PHARMAPI_MOCK=false` one-off). Probed the three
integrated read surfaces' **raw** key-sets — our schemas filter unknown keys, so schema
absence was never evidence of upstream absence (same reasoning as BC-13a).

Patient source: test patient from the committed CDA fixture
(`tests/fixtures/cda/prescription_get_sample.xml`); the pending queue was empty at probe
time. 1 patient, 2 insurance entries, 33 + 46 + (search: empty) key paths captured.
Field *presence* is the finding; testeps values are placeholder data.

## Verdict (D-9)

**No numeric patient-level co-pay % exists anywhere in the read tier.** The only
%-shaped key, `socialInsurance.participationPercentLov`, is fund-level list-of-values
configuration and was `null` in every observed entry.

**But two real, previously-dropped fields do carry the co-pay/coverage story:**

| Upstream field | Endpoint | What it is | Action taken |
|---|---|---|---|
| `patientPartExceptions[]` (`id`, `exceptionReason`, `effectiveFrom`, `effectiveTo`) | `/common/getpatient` | **Patient co-pay exemption records** — the reason a patient deviates from the drug-level participation % and the validity window | **Surfaced**: `participationExceptions` on `GET /v1/patients/{key}` (mapped in `clean_pharmapi_patient_data`) |
| `socialInsurance.eopyy` (bool) | `/getpatient/insurances` | The fund-is-ΕΟΠΥΥ **coverage flag** the pricing line promises | **Surfaced**: `eopyy` on the fund object in `GET /v1/patients/{key}/insurances` |

The effective payable % is computed per prescription line at dispense time, upstream —
outside the Tier-1 read tier. Per the never-fake rule, we do **not** synthesize a
patient % from drug-level `participationPct` + exemptions: exemption semantics
(0% chronic, EKAS, etc.) are ΗΔΥΚΑ's to resolve.

**Pricing-doc wording updated** (`docs/PharmAssist_Pricing.md`) from
"Patient insurance details (ΕΟΠΥΥ coverage, co-pay %)" to what is actually delivered:
fund identity + ΕΟΠΥΥ coverage flag + patient co-pay exemptions, with drug-level
participation % on the drug catalog.

## Raw key-sets observed (types only — no values; PHI never printed)

`/common/getpatient` (33 paths): address, amka, birthDate, city, country{code,codeNum,
id,name,nameInEnglish}, county, email, euCardExpiration, euCardStartDate, euInsurance,
euRegistryNo, firstName, greekCitizen, identificationNo, identificationType, info,
lastName, **patientPartExceptions[]{effectiveFrom, effectiveTo, exceptionReason, id}**,
postalCode, sex{id,name}, showInfo, telephone.

`/getpatient/insurances` (46 paths): envelope {contents[], count, timestamp};
entries: ama, directlyInsuredAmka, expiryDate, fromEmaes, id, isRetired, lastActive,
memberType{id,name}, startDate, updateDate, socialInsurance{active, canExecuteExam,
canPrescribeConsumable, canPrescribeExam, canPrescribeExtifet, code, ekasEnabled,
**eopyy**, executedOnlyAtHospital, forEuPatient, id, isInactiveAmka, isMilitary, isN4368,
isPronoia, limitedExecution, main, maxPrescriptionNo, maxVisitNo, name, noInn,
noInnMandatory, parentSocialInsuranceId, **participationPercentLov (null)**,
prescribedOnlyAtHospital, retailPriceDispense, shortName, spcFilterCompliance,
supplementalInsurance, surcharge}.

`/prescriptions/search`: pending + unfiltered both returned 0 items for this pharmacy at
probe time (wide 2025-01-01→2026-12-31 window) — search-item key-set not re-verified
beyond what `_parse_prescription_search_json` already maps. Re-run the probe when the
test queue has data if search-level participation ever becomes a question.

## Caveats

- One patient observed; `expiryDate`/`startDate` on insurance entries and several
  `socialInsurance` flags (e.g. `ekasEnabled`, `surcharge`) exist upstream and remain
  deliberately un-surfaced — candidates if an integrator asks.
- Values are testeps placeholders; the *presence* of `patientPartExceptions` and `eopyy`
  should be sanity-checked against production data at first onboarding (same gate as the
  FT-3 catalogue quality check).
