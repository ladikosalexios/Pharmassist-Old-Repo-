"""Append-only audit trail for pharmacist state-changing actions.
SECURITY: Never write Api-Key, Authorization, Bearer tokens, credentials, or a
full pack QR into request_body / resource_id.
"""

import asyncio
import logging
import uuid
from typing import Literal

from ..db.models.audit_log import AuditLog
from ..db.session import AsyncSessionLocal

_log = logging.getLogger(__name__)
_background_tasks: set = set()

# HMVS pack-lifecycle actions. Extend this union rather than passing arbitrary
# strings — keeps the audit vocabulary inspector-defensible.
HmvsAction = Literal["HMVS_VERIFIED", "HMVS_DECOMMISSIONED", "HMVS_REACTIVATED"]


async def log_documentation_action(
    *,
    pharmacist_id: uuid.UUID | None,
    pharmacy_id: uuid.UUID | None,
    action: str,
    resource_id: str | None = None,
) -> None:
    try:
        async with AsyncSessionLocal() as session:
            row = AuditLog(
                pharmacist_id=pharmacist_id,
                pharmacy_id=pharmacy_id,
                action=action,
                resource_type="PRESCRIPTION",
                resource_id=resource_id,
            )
            session.add(row)
            await session.commit()
    except Exception:
        _log.warning("audit log failed", exc_info=True)


async def log_hmvs_action(
    *,
    pharmacist_id: uuid.UUID | None,
    pharmacy_id: uuid.UUID | None,
    action: HmvsAction,
    resource_id: str | None = None,
    pharmapi_path: str | None = None,
    pharmapi_status: int | None = None,
) -> None:
    """Append one HMVS audit row. ``resource_id`` is the pack SERIAL (never the
    full QR). Uses its own session so the caller's transaction can roll back
    without losing the audit row, and never propagates — a failed audit write is
    logged, not surfaced to the pharmacist."""
    try:
        async with AsyncSessionLocal() as session:
            row = AuditLog(
                pharmacist_id=pharmacist_id,
                pharmacy_id=pharmacy_id,
                action=action,
                resource_type="HMVS_PACK",
                resource_id=resource_id,
                pharmapi_path=pharmapi_path,
                pharmapi_status=pharmapi_status,
            )
            session.add(row)
            await session.commit()
    except Exception:
        _log.warning("hmvs audit log failed", exc_info=True)


def fire_hmvs_audit(**kwargs) -> None:
    """Schedule ``log_hmvs_action`` as a tracked fire-and-forget task.

    Keeps the fire-and-forget plumbing out of the router: the endpoint calls
    this one function. The strong reference in ``_background_tasks`` is what
    stops the GC reclaiming the task before it runs (PR #76 bot-review lesson);
    the shutdown drain in ``main.py`` awaits the set so a SIGTERM mid-dispense
    doesn't drop the row."""
    task = asyncio.create_task(log_hmvs_action(**kwargs))
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
