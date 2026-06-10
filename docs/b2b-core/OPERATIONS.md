# B2B /v1 — Operations

Operator-facing procedures for the Tier-1 surface. Started by FT-3/FT-4
(masterdata sync); the **Observability & triage** section below is FT-8
(partial). The monitoring *wiring* it references (JSON logs shipped, Sentry
enabled, an external uptime monitor, error-rate alerting) needs the public
deployment target and lands with FT-10/D-11 — those steps are marked
**TODO (FT-10)** so the runbook is complete the day the box exists.

## Masterdata (drug catalogue) sync

The formulary + `/v1/drugs` read the `drug_catalog` table; the sync keeps it
aligned with ΗΔΥΚΑ masterdata. **If the sync stops, formulary quality silently
decays** — that is why every run is recorded.

### Trigger

```bash
# Admin endpoint (202, runs in background; admin session cookie required):
POST /admin/sync-drug-catalog          {"since": "2026-06-01"}   # incremental
POST /admin/sync-drug-catalog          {}                        # full re-sync
```

A **full** sync (no `since`) is required once per environment after the BC-13
migration — rows synced before it have `eopyy_coverage = NULL` (tri-state) and
the `strict` coverage filter would exclude them.

### Status / failure surfacing

```bash
GET /admin/sync-drug-catalog/status
```

Returns the last 10 `catalog_sync_runs` rows (`status: running|success|error`,
counters, `error` text, `triggered_by`) plus the **coverage report** over
active rows: `totalActive`, `with_coverage`, `with_price`,
`with_participation`, `with_form`, `with_substance`.

Reading it:

- last run `error` → the sync is broken; the `error` field carries the
  exception. Re-trigger after fixing; failures also land in the backend log
  (`[sync-drug-catalog]` lines, `logger.exception`).
- last successful run **older than ~48h** → the nightly cron is dead (see
  below) — treat as an incident for a paying tenant, not a curiosity.
- `with_coverage` ≈ 0 while `total_active` is large → the full sync hasn't run
  on this environment (or upstream stopped supplying `positiveList`); the
  formulary `strict` filter would return nothing and `lenient` would carry
  "coverage unknown" caveats on most candidates.

### Nightly schedule (host cron — same pattern as the pilot DB-dump cron)

```cron
# Incremental masterdata sync, 04:10 nightly. `exec -T` = no TTY (cron).
# `date -v-2d` (BSD/mac) / `date -d '2 days ago'` (GNU) — 2-day overlap so a
# missed night self-heals.
10 4 * * * cd /opt/pharmassist && docker compose exec -T backend \
  python -c "import asyncio; from app.services.drug_catalog import run_sync; \
  from datetime import date, timedelta; \
  asyncio.run(run_sync((date.today()-timedelta(days=2)).isoformat(), 'cron'))" \
  >> /var/log/pharmassist-sync.log 2>&1
```

Verify the morning after: `GET /admin/sync-drug-catalog/status` shows a fresh
`success` row with `triggered_by: "cron"`.

### FT-3 onboarding gate (first production sync — D-10 tri-state launch)

Before the first paying location goes live on an environment:

1. Run a **full** sync against production masterdata (needs production-base
   ΗΔΥΚΑ credentials — realistically the first onboarded location's, unless a
   vendor production account exists first).
2. `GET /admin/sync-drug-catalog/status` → `success`, `fetched` in the
   thousands (national list), and `with_coverage` close to `total_active`.
3. Spot-check ~5 known drugs on `GET /v1/drugs?q=…`: `eopyyCoverage`,
   `retailPrice`, `participationPct` look sane (testeps values are
   placeholders — this step exists precisely because value quality was never
   verifiable there; see docs/b2b-core/masterdata-probe.md §Caveats).
4. If production values are junk → stop, escalate: that is the D-10 trigger
   for the ΕΟΦ positive-list import contingency. Do NOT launch `strict`
   filtering on bad data.

## Observability & triage (FT-8, partial)

### Liveness probe — `GET /health/v1`

Unauthenticated and cheap (one `SELECT 1` + one indexed lookup), so an external
monitor can hit it without a key. Defined in `backend/app/routers/health.py`
(`health_v1`). It reports three signals and nothing tenant-specific:

```bash
curl https://api.<domain>/health/v1
{
  "status": "ok",                       # "degraded" when the DB is unreachable
  "version": "0.1.0",                   # APP_VERSION
  "db": { "reachable": true },
  "lastCatalogSync": {                  # newest successful catalog_sync_runs row (FT-4)
    "at": "2026-06-10T16:26:24+00:00",
    "ageSeconds": 9005,
    "stale": false                      # true when age > 48h OR no successful sync yet
  },
  "timestamp": "2026-06-10T18:56:30+00:00"
}
```

