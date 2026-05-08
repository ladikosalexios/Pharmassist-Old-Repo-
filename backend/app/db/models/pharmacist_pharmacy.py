# Pharmapi credentials encrypted AES-256-GCM. Key = CREDENTIAL_ENCRYPTION_KEY env var. Never log plaintext.
import uuid
from datetime import datetime
from sqlalchemy import String, Boolean, DateTime, ForeignKey, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from ..base import Base

class PharmacistPharmacy(Base):
    __tablename__ = "pharmacist_pharmacies"
    __table_args__ = (UniqueConstraint("pharmacist_id", "pharmacy_id"),)
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()"))
    pharmacist_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("pharmacists.id"), nullable=False)
    pharmacy_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("pharmacies.id"), nullable=False)
    pharmapi_username: Mapped[str | None] = mapped_column(String)
    pharmapi_password: Mapped[str | None] = mapped_column(String)
    pharmapi_api_key: Mapped[str | None] = mapped_column(String)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    pharmacist: Mapped["Pharmacist"] = relationship(back_populates="pharmacy_links")
    pharmacy: Mapped["Pharmacy"] = relationship(back_populates="pharmacist_links")
