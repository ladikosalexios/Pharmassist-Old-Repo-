"""Audit-trail helper for the b2b_admin CLI's privileged operator mutations.

One append-only row per state change (tier/entitlement, credentials, key
lifecycle) so an erroneous or unauthorised change is traceable beyond shell
history. Raised as review finding #2 on PR #142.

Two intentional design choices:

* **Same transaction, not fire-and-forget.** Unlike the B2C request-path audit
  (`services/audit.py`, which uses a separate session so a pharmacist action is
  never blocked by an audit failure), an operator mutation is *fail-closed*: the
  audit row is added to the caller's session and commits atomically with the
  change. No tier move (etc.) lands without its audit row, and a failed audit
  rolls the whole thing back. A synchronous CLI that exits immediately also
  can't use the fire-and-forget background-task drain anyway.
* **No secrets in `details`.** Builders here only ever receive non-secret
  context. The raw API key and the Pharmapi credentials never reach this module.
"""

import getpass
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.b2b_admin_audit import B2bAdminAudit

# Action vocabulary — extend this rather than passing arbitrary strings, so the
# trail stays inspector-defensible (same discipline as services/audit.py).
ACTION_CREATE_CUSTOMER = "CREATE_CUSTOMER"
ACTION_SET_TIER = "SET_TIER"
ACTION_CREATE_LOCATION = "CREATE_LOCATION"
# A location provisioned WITHOUT ΗΔΥΚΑ credentials (TIER0-RETRIEVAL-FREE.md T0-4).
# Its own verb, not a CREATE_LOCATION with a flag, so an uncredentialed location
# reads as a deliberate choice in the trail (and is filterable with
# `list-audit --action`) rather than as a half-finished onboarding.
ACTION_CREATE_LOCATION_NO_RETRIEVAL = "CREATE_LOCATION_NO_RETRIEVAL"
ACTION_MINT_KEY = "MINT_KEY"
ACTION_ROTATE_KEY = "ROTATE_KEY"
ACTION_REVOKE_KEY = "REVOKE_KEY"

# Every action, for the `list-audit --action` filter's choices.
ALL_ACTIONS = (
    ACTION_CREATE_CUSTOMER,
    ACTION_SET_TIER,
    ACTION_CREATE_LOCATION,
    ACTION_CREATE_LOCATION_NO_RETRIEVAL,
    ACTION_MINT_KEY,
    ACTION_ROTATE_KEY,
    ACTION_REVOKE_KEY,
)

# Target types.
TARGET_CUSTOMER = "CUSTOMER"
TARGET_LOCATION = "LOCATION"
TARGET_API_KEY = "API_KEY"


def resolve_actor(explicit: str | None) -> str:
    """The operator identity for the trail: the explicit --actor value if given,
    else the OS user running the CLI. Falls back to 'unknown' if the OS user
    can't be determined (e.g. a UID with no passwd entry)."""
    if explicit:
        return explicit
    try:
        return getpass.getuser()
    except Exception:
        return "unknown"


def add_admin_audit(
    session: AsyncSession,
    *,
    actor: str,
    action: str,
    target_type: str | None = None,
    target_id: str | uuid.UUID | None = None,
    details: dict | None = None,
) -> B2bAdminAudit:
    """Stage one audit row on the caller's session — the caller commits it in the
    SAME transaction as the mutation it records (atomic, fail-closed). Returns
    the unpersisted row. ``target_id`` is stringified (it's a plain text column,
    no FK). SECURITY: ``details`` must never carry a raw key or a credential."""
    row = B2bAdminAudit(
        actor=actor,
        action=action,
        target_type=target_type,
        target_id=None if target_id is None else str(target_id),
        details=details,
    )
    session.add(row)
    return row