- **HTTP 200 + `status: ok`** — DB reachable; the app is serving.
- **HTTP 503 + `status: degraded`** — `SELECT 1` failed (DB down/unreachable).
  This is the page-worthy state; the uptime monitor should alert on the 503.
- **`lastCatalogSync.stale: true`** — the formulary is decaying (nightly sync
  dead or never run). Deliberately does **not** flip the probe to 503: a stale
  catalogue is a warn, not an outage (the 48h threshold mirrors the sync
  section above — `SYNC_STALE_AFTER_SECONDS` in `health.py`). Cross-check with
  `GET /admin/sync-drug-catalog/status` and re-trigger the sync.

`/health` (no `/v1`) is the **legacy pilot-box** probe and reports the in-process
B2C ΗΔΥΚΑ session instead — do not point the B2B monitor at it.

### "ΗΔΥΚΑ is down" vs "we are down" — first-response triage

The single most common page is a spike in /v1 5xx. The envelope makes the
source unambiguous **without** reading application internals, because the error
`code` (`backend/app/routers/v1/errors.py`) and the FT-6 access-log `status`
field (`V1AccessLogMiddleware`, `backend/app/observability.py`) distinguish
upstream failures from ours:

| Envelope `code` | HTTP | Whose fault | First response |
|---|---|---|---|
| `upstream_error` | 5xx (usu. 502) | **ΗΔΥΚΑ** (or the relay to it) | Check ΗΔΥΚΑ status; our box is fine. Don't roll back. `upstream_code` (G-code) often present. |
| `upstream_session_expired` | 401/409 | Transient ΗΔΥΚΑ session (G12/G14) | Self-heals — a new session is established on retry. Only alarming if sustained. |
| `internal` | 500 | **Us** | Our bug/crash. This is the roll-back / Sentry-triage path. |
| `rate_limited` | 429 | The caller (FT-1) | One tenant bursting; not an outage. Identify via `api_key_id` in the access log. |
| `unauthorized` / `forbidden` | 401/403 | The caller | Bad/disabled key, or 609/ΕΟΠΥΥ category mismatch (403 on intolerances/history). |

Triage from the FT-6 access log (one JSON line per /v1 request, keyed by
`api_key_id` / `location_id` / `customer_id`, never PHI):

- **`upstream_error` rate high, `internal` rate flat** → ΗΔΥΚΑ is down. We are
  fine. Communicate "upstream provider degraded", do not deploy.
- **`internal` (500) rate high** → it's us. Roll back the last deploy / triage
  the Sentry issue.
- **One `api_key_id` dominates a 429 or error spike** → tenant-specific (abuse,
  a broken integration loop, or a compromised key — see
  [KEY-MANAGEMENT.md](KEY-MANAGEMENT.md) for the compromise procedure, which
  greps this same log by `api_key_id`).

### Monitoring wiring — TODO (FT-10, needs the public target)

These stand up only once the public TLS box exists (FT-10/D-11); listed here so
the runbook is complete on day one. None are enabled in any current compose.

- **TODO (FT-10): ship JSON logs.** Set `LOG_FORMAT=json` in the B2B compose so
  `configure_logging()` (`observability.py`) emits the FT-6 access lines as
  parseable JSON to the aggregator. Today the prod compose sets neither
  `LOG_FORMAT` nor `SENTRY_DSN`.
- **TODO (FT-10): enable Sentry.** Set `SENTRY_DSN` (+ `SENTRY_ENVIRONMENT=b2b-prod`).
  `send_default_pii=False` is already pinned (`configure_sentry()`), and the
  region/PII stance feeds the FT-14 subprocessor list — Sentry stays off unless
  the org is EU-hosted.
- **TODO (FT-10): external uptime monitor.** Point an UptimeRobot/healthchecks.io
  tier at the public `/health/v1` (alert on 503) **plus** one authenticated
  synthetic — a dedicated monitoring `pa_live_` key hitting `GET /v1/status` —
  so the check measures what the customer experiences, not what the box thinks.
- **TODO (FT-10): error-rate alert.** A Sentry issue-rate alert on `internal`
  5xx + a log-derived threshold over the FT-6 access log's `status` field. Page
  target = the support channel committed in D-11 (SLA TBD).
