# B2B /v1 — Operations

Operator-facing procedures for the Tier-1 surface. Started by FT-3/FT-4
(masterdata sync); FT-8 extends this with alerting/incident sections when the
public deployment lands (FT-10/D-11).

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
