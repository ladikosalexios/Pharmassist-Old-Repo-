# G6PD, pregnancy, renal impairment etc. Recorded by pharmacist. Pharmapi does NOT carry this. Powers safety alerts.
import uuid

from sqlalchemy import Boolean, ForeignKey, Index, String, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..base import Base, TimestampMixin


class PatientCondition(Base, TimestampMixin):
    __tablename__ = "patient_conditions"
    __table_args__ = (
        Index("ix_patient_conditions_amka_active", "amka", postgresql_where=text("active = true")),
        # Stop double-click duplicates on the Save-condition modal; one canonical
        # active row per (amka, condition_code). Soft-deleted rows (active=false)
        # stay for audit and are excluded by the partial predicate.
        Index(
            "uq_patient_conditions_amka_condition_active",
            "amka",
            "condition_code",
            unique=True,
            postgresql_where=text("active = true"),
        ),
    )
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    amka: Mapped[str] = mapped_column(String, nullable=False)
    condition_code: Mapped[str] = mapped_column(
        String, nullable=False
    )  # G6PD | PREGNANCY | RENAL_SEVERE | HEPATIC | etc.
    name: Mapped[str] = mapped_column(String, nullable=False)  # e.g. "G6PD Deficiency"
    severity: Mapped[str | None] = mapped_column(String)  # MILD | MODERATE | SEVERE
    notes: Mapped[str | None] = mapped_column(String)
    recorded_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("pharmacists.id"), nullable=False
    )
    pharmacy_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("pharmacies.id"), nullable=False
    )
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    recorded_by_pharmacist: Mapped["Pharmacist"] = relationship(
        back_populates="recorded_conditions"
    )
