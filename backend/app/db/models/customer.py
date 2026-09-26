# B2B tenant root — a company (pharmacy chain, cooperative, OS vendor) buying API access.
# Deliberately FK-free from every seeded table: scripts/seed.py TRUNCATEs its tables
# CASCADE on reseed and must never be able to reach tenant data.
import uuid

from sqlalchemy import Boolean, CheckConstraint, String, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..base import Base, TimestampMixin


class Customer(Base, TimestampMixin):
    __tablename__ = "customers"
    # DB-level guard mirroring migrations c9e1a7b4f203 + e5b1c9d47a20 — keep them
    # in sync if the tier vocabulary ever changes (also TIER_ORDER in
    # routers/v1/deps.py). name="tier" renders as ck_customers_tier through the
    # metadata naming convention, matching the migrated constraint.
    __table_args__ = (
        CheckConstraint(
            "tier IN ('clinical_only', 'core', 'clinical', 'platform')",
            name="tier",
        ),
    )
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    contact_email: Mapped[str | None] = mapped_column(String)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # Entitlement tier (T2-1 / D-14: customer-level — the whole estate is one
    # tier). Ordinal: platform >= clinical >= core >= clinical_only (D-20). The
    # /v1 gate reads it through the customer row get_api_context already loads
    # per request and grants when the customer's rank meets or exceeds the
    # route's minimum. Validated at the CLI/app boundary; an unknown value fails
    # safe (ranks as the base tier, clinical_only) in the gate. The insert
    # default stays 'core' — onboarding onto the new base tier is an explicit
    # `--tier clinical_only`, never a silent downgrade of the existing default.
    tier: Mapped[str] = mapped_column(
        String, nullable=False, default="core", server_default=text("'core'")
    )
    locations: Mapped[list["Location"]] = relationship(back_populates="customer")
