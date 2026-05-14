import uuid

from sqlalchemy import Boolean, String, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base, TimestampMixin


class SafetyRule(Base, TimestampMixin):
    __tablename__ = "safety_rules"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    rule_code: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    check_type: Mapped[str] = mapped_column(String, nullable=False)
    trigger_atc: Mapped[str | None] = mapped_column(String)
    trigger_condition_code: Mapped[str | None] = mapped_column(String)
    conflicting_atc: Mapped[str | None] = mapped_column(String)
    severity: Mapped[str] = mapped_column(String, nullable=False)
    message_en: Mapped[str] = mapped_column(String, nullable=False)
    details_en: Mapped[str | None] = mapped_column(Text)
    recommended_action_en: Mapped[str | None] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
