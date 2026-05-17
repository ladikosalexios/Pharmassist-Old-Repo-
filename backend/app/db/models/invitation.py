import secrets
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..base import Base, TimestampMixin

INVITE_EXPIRE_DAYS = 7


class Invitation(Base, TimestampMixin):
    __tablename__ = "invitations"
    __table_args__ = (Index("ix_invitations_token", "token", unique=True),)
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    # 64-char URL-safe token = 48 bytes = 384 bits of entropy
    token: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    email: Mapped[str] = mapped_column(String, nullable=False)
    pharmacy_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("pharmacies.id"), nullable=False
    )
    # Exactly one of invited_by / invited_by_staff_id is set — a pharmacist or
    # a company staff member. Staff-created invites use the staff column.
    invited_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("pharmacists.id")
    )
    invited_by_staff_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("staff_users.id")
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    pharmacy: Mapped["Pharmacy"] = relationship()
    inviter: Mapped["Pharmacist | None"] = relationship()
    inviter_staff: Mapped["StaffUser | None"] = relationship()

    @staticmethod
    def generate_token() -> str:
        return secrets.token_urlsafe(48)
