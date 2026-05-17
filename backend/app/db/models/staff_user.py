import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base, TimestampMixin


class StaffUser(Base, TimestampMixin):
    """PharmAssist company staff — accounts for the admin portal.

    Distinct from Pharmacist: staff have no pharmacy, no ΗΔΥΚΑ credentials and
    no EOF licence. They authenticate via /admin/login on a separate cookie.
    """

    __tablename__ = "staff_users"
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    email: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String, nullable=False)
    full_name: Mapped[str] = mapped_column(String, nullable=False)
    # "admin" today — reserved for a future super-admin tier.
    role: Mapped[str] = mapped_column(
        String, nullable=False, default="admin", server_default=text("'admin'")
    )
    active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
