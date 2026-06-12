"""B2B /v1 ADR events — audit trail for b2b_adr_reports (mirrors adr_events)."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..base import Base, TimestampMixin


class B2bAdrEvent(Base, TimestampMixin):
    __tablename__ = "b2b_adr_events"
    __table_args__ = (Index("ix_b2b_adr_events_adr_id", "adr_id"),)
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    adr_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("b2b_adr_reports.id"), nullable=False
    )
    # API-key actor — no pharmacist row on the /v1 surface.
    actor_api_key_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("api_keys.id"), nullable=True
    )
    event_type: Mapped[str] = mapped_column(String, nullable=False)
    from_status: Mapped[str | None] = mapped_column(String)
    to_status: Mapped[str | None] = mapped_column(String)
    notes: Mapped[str | None] = mapped_column(String)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    report: Mapped["B2bAdrReport"] = relationship(back_populates="events")
