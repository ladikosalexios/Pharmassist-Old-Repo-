"""Append-only audit trail for pharmacist state-changing actions.
SECURITY: Never write Api-Key, Authorization, Bearer tokens, credentials, or a
full pack QR into request_body / resource_id.
"""

import logging
import uuid

from ..db.models.audit_log import AuditLog
from ..db.session import AsyncSessionLocal

_log = logging.getLogger(__name__)
_background_tasks: set = set()


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
