# Append-only. Never updated or deleted. Partition by month in production.
from datetime import datetime
from sqlalchemy import BigInteger, String, Integer, DateTime, ForeignKey, text
from sqlalchemy.dialects.postgresql import UUID, INET, JSONB
from sqlalchemy.orm import Mapped, mapped_column
from ..base import Base

class AuditLog(Base):
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    pharmacist_id: Mapped[str | None] = mapped_column(UUID(as_uuid=True), ForeignKey("pharmacists.id"))
    pharmacy_id: Mapped[str | None] = mapped_column(UUID(as_uuid=True), ForeignKey("pharmacies.id"))
    action: Mapped[str] = mapped_column(String, nullable=False)
    resource_type: Mapped[str | None] = mapped_column(String)
    resource_id: Mapped[str | None] = mapped_column(String)
    pharmapi_path: Mapped[str | None] = mapped_column(String)
    pharmapi_status: Mapped[int | None] = mapped_column(Integer)
    request_body: Mapped[dict | None] = mapped_column(JSONB)  # sanitised — no credentials ever
    response_code: Mapped[str | None] = mapped_column(String)
    ip_address: Mapped[str | None] = mapped_column(INET)
    user_agent: Mapped[str | None] = mapped_column(String)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
