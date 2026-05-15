import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, select, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column, relationship, selectinload

from ..base import Base, TimestampMixin


class Pharmacist(Base, TimestampMixin):
    __tablename__ = "pharmacists"
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    email: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String, nullable=False)
    full_name: Mapped[str] = mapped_column(String, nullable=False)
    eof_licence_no: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    phone: Mapped[str | None] = mapped_column(String)
    role: Mapped[str] = mapped_column(String, nullable=False, default="pharmacist")
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    pharmacy_links: Mapped[list["PharmacistPharmacy"]] = relationship(back_populates="pharmacist")
    recorded_conditions: Mapped[list["PatientCondition"]] = relationship(
        back_populates="recorded_by_pharmacist"
    )

    async def get_default_pharmacy_link(self, session: AsyncSession):
        """Return the PharmacistPharmacy row marked ``is_default=True`` for
        this pharmacist, with the Pharmacy eagerly loaded so callers can
        reach ``link.pharmacy`` without a second round-trip. ``None`` if no
        default link exists."""
        # Lazy import to keep model module imports acyclic — pharmacist_pharmacy
        # only forward-ref strings Pharmacist back to here.
        from .pharmacist_pharmacy import PharmacistPharmacy

        return await session.scalar(
            select(PharmacistPharmacy)
            .where(
                PharmacistPharmacy.pharmacist_id == self.id,
                PharmacistPharmacy.is_default.is_(True),
            )
            .options(selectinload(PharmacistPharmacy.pharmacy))
        )
