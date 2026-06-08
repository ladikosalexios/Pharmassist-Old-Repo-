# Idempotency guard + store-and-forward record for HMVS pack state changes.
# One row per (pack, target-state) intent. The UNIQUE idempotency_key is what
# makes a retried PATCH safe: a timeout cannot double-supply because the second
# attempt collides on the key and returns the recorded result instead of issuing
# a fresh upstream call.
import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base, TimestampMixin


class HmvsOperation(Base, TimestampMixin):
    __tablename__ = "hmvs_operations"
    # Enforce the status enum at the DB level too — raw SQL / admin tools must
    # not be able to write a value the idempotency logic doesn't understand.
    __table_args__ = (
        CheckConstraint("status IN ('pending', 'completed', 'failed')", name="status_valid"),
    )
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    # gtin:serial:batch:target_state — deterministic so a retry hashes identically.
    idempotency_key: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    pharmacist_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("pharmacists.id"), nullable=False
    )
    pharmacy_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("pharmacies.id"), nullable=False
    )
    gtin: Mapped[str] = mapped_column(String, nullable=False)
    serial: Mapped[str] = mapped_column(String, nullable=False)
    batch: Mapped[str] = mapped_column(String, nullable=False)
    expiry: Mapped[str | None] = mapped_column(String)
    target_state: Mapped[str] = mapped_column(String, nullable=False)
    # pending → completed | failed. `pending` rows are the store-and-forward
    # queue replay_pending() re-issues; `completed` rows are the idempotency cache.
    status: Mapped[str] = mapped_column(String, nullable=False, server_default=text("'pending'"))
    operation_code: Mapped[str | None] = mapped_column(String)
    response_json: Mapped[dict | None] = mapped_column(JSONB)
    # default=0 (Python-side) so the attribute is concrete right after flush —
    # avoids a sync lazy-load of the server_default in async context; the
    # server_default covers rows written by raw SQL.
    attempts: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
