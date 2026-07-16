# Scan log: one row per barcode scan that resolved a prescription, with the
# full normalized prescription payload AND a patient snapshot at scan time.
# This is the retrieval-only product's local record of what crossed the
# counter — there is no dispense_logs anymore (tag hmvs-certified), so this
# is what powers "what did we look at, for whom, and what did the safety
# engine say at that moment". Written fire-and-forget (services/scan_log.py)
# so a slow patient-snapshot fetch never delays the scan response.
import uuid

from sqlalchemy import ForeignKey, Index, String, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base, TimestampMixin


class PrescriptionScan(Base, TimestampMixin):
    __tablename__ = "prescription_scans"
    __table_args__ = (
        Index("ix_prescription_scans_pharmacy_created", "pharmacy_id", "created_at"),
        Index("ix_prescription_scans_barcode", "barcode"),
        Index("ix_prescription_scans_patient_amka", "patient_amka"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    pharmacy_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("pharmacies.id"), nullable=False
    )
    pharmacist_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("pharmacists.id"), nullable=False
    )
    barcode: Mapped[str] = mapped_column(String, nullable=False)
    # Mapped internal status (PENDING/COMPLETED/FLAGGED/UNKNOWN) + the raw
    # upstream string, so mapping drift stays diagnosable after the fact.
    status: Mapped[str] = mapped_column(String, nullable=False)
    pharmapi_status: Mapped[str | None] = mapped_column(String)
    patient_amka: Mapped[str | None] = mapped_column(String)
    patient_name: Mapped[str | None] = mapped_column(String)
    source: Mapped[str] = mapped_column(String, nullable=False)  # "live" | "mock"
    # Full normalized prescription dict incl. therapyLines + the safety-check
    # snapshot at scan time (the legal moment-in-time record).
    rx_payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    # Patient profile snapshot (demographics + intolerances) fetched at scan
    # time; None when the lookup failed — never blocks the scan itself.
    patient_payload: Mapped[dict | None] = mapped_column(JSONB)
