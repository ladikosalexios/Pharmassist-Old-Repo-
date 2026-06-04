---
name: audit-log
description: Use this skill when adding regulator-facing audit-trail entries to backend endpoints (dispense, ADR submission, prescription patch, settings change, credential rotation, HMVS verify/decommission/reactivate). Encodes the fire-and-forget pattern from PR #76 plus the shutdown drain handler so audit rows survive graceful restarts.
---

# audit-log — write append-only audit rows from a state-changing endpoint

## When to use

The user is adding or modifying a backend endpoint that mutates state and
should leave an EOF-inspector-defensible audit trail. Concretely: dispense,
prescription approve/flag, ADR submit, settings change, credential rotation,
HMVS verify / decommission / reactivate, staff invite acceptance.

## What "audit log" means here

The repo has an `AuditLog` model and `app/services/audit.py` (introduced in
PR #76). Existing call sites pattern:

```python
# app/services/documentation.py:record_prescription_action(...)
log = DocumentationLog(...)
session.add(log)
await session.commit()
await session.refresh(log)

# Fire the audit task — never blocks the caller-facing response
task = asyncio.create_task(
    log_documentation_action(
        pharmacist_id=pharmacist_id,
        pharmacy_id=pharmacy_id,
        action=f"PRESCRIPTION_{action_type}D",  # APPROVED / FLAGGED
        resource_id=rx["rxId"],
    )
)
_background_tasks.add(task)
task.add_done_callback(_background_tasks.discard)
```

## Inputs the agent MUST gather

1. **Read `backend/app/services/audit.py`** — see the canonical pattern.
   Action constants live there; reuse rather than invent new ones.
2. **Read `backend/app/db/models/audit_log.py`** — confirm the column set
   (action, resource_type, resource_id, pharmacist_id, pharmacy_id,
   occurred_at via server-side default).
3. **Read `main.py` shutdown handler** — confirm `_drain_audit_tasks` is
   registered. If it's not, that's a follow-up gap to flag (see DO NOT
   below).

## Rules for writing the audit call

### Action naming
- Format: `<RESOURCE>_<VERB_PAST>` — e.g. `PRESCRIPTION_APPROVED`,
  `PRESCRIPTION_FLAGGED`, `ADR_SUBMITTED`, `HMVS_VERIFIED`,
  `HMVS_DECOMMISSIONED`, `SETTINGS_CHANGED`.
- Existing actions live in `app/services/audit.py` — extend the literal
  type union there; never accept arbitrary strings.

### Resource identification
- `resource_type` is a coarse bucket: `PRESCRIPTION`, `ADR_REPORT`,
  `HMVS_PACK`, `STAFF_INVITE`, `SETTINGS`.
- `resource_id` is the natural identifier the inspector will search for —
  Rx barcode, pack serial (NOT full QR), invite token, etc.
- **Never put a full QR code in `resource_id`** — it contains the serial
  which is privacy-sensitive (HMVO guidance).

### Fire-and-forget plumbing
- Create the task via `asyncio.create_task(...)`.
- Register it in `_background_tasks` and attach `discard` as a done
  callback. The set keeps a strong reference so the GC can't collect the
  task before it runs. This is the bug the PR #76 bot review caught — do
  not skip it.
- Use an independent `AsyncSessionLocal()` inside the audit service so the
  caller's transaction can roll back without losing the audit row.

### Error handling
- Audit failures must NOT propagate. Use `try / except Exception` and log
  at WARNING with `exc_info=True`. The pharmacist-facing call has already
  succeeded; an audit hiccup is a logging issue, not a user issue.
- Never use a bare `contextlib.suppress(Exception)` — that swallows the
  error without surfacing anything to log aggregators. (Bot review PR #76.)

### Sensitive payloads
- `request_body` stays `None` until a per-endpoint sanitisation review
  has happened. Never write tokens, passwords, `Api-Key` headers, or
  bearer tokens into the audit table.

## Shutdown drain — required for new state-changing endpoints

If `main.py` does NOT have a `@app.on_event("shutdown")` handler that
awaits `_background_tasks`, add one as part of this work. Without it,
in-flight audit tasks are dropped on graceful restart — which means a
pharmacist's last action of the shift can vanish from the audit log.
Pattern (5 lines):

```python
# main.py
import asyncio
from app.services.audit import _background_tasks

@app.on_event("shutdown")
async def _drain_audit_tasks():
    if _background_tasks:
        await asyncio.gather(*_background_tasks, return_exceptions=True)
```

(This is the gap PR #76 left open; close it the first time a new audit
call site is added.)

## Tests

Each new audit call site needs a test that:
1. Mocks `AsyncSessionLocal` via a fixture (see PR #76 test discussion for
   the pattern).
2. Calls the endpoint with success and asserts an AuditLog row was written
   with the right `action` and `resource_id`.
3. Calls the endpoint with the AuditLog write failing, and asserts the
   user-facing response is still 200 (or whatever the success contract is).

## DO NOT

- Do not write the audit row synchronously in the request transaction —
  rolling back the user action would drop the audit, and vice versa.
- Do not log credentials, QR codes, Bearer tokens, or any field the
  endpoint received as a secret.
- Do not invent new action strings in-line; extend the literal in
  `app/services/audit.py`.
- Do not skip the `_background_tasks` registration — discarding the task
  reference lets the GC collect it before it runs. PR #76 review caught
  this; the lesson stuck.
- Do not write to the audit log from a router directly. The pattern is:
  router → service function that does the work → service function calls
  `log_*_action(...)`. Keeps the audit closer to the action-of-record,
  not the HTTP layer.

## Output

A working endpoint that:
- Behaves identically to before from the caller's perspective.
- Writes an `AuditLog` row asynchronously on success.
- Survives audit-write failures without 5xx-ing.
- Survives a SIGTERM with the shutdown drain handler in place.
- Has a test covering the success path AND the audit-failure-doesn't-leak
  path.
