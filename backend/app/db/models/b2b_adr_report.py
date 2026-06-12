"""B2B /v1 ADR reports — the per-LOCATION twin of adr_reports (D-3).

Separate table, not a column on the B2C one: the B2C table's pharmacist_id /
pharmacy_id are NOT NULL FKs so a B2B row cannot be inserted there without a
pharmacist row.  Here the anchor is location_id + created_via_api_key_id,
same vocabulary (status / severity / causality) and same next_status semantics
as the B2C state machine.

EOF_REPORTED is a tracked label only — PharmAssist does not transmit to ΕΟΦ.
eof_report_ref is caller-supplied and stored as a reference string.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.constants import AdrStatus

from ..base import Base, TimestampMixin


class B2bAdrReport(Base, TimestampMixin):
    __tablename__ = "b2b_adr_reports"
    __table_args__ = (
        Index("ix_b2b_adr_reports_location_id", "location_id"),
        Index("ix_b2b_adr_reports_patient_amka", "patient_amka"),
        Index("ix_b2b_adr_reports_reported_at", "reported_at"),
    )
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    location_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("locations.id"), nullable=False
    )
    # Nullable so key deletion never orphans ADR rows.
    created_via_api_key_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("api_keys.id"), nullable=True
    )
    patient_amka: Mapped[str | None] = mapped_column(String)
    patient_name: Mapped[str | None] = mapped_column(String)
    rx_id: Mapped[str | None] = mapped_column(String)
    medicine_barcode: Mapped[str | None] = mapped_column(String)
    medicine_name: Mapped[str | None] = mapped_column(String)
    atc_code: Mapped[str | None] = mapped_column(String)
    symptom_description: Mapped[str] = mapped_column(String, nullable=False)
    onset_timing: Mapped[str | None] = mapped_column(String)
    severity: Mapped[str | None] = mapped_column(String)  # MILD | MODERATE | SEVERE
    causality: Mapped[str | None] = mapped_column(
        String
    )  # Certain | Probable | Possible | Unlikely
    status: Mapped[str] = mapped_column(String, nullable=False, default=AdrStatus.PENDING_REVIEW)
    eof_report_ref: Mapped[str | None] = mapped_column(String)
    reported_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    events: Mapped[list["B2bAdrEvent"]] = relationship(
        back_populates="report", order_by="B2bAdrEvent.occurred_at"
    )
