# Going Real: Production-Readiness Checklists

> Companion to [`going-real-live-mode-ux.md`](./going-real-live-mode-ux.md).
> Two distinct concerns:
>
> 1. **Flow / Functionality** — engineering work that makes the app actually
>    do its job correctly end-to-end against live ΗΔΥΚΑ. Currently blocks the
>    app from being usable as a real pharmacist tool.
> 2. **Production-Ready** — infra, security, compliance, and ops work that
>    makes it *safe* to put real users / real patient data on it.
>
> Both lists are roughly in dependency order. Effort estimates are rough.

---

## 🔧 Flow / Functionality

What's missing for the app to actually function end-to-end as a real
pharmacist tool. Even with all this done, see the Production-Ready list
before deploying for real.

### Critical path — read-only live demo (~3 days)

The minimum that closes the loop "scan a real barcode → see real safety
alerts." No dispensing yet; pure read-side.

- [ ] **HL7 CDA fetch service** — `pharmapi_get_prescription_hl7(barcode, pharmacy_id) -> str`.
      Wraps `GET /api/v1/prescriptions/get/{barcode}?pharmacyId={pid}` with
      `Accept: application/x-hl7`. Single source of the live fetch.
- [ ] **HL7 CDA parser** — `parse_prescription_cda(xml) -> dict` returning
      the engine-friendly shape: `rxId`, `patient.{id, amka, name}`,
      `medication[]` with `{name, eofCode, atc?}`, `prescriber`, validity
      dates, `executions`, `insurance`.
- [ ] **`GET /prescriptions/by-barcode/{barcode}` route** — backend entry
      point that returns the *normalized* shape (not raw HL7) so the SPA's
      scan flow has somewhere to call.
- [ ] **SPA: scanner / barcode entry on the dashboard** — primary CTA. Also
      add an "AMKA + PIN" secondary action for paperless walk-ins
      (`/prescriptions/nopaper`). Currently there is no UI path to enter the
      verification view in live mode.
- [ ] **T6 — full `drug_catalog` sync** from `/api/v1/masterdata/medicines`
      (paginated, upsert on `gns_code`). Without this, EOF codes don't
      resolve to ATCs and most safety alerts silently miss. Already on the
      sprint, just unrun.
- [ ] **SPA: rewire verification view** to fetch from the new by-barcode
      endpoint instead of the mock-prescription lookup. Keep mock mode
      as-is for demos.

### Dispense path (~1–2 weeks)

The HL7 CDA write side. Lets a pharmacist actually complete a dispense
against ΗΔΥΚΑ.

- [ ] **HL7 CDA *builder* for dispense** — replace the 501 stub in
      `pharmapi_execute_prescription` with a real `<ClinicalDocument>`
      builder that POSTs to `/api/v1/prescriptions/dispense` (Content-Type:
      `application/x-hl7`).
- [ ] **Dispense response handling** — parse the response CDA, capture
      `executionNo` / exec_ref, persist on `documentation_logs`.
- [ ] **Partial-dispense path** — wire `/prescriptions/cancel-part/{barcode}/{executionNo}`
      and the corresponding UI.
- [ ] **Print receipt after dispense** — `GET /prescriptions/print/{barcode}?executionNo=N`.

### HMVS / FMD verification (legally required for live dispensing)

Independent track. Blocked on HMVO approval (see Production-Ready list).
Can be coded against the IQE test environment in the meantime.

- [ ] **New `app/services/hmvs.py` module** — separate host, Basic + their
      own API key, XML responses, `iqe=true` flag for test env.
- [ ] Wrap the 4 endpoints: `lot/qr` (verify), `otcm/dispense`,
      `otcm/reactivate`, `medicines/decommission`.
- [ ] **SPA: scan-pack flow** — DataMatrix entry for the pack's authenticity
      strip (GS1 or PPN scheme), passed into `lot/qr`.
- [ ] **Verify-before-dispense gate** — wire HMVS verify into the approve
      flow; block dispense when `status=2` (already dispensed elsewhere).
