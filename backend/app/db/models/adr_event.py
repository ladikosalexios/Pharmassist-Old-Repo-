import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..base import Base, TimestampMixin


class AdrEvent(Base, TimestampMixin):
    __tablename__ = "adr_events"
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    adr_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("adr_reports.id"), nullable=False
    )
    actor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("pharmacists.id"), nullable=False
    )
    event_type: Mapped[str] = mapped_column(
        String, nullable=False
    )  # STATUS_CHANGED | PHYSICIAN_NOTIFIED | PATIENT_CONTACTED | EOF_SUBMITTED
    from_status: Mapped[str | None] = mapped_column(String)
    to_status: Mapped[str | None] = mapped_column(String)
    notes: Mapped[str | None] = mapped_column(String)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    report: Mapped["AdrReport"] = relationship(back_populates="events")
