# One row per drug-catalogue masterdata sync run (FT-4) — the freshness +
# failure-surfacing record behind GET /admin/sync-drug-catalog/status. The old
# behaviour swallowed every failure into a container-log print; a paid
# formulary endpoint silently decaying because the nightly sync stopped is
# exactly the failure mode this table exists to make visible.
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base, TimestampMixin


class CatalogSyncRun(Base, TimestampMixin):
    __tablename__ = "catalog_sync_runs"
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    mode: Mapped[str] = mapped_column(String(16), nullable=False)  # full | incremental
    since: Mapped[str | None] = mapped_column(String(10))  # YYYY-MM-DD on incremental runs
    status: Mapped[str] = mapped_column(  # running | success | error
        String(16), nullable=False, default="running", server_default=text("'running'")
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    fetched: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    upserted: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    skipped: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    error: Mapped[str | None] = mapped_column(Text)
    # Who started it — "admin:<email>" from the endpoint, "cron"/"cli" otherwise.
    triggered_by: Mapped[str | None] = mapped_column(String)
