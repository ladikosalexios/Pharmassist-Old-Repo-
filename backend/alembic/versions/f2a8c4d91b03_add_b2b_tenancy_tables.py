"""add_b2b_tenancy_tables

Revision ID: f2a8c4d91b03
Revises: c7da2b900aef
Create Date: 2026-06-10 09:30:00.000000

B2B Core (Tier-1) tenancy foundation — see docs/b2b-core/TICKETS.md BC-1.

Three tables: customers (tenant root), locations (the billable unit, carrying
the location's own ΗΔΥΚΑ unit id + AES-256-GCM-encrypted Pharmapi credentials),
api_keys (sha256 hash at rest, plaintext shown once by scripts/b2b_admin.py).

Deliberately NO foreign keys into any table touched by scripts/seed.py's
TRUNCATE ... CASCADE (pharmacies, pharmacists, ...) so a routine reseed can
never wipe tenant data.

Each table gets the standard BEFORE UPDATE updated_at trigger (the
set_updated_at_now() function already exists from 463cc54e7949).
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "f2a8c4d91b03"
down_revision: Union[str, Sequence[str], None] = "c7da2b900aef"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

B2B_TABLES = ("customers", "locations", "api_keys")


def upgrade() -> None:
    op.create_table(
        "customers",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("contact_email", sa.String(), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_customers")),
    )
    op.create_table(
        "locations",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("customer_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("address", sa.String(), nullable=True),
        sa.Column("pharmapi_unit_id", sa.Integer(), nullable=False),
        sa.Column("pharmapi_username", sa.String(), nullable=True),
        sa.Column("pharmapi_password", sa.String(), nullable=True),
        sa.Column("is_eopyy", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["customer_id"], ["customers.id"], name=op.f("fk_locations_customer_id_customers")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_locations")),
    )
    op.create_table(
        "api_keys",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("location_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("key_hash", sa.String(length=64), nullable=False),
        sa.Column("label", sa.String(), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["location_id"], ["locations.id"], name=op.f("fk_api_keys_location_id_locations")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_api_keys")),
        sa.UniqueConstraint("key_hash", name=op.f("uq_api_keys_key_hash")),
    )
    for table in B2B_TABLES:
        op.execute(
            f"CREATE TRIGGER trg_{table}_set_updated_at "
            f"BEFORE UPDATE ON {table} "
            f"FOR EACH ROW EXECUTE FUNCTION set_updated_at_now();"
        )


def downgrade() -> None:
    for table in B2B_TABLES:
        op.execute(f"DROP TRIGGER IF EXISTS trg_{table}_set_updated_at ON {table};")
    op.drop_table("api_keys")
    op.drop_table("locations")
    op.drop_table("customers")
