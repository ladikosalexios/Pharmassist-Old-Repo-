# One billable B2B location (the pricing unit: €/location/month). Carries its own
# ΗΔΥΚΑ identity: pharmapi_unit_id (the upstream pharmacy unit, ΗΔΥΚΑ's "idika
# pharmacy id") plus Pharmapi Basic-Auth credentials AES-256-GCM-encrypted under
# CREDENTIAL_ENCRYPTION_KEY (same app/crypto.py pattern as pharmacist_pharmacies).
# Never log the decrypted values.
#
# The ΗΔΥΚΑ identity is OPTIONAL (TIER0-RETRIEVAL-FREE.md T0-4): a location
# provisioned with `b2b_admin create-location --no-retrieval` has all three
# columns NULL and serves only the upstream-free /v1 routes; retrieval routes
# answer 409 retrieval_unavailable. The check constraint keeps the credentials
# both-or-neither (a blank string counts as unset) and requires a unit id
# whenever they are set, so a half-provisioned row can't exist.
import uuid

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Integer, String, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..base import Base, TimestampMixin


class Location(Base, TimestampMixin):
    __tablename__ = "locations"
    # Mirrors migration e5b1c9d47a20 (renders as ck_locations_pharmapi_credentials).
    __table_args__ = (
        CheckConstraint(
            "(NULLIF(pharmapi_username, '') IS NULL) = (NULLIF(pharmapi_password, '') IS NULL) "
            "AND (NULLIF(pharmapi_username, '') IS NULL OR pharmapi_unit_id IS NOT NULL)",
            name="pharmapi_credentials",
        ),
    )
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
    # NULL only on a location provisioned without ΗΔΥΚΑ credentials.
    pharmapi_unit_id: Mapped[int | None] = mapped_column(Integer)
    # AES-256-GCM ciphertext (base64) — decrypted in-memory per request only.
    # Both NULL on a location provisioned without ΗΔΥΚΑ credentials.
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
