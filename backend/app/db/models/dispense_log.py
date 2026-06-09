# Per-rx eDispensation audit row. Written ONLY after ΗΔΥΚΑ POST returns 200
# and parse_dispense_response yields an executionNo. Persisting on failure
# would leave a phantom dispense in our trail with no corresponding upstream
# record — the router enforces this ordering.
#
# Sibling to DocumentationLog: doc-log is the pharmacist's counselling /
# legal record (5-year EOF retention), dispense-log is the upstream-receipt
# trail that lets us answer "what CDA did we send and receive" during a
# regulator audit. Keep them separate so a doc-log rebuild doesn't replay
# upstream calls.
import uuid

from sqlalchemy import ForeignKey, Index, String, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base, TimestampMixin


class DispenseLog(Base, TimestampMixin):
    __tablename__ = "dispense_logs"
    __table_args__ = (
        Index("ix_dispense_logs_pharmacy_barcode", "pharmacy_id", "barcode"),
        Index("ix_dispense_logs_pharmacy_created", "pharmacy_id", "created_at"),
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
    # ΗΔΥΚΑ executionNo (response id[@root='1.22']). Treated as opaque string.
    exec_ref: Mapped[str] = mapped_column(String, nullable=False)
    # Outbound + inbound CDAs persisted verbatim for the audit trail. PHI guard:
    # never log the bodies, only the exec_ref and the row id.
    request_cda: Mapped[str] = mapped_column(Text, nullable=False)
    response_cda: Mapped[str] = mapped_column(Text, nullable=False)
