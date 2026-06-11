# Append-only operator audit for the b2b_admin CLI — every privileged tenant
# mutation (tier/entitlement, credential, and API-key lifecycle changes) lands
# one row here. Never updated or deleted in normal operation.
#
# Deliberately FK-free: target_id is plain text, NOT a foreign key into
# customers/locations/api_keys. The row must survive its target's later removal
# (an audit trail you can CASCADE-delete is no audit trail) and must never ride
# a reseed's TRUNCATE ... CASCADE — same FK-free posture as the tenancy tables.
#
# SECURITY: `details` must NEVER carry a raw API key or a Pharmapi credential
# (plaintext or ciphertext). The CLI builders only put non-secret context here
# (ids, labels, tier from→to, unit id, eopyy flag).
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Index, String, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base, TimestampMixin


class B2bAdminAudit(Base, TimestampMixin):
    __tablename__ = "b2b_admin_audit"
    # Forensic lookup: "what happened to this customer / location / key".
    __table_args__ = (Index("ix_b2b_admin_audit_target", "target_type", "target_id"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    # Operator identity — the OS user running the CLI, overridable via --actor.
    actor: Mapped[str] = mapped_column(String, nullable=False)
    # Verb, from the ACTIONS vocabulary in services/b2b_admin_audit.py.
    action: Mapped[str] = mapped_column(String, nullable=False)
    target_type: Mapped[str | None] = mapped_column(String)  # CUSTOMER | LOCATION | API_KEY
    target_id: Mapped[str | None] = mapped_column(String)  # uuid as text — no FK by design
    details: Mapped[dict | None] = mapped_column(JSONB)  # non-secret before→after + context
    # The semantic "when the action happened" timestamp, and what list_audit
    # orders by. Distinct from TimestampMixin.created_at (row-insert provenance):
    # they're set within the same insert here, but occurred_at is the audited
    # fact and is queried/ordered as such, mirroring audit_log.occurred_at.
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
