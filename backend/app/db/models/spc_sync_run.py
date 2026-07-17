# One row per SPC batch-fetch run — the freshness + failure-surfacing record
# behind GET /admin/spc/status (same philosophy as catalog_sync_runs: a decay
# in automated fetching must be visible, not buried in container logs).
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base, TimestampMixin


class SpcSyncRun(Base, TimestampMixin):
    __tablename__ = "spc_sync_runs"
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    mode: Mapped[str] = mapped_column(String(16), nullable=False)  # batch | single
    status: Mapped[str] = mapped_column(  # running | success | error
        String(16), nullable=False, default="running", server_default=text("'running'")
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    examined: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    fetched_docs: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    parsed_docs: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    failed: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    error: Mapped[str | None] = mapped_column(Text)
    # Who started it — "admin:<email>" from the endpoint, "scan"/"cli" otherwise.
    triggered_by: Mapped[str | None] = mapped_column(String)
