# Legal dispensing record. E.O.Φ. required. Retained 5 years.
# pharmacist_signature = SHA256(pharmacist_id + prescription_barcode + dispensed_at + JWT_SECRET)
import uuid
from datetime import datetime
from sqlalchemy import String, DateTime, ForeignKey, Index, text
from sqlalchemy.dialects.postgresql import UUID, INET
from sqlalchemy.orm import Mapped, mapped_column
from ..base import Base, TimestampMixin

class DocumentationLog(Base, TimestampMixin):
    __tablename__ = "documentation_logs"
    __table_args__ = (
        Index("ix_doc_logs_patient_amka_dispensed", "patient_amka", "dispensed_at"),
        Index("ix_doc_logs_pharmacy_dispensed", "pharmacy_id", "dispensed_at"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()"))
    pharmacist_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("pharmacists.id"), nullable=False)
    pharmacy_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("pharmacies.id"), nullable=False)
    prescription_barcode: Mapped[str] = mapped_column(String, nullable=False)
    patient_amka: Mapped[str] = mapped_column(String, nullable=False)
    patient_name: Mapped[str] = mapped_column(String, nullable=False)
    medicine_barcode: Mapped[str | None] = mapped_column(String)
    medicine_name: Mapped[str] = mapped_column(String, nullable=False)
    info_provided: Mapped[str] = mapped_column(String, nullable=False)
    language: Mapped[str] = mapped_column(String, nullable=False, default="el")
    delivery_method: Mapped[str] = mapped_column(String, nullable=False)  # PRINT | DIGITAL | BOTH
    dispensed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    pharmapi_exec_ref: Mapped[str | None] = mapped_column(String)
    exported_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    pharmacist_signature: Mapped[str] = mapped_column(String, nullable=False)
    ip_address: Mapped[str | None] = mapped_column(INET)
    user_agent: Mapped[str | None] = mapped_column(String)
