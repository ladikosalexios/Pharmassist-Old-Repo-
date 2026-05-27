"""Append-only audit trail for pharmacist documentation actions.
SECURITY: Never write Api-Key, Authorization, or credentials into request_body.
"""

import contextlib
from datetime import UTC, datetime

from ..db.models.audit_log import AuditLog
from ..db.session import AsyncSessionLocal


async def log_documentation_action(*, pharmacist_id, pharmacy_id, action, resource_id=None):
    with contextlib.suppress(Exception):
        async with AsyncSessionLocal() as session:
            row = AuditLog(
                pharmacist_id=pharmacist_id,
                pharmacy_id=pharmacy_id,
                action=action,
                resource_type="PRESCRIPTION",
                resource_id=resource_id,
                occurred_at=datetime.now(UTC),
            )
            session.add(row)
            await session.commit()
