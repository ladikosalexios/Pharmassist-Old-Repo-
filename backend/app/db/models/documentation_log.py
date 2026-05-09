# Legal dispensing record + prescription action audit log. E.O.Φ. required. Retained 5 years.
# pharmacist_signature = SHA256(pharmacist_id + prescription_barcode + dispensed_at + JWT_SECRET)
#
# Two row shapes share this table, distinguished by `action_type`:
#   APPROVE — full dispense record. info_provided / delivery_method always set.
#             pharmapi_exec_ref carries the IDIKA execution reference.
#   FLAG    — discrepancy audit. info_provided / delivery_method left NULL.
#             discrepancy_type + notes carry the reason. pharmapi_exec_ref NULL.
import uuid
from datetime import datetime
from sqlalchemy import String, Text, DateTime, ForeignKey, Index, CheckConstraint, text
from sqlalchemy.dialects.postgresql import UUID, INET, JSONB
from sqlalchemy.orm import Mapped, mapped_column
from ..base import Base, TimestampMixin

class DocumentationLog(Base, TimestampMixin):
    __tablename__ = "documentation_logs"
    __table_args__ = (
        Index("ix_doc_logs_patient_amka_dispensed", "patient_amka", "dispensed_at"),
        Index("ix_doc_logs_pharmacy_dispensed", "pharmacy_id", "dispensed_at"),
        CheckConstraint("action_type IN ('APPROVE', 'FLAG')", name="action_type_valid"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()"))
    pharmacist_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("pharmacists.id"), nullable=False)
    pharmacy_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("pharmacies.id"), nullable=False)
    action_type: Mapped[str] = mapped_column(String, nullable=False)  # APPROVE | FLAG
    prescription_barcode: Mapped[str] = mapped_column(String, nullable=False)
    patient_amka: Mapped[str] = mapped_column(String, nullable=False)
    patient_name: Mapped[str] = mapped_column(String, nullable=False)
    medicine_barcode: Mapped[str | None] = mapped_column(String)
    medicine_name: Mapped[str] = mapped_column(String, nullable=False)
    info_provided: Mapped[str | None] = mapped_column(String)  # APPROVE only
    language: Mapped[str] = mapped_column(String, nullable=False, default="el")
    delivery_method: Mapped[str | None] = mapped_column(String)  # APPROVE only: PRINT | DIGITAL | BOTH
    discrepancy_type: Mapped[str | None] = mapped_column(String)  # FLAG only
    notes: Mapped[str | None] = mapped_column(Text)  # FLAG only
    safety_check_snapshot: Mapped[list] = mapped_column(JSONB, nullable=False)
    dispensed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    pharmapi_exec_ref: Mapped[str | None] = mapped_column(String)
    exported_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    pharmacist_signature: Mapped[str] = mapped_column(String, nullable=False)
    ip_address: Mapped[str | None] = mapped_column(INET)
    user_agent: Mapped[str | None] = mapped_column(String)
