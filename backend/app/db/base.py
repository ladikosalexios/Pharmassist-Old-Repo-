from datetime import datetime
from sqlalchemy import DateTime, MetaData, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class TimestampMixin:
    # `onupdate=now()` makes SQLAlchemy emit the new value in its UPDATE
    # statements (so `obj.updated_at` is fresh after flush via RETURNING).
    # It does NOT cover updates from raw SQL, psql, or any other writer
    # — a BEFORE UPDATE trigger handles that case (see migration adding
    # set_updated_at_now()). Keep both: the trigger is the source of truth,
    # `onupdate` is the ergonomic ORM path.
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()"), onupdate=text("now()")
    )
