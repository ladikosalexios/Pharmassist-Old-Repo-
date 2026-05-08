"""add_updated_at_trigger

Revision ID: 463cc54e7949
Revises: d8516c105cf2
Create Date: 2026-05-08 19:43:12.137463

Adds a BEFORE UPDATE trigger to every table with an updated_at column
so the field is refreshed regardless of who issues the UPDATE — the
ORM's `onupdate=` only covers SQLAlchemy-emitted statements; raw SQL
from psql, migrations, or another service would otherwise leave
updated_at stale.

The trigger function set_updated_at_now() unconditionally sets
NEW.updated_at = now() on every UPDATE. This intentionally overrides
any value the caller supplied (callers should not be setting
updated_at by hand; the column is owned by the database).

"""
from typing import Sequence, Union

from alembic import op


revision: str = '463cc54e7949'
down_revision: Union[str, Sequence[str], None] = 'd8516c105cf2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TABLES_WITH_UPDATED_AT = (
    "pharmacists",
    "pharmacies",
    "pharmacist_pharmacies",
    "patient_conditions",
    "documentation_logs",
    "adr_reports",
    "adr_events",
    "audit_log",
)


def upgrade() -> None:
    op.execute("""
        CREATE OR REPLACE FUNCTION set_updated_at_now()
        RETURNS trigger AS $$
        BEGIN
            NEW.updated_at = now();
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)
    for table in TABLES_WITH_UPDATED_AT:
        op.execute(
            f"CREATE TRIGGER trg_{table}_set_updated_at "
            f"BEFORE UPDATE ON {table} "
            f"FOR EACH ROW EXECUTE FUNCTION set_updated_at_now();"
        )


def downgrade() -> None:
    for table in TABLES_WITH_UPDATED_AT:
        op.execute(f"DROP TRIGGER IF EXISTS trg_{table}_set_updated_at ON {table};")
    op.execute("DROP FUNCTION IF EXISTS set_updated_at_now();")
