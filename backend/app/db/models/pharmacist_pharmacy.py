# Pharmapi credentials encrypted AES-256-GCM. Key = CREDENTIAL_ENCRYPTION_KEY env var. Never log plaintext.
import uuid

from sqlalchemy import Boolean, ForeignKey, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..base import Base, TimestampMixin


class PharmacistPharmacy(Base, TimestampMixin):
    __tablename__ = "pharmacist_pharmacies"
    __table_args__ = (UniqueConstraint("pharmacist_id", "pharmacy_id"),)
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
    pharmapi_username: Mapped[str | None] = mapped_column(String)
    pharmapi_password: Mapped[str | None] = mapped_column(String)
    # HMVS (ΗΔΥΚΑ/EU-FMD) OAuth2 client-credentials, AES-256-GCM-encrypted at
    # rest under CREDENTIAL_ENCRYPTION_KEY — mirrors pharmapi_*. The IQE
    # "Create-Equipment" Client ID/Secret, NOT a username/password. Nullable:
    # in dev/ITE the shared creds come from env (settings.hmvs_client_*) instead.
    hmvs_client_id: Mapped[str | None] = mapped_column(String)
    hmvs_client_secret: Mapped[str | None] = mapped_column(String)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    pharmacist: Mapped["Pharmacist"] = relationship(back_populates="pharmacy_links")
    pharmacy: Mapped["Pharmacy"] = relationship(back_populates="pharmacist_links")
