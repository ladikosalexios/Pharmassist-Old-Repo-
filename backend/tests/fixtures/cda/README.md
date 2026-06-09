# eDispensation CDA fixtures

Verbatim request + response examples taken from the ΗΔΥΚΑ pharmapi v2 spec —
`info.description` → `## Εκτέλεση Συνταγής` at
`https://testeps.e-prescription.gr/pharmapiv2/v3/api-docs/manufacturers`.

Used as golden anchors by `tests/test_cda.py`:

- `dispense_request_sample.xml` is what `app.services.cda.build_dispense_cda`
  should produce for the canonical two-medicine example (barcode 2411223344556,
  pharmacy unit 6543).
- `dispense_response_sample.xml` is what the mock branch of
  `app.services.pharmapi.pharmapi_dispense` returns and what
  `parse_dispense_response` is expected to handle in production.

## PHI guard

The samples carry only synthetic placeholders:

- AMKA `05055505340` (leading-zero, non-conforming Luhn — not a real number)
- Names `ΟΝΟΜΑ` / `ΕΠΩΝΥΜΟ` and `ΟΝΟΜΑΦ` / `ΕΠΙΘΕΤΟΦ` (Greek placeholders for
  "first name" / "last name", same as the spec)
- Pharmacy unit `6543`, phones with repeated digits, generic addresses

Do **not** drop real patient data into this directory. Replace with synthetic
values before committing if you ever re-capture from a live testeps account.
