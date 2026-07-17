import uuid
from decimal import Decimal

from sqlalchemy import Boolean, Numeric, String, text
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
    # NOTE: despite the name this stores the EOF *barcode* from Pharmapi
    # masterdata (services/drug_catalog._to_row) — the /v1 contract exposes it
    # honestly as `barcode`.
    gns_code: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    # Indexed for formulary same-class queries (ATC prefix scans).
    atc_code: Mapped[str] = mapped_column(String, nullable=False, index=True)
    atc_class: Mapped[str] = mapped_column(String, nullable=False)
    name_gr: Mapped[str] = mapped_column(String, nullable=False)
    # Holds the main active-substance INN description, not an English brand name.
    name_en: Mapped[str | None] = mapped_column(String)
    interaction_group: Mapped[str | None] = mapped_column(String)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # ── Formulary columns (BC-13; field mapping in docs/b2b-core/masterdata-probe.md) ──
    # All nullable: rows synced before this migration / seed rows have no values
    # until the next full masterdata sync. eopyy_coverage is tri-state — None
    # means "unknown", and the formulary endpoint surfaces that as a caveat.
    form_code: Mapped[str | None] = mapped_column(String)  # pharmaceutical form (formCode)
    strength_raw: Mapped[str | None] = mapped_column(String)  # upstream `content` text
    strength_value: Mapped[Decimal | None] = mapped_column(Numeric)
    strength_unit: Mapped[str | None] = mapped_column(String)
    retail_price: Mapped[Decimal | None] = mapped_column(Numeric)
    reference_price: Mapped[Decimal | None] = mapped_column(Numeric)
    eopyy_coverage: Mapped[bool | None] = mapped_column(Boolean)  # positiveList
    participation_pct: Mapped[Decimal | None] = mapped_column(Numeric)
    substance_code: Mapped[str | None] = mapped_column(String)  # main activeSubstance.code
    package_size: Mapped[str | None] = mapped_column(String)  # piecesPerPackage
    # ΕΟΦ product code from masterdata `eofCode` — the key the ΕΟΦ portal's
    # product search understands (SPC/ΦΟΧ document lookup). Nullable: rows
    # synced before this column filled on the next full sync.
    eof_code: Mapped[str | None] = mapped_column(String, index=True)
