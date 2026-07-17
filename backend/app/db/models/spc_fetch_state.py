# Retry/backoff state for automated SPC document fetching, one row per
# (barcode, source). Deliberately a separate table from spc_documents: backoff
# state exists precisely when NO document exists yet, and keying per source
# means a dead ΕΟΦ portal never blocks the EMA adapter. Rows are deleted on a
# successful fetch.
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base, TimestampMixin


class SpcFetchState(Base, TimestampMixin):
    __tablename__ = "spc_fetch_state"
    __table_args__ = (
        UniqueConstraint("barcode", "source"),
        Index("ix_spc_fetch_state_next_attempt", "next_attempt_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    barcode: Mapped[str] = mapped_column(String, nullable=False)
    source: Mapped[str] = mapped_column(String(10), nullable=False)  # eof | ema
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
