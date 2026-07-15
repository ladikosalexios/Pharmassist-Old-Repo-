# Prescription-retrieval CDA fixture

Verbatim example taken from the ΗΔΥΚΑ pharmapi v2 spec — `info.description` at
`https://testeps.e-prescription.gr/pharmapiv2/v3/api-docs/manufacturers`.

Used as a golden anchor by `tests/test_prescription_cda.py`:

- `prescription_get_sample.xml` is a retrieved prescription CDA (Άντληση
  Συνταγής, GET /api/v1/prescriptions/get/{barcode}) that
  `app.services.cda.parse_prescription_cda` is expected to handle.

The eDispensation (dispense request/response) fixtures were removed with the
execution path — see tag `hmvs-certified`.

## PHI guard

The sample carries only synthetic placeholders:

- AMKA `01010003430` (not a real number)
- Names `TEST PATIENT` / `DOC WHO`
- Pharmacy unit and phone placeholders, generic addresses

Do **not** drop real patient data into this directory. Replace with synthetic
values before committing if you ever re-capture from a live testeps account.
