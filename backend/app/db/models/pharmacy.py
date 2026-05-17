import uuid

from sqlalchemy import Boolean, Integer, String, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..base import Base, TimestampMixin


class Pharmacy(Base, TimestampMixin):
    __tablename__ = "pharmacies"
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    address: Mapped[str | None] = mapped_column(String)
    street_name: Mapped[str | None] = mapped_column(String)  # e.g. "ΛΕΩΦΟΡΟΣ ΠΕΝΤΕΛΗΣ"
    # String not Integer — Greek addresses can be "12A", "138Β" etc.
    street_number: Mapped[str | None] = mapped_column(String)
    area: Mapped[str | None] = mapped_column(String)  # Neighbourhood / district — e.g. "ΧΑΛΑΝΔΡΙ"
    city: Mapped[str | None] = mapped_column(String)  # e.g. "ΑΘΗΝΑ"
    # 5-digit Greek postal code stored as string — e.g. "15234"
    postal_code: Mapped[str | None] = mapped_column(String)
    phone: Mapped[str | None] = mapped_column(String)  # Primary contact phone
    fax: Mapped[str | None] = mapped_column(String)  # Fax number
    # Pharmacy contact email (not the pharmacist's personal email)
    email: Mapped[str | None] = mapped_column(String)
    # Prefecture-level — e.g. "ΧΑΛΑΝΔΡΙ ΑΤΤΙΚΗ"
    geographic_region: Mapped[str | None] = mapped_column(String)
    # "B" or "C" (Β' or Γ' Κατηγορίας per Greek accounting law)
    accounting_category: Mapped[str | None] = mapped_column(String)
    # True if this pharmacy is a branch of another; False = main pharmacy
    is_branch: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    tax_id: Mapped[str | None] = mapped_column(String)
    pharmapi_unit_id: Mapped[int] = mapped_column(Integer, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    pharmacist_links: Mapped[list["PharmacistPharmacy"]] = relationship(back_populates="pharmacy")
