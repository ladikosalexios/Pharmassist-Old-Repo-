# Local patient registry, built passively from counter activity: every scan
# that resolves a prescription upserts its patient here (services/scan_log.py),
# so "recent patients" and patient lookups work from data the pharmacy has
# actually seen — ΗΔΥΚΑ has no "list my patients" feed to pull.
# Scoped per pharmacy (UNIQUE pharmacy_id+amka): each pharmacy only ever sees
# patients who visited IT.
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base, TimestampMixin


class Patient(Base, TimestampMixin):
    __tablename__ = "patients"
    __table_args__ = (
        UniqueConstraint("pharmacy_id", "amka"),
        Index("ix_patients_pharmacy_last_seen", "pharmacy_id", "last_seen_at"),
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
    amka: Mapped[str] = mapped_column(String, nullable=False)
    name: Mapped[str | None] = mapped_column(String)
    age: Mapped[int | None] = mapped_column(Integer)
    sex: Mapped[str | None] = mapped_column(String)
    phone: Mapped[str | None] = mapped_column(String)
    # Full profile snapshot from patients.resolve (demographics + intolerances
    # + safety flags) as of the LAST visit; None when the lookup failed and we
    # only know identity from the prescription itself.
    profile: Mapped[dict | None] = mapped_column(JSONB)
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
