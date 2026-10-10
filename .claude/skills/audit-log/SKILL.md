---
name: audit-log
description: Use this skill when adding regulator-facing audit-trail entries to backend endpoints (ADR submission, prescription patch/flag, settings change, credential rotation). Encodes the fire-and-forget pattern from PR #76 plus the shutdown drain handler so audit rows survive graceful restarts.
---

# audit-log — write append-only audit rows from a state-changing endpoint

## When to use

The user is adding or modifying a backend endpoint that mutates state and
should leave an EOF-inspector-defensible audit trail. Concretely:
prescription flag, ADR submit, settings change, credential rotation,
staff invite acceptance.

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
        action={"CONTACT_PRESCRIBER": "PRESCRIBER_CONTACTED"}.get(
            action_type, f"PRESCRIPTION_{action_type}D"
        ),  # Preserve the existing service mapping; review new names explicitly.
        resource_id=rx["rxId"],
    )
)
_background_tasks.add(task)
task.add_done_callback(_background_tasks.discard)
```

## Inputs the agent MUST gather

1. **Read `backend/app/services/audit.py`** — see the canonical pattern.
   `log_documentation_action` accepts `action: str` and fixes `resource_type`
   to `PRESCRIPTION`; it is not a generic helper for every resource.
2. **Read `backend/app/db/models/audit_log.py`** — confirm the column set
   (action, resource_type, resource_id, pharmacist_id, pharmacy_id,
   occurred_at via server-side default).
3. **Read `backend/app/services/documentation.py`** — reuse the existing
   action mapping and task registration in `record_prescription_action`.
4. **Read `backend/main.py` lifespan** — it already drains `_background_tasks`
   with `asyncio.gather(..., return_exceptions=True)` during shutdown.

## Rules for writing the audit call

### Action naming
- Format: `<RESOURCE>_<VERB_PAST>` — e.g. `PRESCRIPTION_FLAGGED`,
  `ADR_SUBMITTED`, `SETTINGS_CHANGED`.
- The helper currently accepts `action: str`; there is no action `Literal`
  union or action-constant registry in `app/services/audit.py`.
- Reuse service-owned action names from existing call sites (including
  `PRESCRIBER_CONTACTED`). Keep naming controlled by the service rather than
  accepting caller-supplied action strings. A typed registry would be a
  separate runtime change, not a prerequisite for following this pattern.

### Resource identification
- The current helper always writes `resource_type="PRESCRIPTION"`. For another
  resource, inspect its existing service; do not pass unsupported arguments
  or label an ADR report, staff invite or settings change as a prescription.
- `resource_id` is the natural identifier the inspector will search for —
  Rx barcode, invite token, etc. Never a secret or privacy-sensitive code.

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

## Shutdown drain — preserve the existing lifespan

`backend/main.py` already passes `lifespan=lifespan` to FastAPI. Its shutdown
cleanup drains the shared task set after stopping the keepalive task:

```python
# Inside the existing lifespan cleanup
if _background_tasks:
    await asyncio.gather(*_background_tasks, return_exceptions=True)
```

Register new tasks in that same set. Do not add a second shutdown handler or
replace the lifespan. This is a graceful-shutdown drain, not durable delivery
after a crash or forced termination. If a new service uses a separate task
set, flag its lifecycle requirements explicitly.

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
- Do not accept action names from request input; reuse or deliberately extend
  the owning service's naming convention.
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
- Drains registered tasks during graceful FastAPI lifespan shutdown.
- Has a test covering the success path AND the audit-failure-doesn't-leak
  path.
