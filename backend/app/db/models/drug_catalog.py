import uuid

from sqlalchemy import Boolean, String, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base, TimestampMixin


class DrugCatalog(Base, TimestampMixin):
    __tablename__ = "drug_catalog"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    gns_code: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    atc_code: Mapped[str] = mapped_column(String, nullable=False)
    atc_class: Mapped[str] = mapped_column(String, nullable=False)
    name_gr: Mapped[str] = mapped_column(String, nullable=False)
    name_en: Mapped[str | None] = mapped_column(String)
    interaction_group: Mapped[str | None] = mapped_column(String)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
