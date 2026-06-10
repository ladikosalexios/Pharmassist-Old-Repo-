# One billable B2B location (the pricing unit: €/location/month). Carries its own
# ΗΔΥΚΑ identity: pharmapi_unit_id (the upstream pharmacy unit, ΗΔΥΚΑ's "idika
# pharmacy id") plus Pharmapi Basic-Auth credentials AES-256-GCM-encrypted under
# CREDENTIAL_ENCRYPTION_KEY (same app/crypto.py pattern as pharmacist_pharmacies).
# Never log the decrypted values.
import uuid

from sqlalchemy import Boolean, ForeignKey, Integer, String, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..base import Base, TimestampMixin


class Location(Base, TimestampMixin):
    __tablename__ = "locations"
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    customer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("customers.id"), nullable=False
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    address: Mapped[str | None] = mapped_column(String)
    # ΗΔΥΚΑ pharmacy unit id (units[0].id from /user/me) — same convention as
    # pharmacies.pharmapi_unit_id. Embedded in intolerance/medicine-history URLs.
    pharmapi_unit_id: Mapped[int] = mapped_column(Integer, nullable=False)
    # AES-256-GCM ciphertext (base64) — decrypted in-memory per request only.
    pharmapi_username: Mapped[str | None] = mapped_column(String)
    pharmapi_password: Mapped[str | None] = mapped_column(String)
    # ΕΟΠΥΥ category flag (ΗΔΥΚΑ "isIka"). Gates patient intolerances and medicine
    # history — non-ΕΟΠΥΥ accounts get upstream error 609 on those endpoints.
    is_eopyy: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    customer: Mapped["Customer"] = relationship(back_populates="locations")
    api_keys: Mapped[list["ApiKey"]] = relationship(back_populates="location")
