"""Audit-log writes for company-staff actions.

The first writer of the `audit_log` table — staff-initiated admin actions land
here with `staff_id` set and `pharmacist_id` NULL. The caller is responsible
for committing, so the mutation and its audit row land in one transaction.
"""

import uuid

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.models.audit_log import AuditLog


def write_staff_audit(
    db: AsyncSession,
    *,
    staff_id: str,
    action: str,
    resource_type: str | None = None,
    resource_id: str | None = None,
    pharmacy_id: str | None = None,
    request_body: dict | None = None,
    request: Request | None = None,
) -> None:
    """Stage an audit row for a staff action. Does NOT commit — the calling
    endpoint commits it alongside the mutation it records.

    `request_body` must already be sanitised — never pass passwords or
    credentials (the audit_log table is not a place for secrets).
    """
    db.add(
        AuditLog(
            staff_id=uuid.UUID(staff_id),
            pharmacist_id=None,
            pharmacy_id=uuid.UUID(pharmacy_id) if pharmacy_id else None,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            request_body=request_body,
            ip_address=request.client.host if request and request.client else None,
            user_agent=request.headers.get("user-agent") if request else None,
        )
    )
