"""Private reporting data. Submission rows are also the transactional outbox."""

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    LargeBinary,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base, TimestampMixin


class Owned:
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    pharmacist_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("pharmacists.id"), nullable=False
    )
    pharmacy_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("pharmacies.id"), nullable=False
    )


class YellowSignature(Owned, Base, TimestampMixin):
    __tablename__ = "yellow_signatures"
    image: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class YellowReport(Owned, Base, TimestampMixin):
    __tablename__ = "yellow_reports"
    __table_args__ = (CheckConstraint("revision > 0", name="positive_revision"),)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    payload: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)


class YellowPreview(Owned, Base):
    __tablename__ = "yellow_previews"
    report_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("yellow_reports.id"), nullable=False
    )
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    signature_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("yellow_signatures.id"), nullable=False
    )
    payload: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    pdf: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    template_version: Mapped[str] = mapped_column(String, nullable=False)
    envelope: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    envelope_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )


class YellowSubmission(Owned, Base, TimestampMixin):
    __tablename__ = "yellow_submissions"
    __table_args__ = (
        UniqueConstraint("pharmacist_id", "pharmacy_id", "idempotency_key"),
        UniqueConstraint("preview_id"),
        CheckConstraint(
            "status IN ('QUEUED','SENDING','CAPTURED_LOCAL','FAILED','UNKNOWN','CANCELLED')",
            name="status",
        ),
    )
    preview_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("yellow_previews.id"), nullable=False
    )
    idempotency_key: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="QUEUED")
    transport: Mapped[str] = mapped_column(String, nullable=False, default="local_capture")
    approved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    approval_version: Mapped[str] = mapped_column(String, nullable=False, default="local-v1")
    attempted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failure_code: Mapped[str | None] = mapped_column(String)


class YellowEvent(Base):
    __tablename__ = "yellow_events"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    submission_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("yellow_submissions.id"), nullable=False
    )
    kind: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )
