# B2B tenant root — a company (pharmacy chain, cooperative, OS vendor) buying API access.
# Deliberately FK-free from every seeded table: scripts/seed.py TRUNCATEs its tables
# CASCADE on reseed and must never be able to reach tenant data.
import uuid

from sqlalchemy import Boolean, String, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..base import Base, TimestampMixin


class Customer(Base, TimestampMixin):
    __tablename__ = "customers"
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    contact_email: Mapped[str | None] = mapped_column(String)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    locations: Mapped[list["Location"]] = relationship(back_populates="customer")
