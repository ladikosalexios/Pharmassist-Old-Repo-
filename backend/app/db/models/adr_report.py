import uuid
from datetime import datetime
from sqlalchemy import String, DateTime, ForeignKey, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from ..base import Base, TimestampMixin

class AdrReport(Base, TimestampMixin):
    __tablename__ = "adr_reports"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()"))
    pharmacist_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("pharmacists.id"), nullable=False)
    pharmacy_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("pharmacies.id"), nullable=False)
    patient_amka: Mapped[str | None] = mapped_column(String)
    patient_name: Mapped[str | None] = mapped_column(String)
    medicine_barcode: Mapped[str | None] = mapped_column(String)
    medicine_name: Mapped[str | None] = mapped_column(String)
    atc_code: Mapped[str | None] = mapped_column(String)
    symptom_description: Mapped[str] = mapped_column(String, nullable=False)
    onset_timing: Mapped[str | None] = mapped_column(String)
    severity: Mapped[str | None] = mapped_column(String)  # MILD | MODERATE | SEVERE
    status: Mapped[str] = mapped_column(String, nullable=False, default="PENDING_REVIEW")  # PENDING_REVIEW | ESCALATED | EOF_REPORTED | CLOSED
    eof_report_ref: Mapped[str | None] = mapped_column(String)
    reported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    events: Mapped[list["AdrEvent"]] = relationship(back_populates="report", order_by="AdrEvent.occurred_at")