- [ ] **Decommission-on-success** — call `/medicines/decommission` after
      every successful dispense; legally required by EU FMD.

### Dashboard / UX alignment with event-driven model

Per [`going-real-live-mode-ux.md`](./going-real-live-mode-ux.md). The
current pre-populated queue model doesn't map to any live endpoint.

- [ ] Replace pre-populated "Prescription Queue" with **In-progress** +
      **Recent history** panels.
- [ ] Primary CTA → "Scan prescription".
- [ ] Safety Alerts panel sources from in-progress scans only.
- [ ] Surface dropped patient fields in the verification view: `info`
      (public-health notification message), `patientPartExceptions`
      (participation exemptions e.g. flood-victim status), full address.

### Pre-existing housekeeping

- [ ] Remove or rewire `/pharmapi/prescriptions/{barcode}` (router proxy
      that calls a non-existent v2 endpoint — predates the discovery that
      `/get/{barcode}` is HL7-only).
- [ ] Backend tests for the HL7 parser + dispense builder once those land.
- [ ] **Frontend test suite** — there isn't one today.
- [ ] Live-mode-aware UI: when `PHARMAPI_MOCK=false`, hide demo affordances
      (the seeded mock prescriptions, "Generate Instructions" demo, etc.).

---

## 🏭 Production-Ready

Infra, security, compliance, and ops. Separate from the functionality work
above. Most of these are "do once, maintain forever" rather than feature
work.

### Regulatory / external paperwork (slowest — start now)

- [ ] **Production ΕΟΠΥΥ certification** — email `Hd@idika.gr`, fill their
      forms, get a real pharmacy onboarded into the ΕΟΠΥΥ category. Test
      pharmacy `70014` is not a production credential.
- [ ] **HMVO registration approval** — submitted; awaiting response.
      Required before any HMVS / FMD work goes live.
- [ ] **Greek FMD compliance review** — legal sign-off that the
      dispense + decommission flow meets the EU Falsified Medicines
      Directive.
- [ ] **GDPR review** — patient AMKA, history, intolerances are special-
      category clinical data. Need a data-retention policy, deletion path,
      and processing-purpose documentation.
- [ ] **ΗΔΥΚΑ production credentials** — per-pharmacy (or per-pharmacist),
      not the shared `medcare1pharmapi` test creds.

### Secrets / config

- [ ] Move `SECRET_KEY`, `PHARMAPI_*`, `CREDENTIAL_ENCRYPTION_KEY` out of
      `compose.yaml` into a secrets manager (AWS SM / GCP Secret Manager /
      Vault).
- [ ] **Rotate `CREDENTIAL_ENCRYPTION_KEY`** — current dev value is `b"\x01" * 32`
      in tests; production must use a rotated, audited key with backup.
- [ ] Document the key-rotation procedure (re-encrypt
      `pharmacist_pharmacies.pharmapi_password` rows on key change).
- [ ] Pharmapi `Api-Key` rotation policy (coordinate with ΗΔΥΚΑ).
- [ ] Strip credentials from `compose.yaml` in the repo; supply via `.env`
      only (a `.env.example` already covers the shape).

### Auth / session

- [ ] **T15's `COOKIE_SECURE=true` production guard** — ✅ landed; rely on it.
- [ ] Set security headers at the edge proxy:
      `Strict-Transport-Security`, `Content-Security-Policy`,
      `X-Frame-Options`, `X-Content-Type-Options`.
- [ ] Session cookie rotation on every login (currently the JWT lives until
      its 8h expiry).
- [ ] **Rate limiting on `/auth/login`** — bcrypt constant-time check is
      good against side-channels but no rate limit means brute force is
      free.
- [ ] Per-pharmacist Pharmapi credentials (one set per pharmacist, not a
      global one) — already supported by `pharmacist_pharmacies` schema
      but production needs a real provisioning flow.
- [ ] Account lockout / breach detection.

### Audit / observability

- [ ] T11 audit-log writes — verify coverage of every dispense and every
      patient-clinical-data access (see [PR #?? if open]).
- [ ] Centralized log aggregation (Loki / Datadog / CloudWatch).
- [ ] Replace remaining `print(...)` calls in `app/services/pharmapi.py`
      with `logger` — partial migration done, some left.
- [ ] Error tracking (Sentry or equivalent).
- [ ] Latency / availability dashboards for ΗΔΥΚΑ upstream calls.
- [ ] Health probes for the orchestrator: `/health` exists; add `/ready`
      that checks DB + upstream reachability.

### Persistence / data

- [ ] **Production Postgres** — separate instance from dev, not in the same
      compose stack.
- [ ] Backup + point-in-time recovery for `documentation_logs`, `audit_log`,
      `patient_conditions`, `pharmacist_pharmacies`.
- [ ] Alembic migration strategy for live deploys (CI step? auto on boot?
      manual?).
- [ ] Audit-log retention policy — Greek law likely mandates X years.
- [ ] Patient-data retention / deletion path (GDPR).
- [ ] **Drug-catalog refresh schedule** — T6 nightly sync via
      `pharmapi_get_masterdata_medicines(since=YYYY-MM-DD)` (the `?since=`
      query is already supported by the service helper).

### CI / quality

- [ ] **`pytest` in CI** — currently only ruff + eslint run. The new
      `test_endpoints_integration.py` needs a Postgres service; either
      add one to CI or split the suite into pure-unit (CI) vs
      integration (local-only).
- [ ] **Bake `pytest` (+ dev deps) into the backend image**, or document
      `pip install -r requirements-dev.txt` in the contributor README —
      currently lost on container recreate.
- [ ] Frontend lint / typecheck already in CI ✅.
- [ ] Pre-commit hook coverage ✅.

### Deployment / ops

- [ ] Push `pharmassist/backend` + `pharmassist/frontend` to a real
      container registry (GHCR / ECR / GCR / Docker Hub).
- [ ] Orchestration (k8s / ECS / Fly.io / etc.) with secrets bound from the
      secrets manager.
- [ ] TLS termination (Caddy / Cloudflare / load balancer).
- [ ] Domain + DNS.
- [ ] **Production `ENV=production`** set explicitly — T15 guard verifies
      cookie security.
- [ ] **CORS configured for the real frontend origin** (currently `*`).
- [ ] Frontend bundle hosting on a CDN / static host with proper cache
      headers.
- [ ] Smoke-test pipeline that hits the deployed app post-deploy.
- [ ] Rollback procedure documented.

### Operational readiness

- [ ] On-call / incident runbook.
- [ ] Pharmacy onboarding documentation (admin path to register a new
      pharmacy in our system).
- [ ] Pharmacist onboarding documentation (invite + initial credential
      setup).
- [ ] Customer-support process for common pharmacist issues ("session
      expired", "can't dispense", "wrong patient data").
- [ ] Data-export tooling for compliance audits.
- [ ] Penetration test / external security audit before public launch.

---

## Suggested phasing

1. **Now → 1 week:** finish the *Flow critical path* → read-only live demo
   against real ΗΔΥΚΑ. Side-track: fire the regulatory paperwork
   (`Hd@idika.gr`, HMVO follow-up).
2. **Weeks 2–3:** HL7 dispense builder + HMVS integration once HMVO
   approves.
3. **Weeks 3–6:** the Production-Ready list (secrets, observability, CI,
   deployment).
4. **Pre-launch:** legal/compliance review, pen test, customer-support
   process.

## Related docs

- [`going-real-live-mode-ux.md`](./going-real-live-mode-ux.md) — why the
  dashboard concept needs to change (event-driven, not queue-driven).
- [`going-real-audit.md`](./going-real-audit.md) — original "going real"
  audit (pre-dates the HL7 discovery).
- [`sprint-split.md`](./sprint-split.md) — the original sprint allocation
  with tickets T1–T15.
