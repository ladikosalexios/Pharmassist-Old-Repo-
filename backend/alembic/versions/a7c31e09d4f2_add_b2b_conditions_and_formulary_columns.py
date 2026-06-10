"""add_b2b_conditions_and_formulary_columns

Revision ID: a7c31e09d4f2
Revises: f2a8c4d91b03
Create Date: 2026-06-10 11:00:00.000000

Two B2B Core pieces (docs/b2b-core/TICKETS.md BC-12b + BC-13):

1. b2b_patient_conditions — the per-location twin of patient_conditions.
   Unique key INCLUDES location_id (partial, WHERE active) so tenants never
   collide with — or learn about — another tenant's record for the same AMKA.
   The B2C table and its global unique index are untouched.

2. drug_catalog formulary columns — nullable additions sourced from Pharmapi
   masterdata (field mapping verified by live probe, see
   docs/b2b-core/masterdata-probe.md): form, strength (raw + parsed), prices,
   ΕΟΠΥΥ positive-list coverage (tri-state), participation %, substance code,
   package size. Plus the atc_code index formulary class-queries need.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "a7c31e09d4f2"
down_revision: Union[str, Sequence[str], None] = "f2a8c4d91b03"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "b2b_patient_conditions",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("location_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("amka", sa.String(), nullable=False),
        sa.Column("condition_code", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("severity", sa.String(), nullable=True),
        sa.Column("notes", sa.String(), nullable=True),
        sa.Column("created_via_api_key_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["location_id"],
            ["locations.id"],
            name=op.f("fk_b2b_patient_conditions_location_id_locations"),
        ),
        sa.ForeignKeyConstraint(
            ["created_via_api_key_id"],
            ["api_keys.id"],
            name=op.f("fk_b2b_patient_conditions_created_via_api_key_id_api_keys"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_b2b_patient_conditions")),
    )
    op.create_index(
        "ix_b2b_patient_conditions_location_amka_active",
        "b2b_patient_conditions",
        ["location_id", "amka"],
        postgresql_where=sa.text("active = true"),
    )
    op.create_index(
        "uq_b2b_patient_conditions_location_amka_condition_active",
        "b2b_patient_conditions",
        ["location_id", "amka", "condition_code"],
        unique=True,
        postgresql_where=sa.text("active = true"),
    )
    op.execute(
        "CREATE TRIGGER trg_b2b_patient_conditions_set_updated_at "
        "BEFORE UPDATE ON b2b_patient_conditions "
        "FOR EACH ROW EXECUTE FUNCTION set_updated_at_now();"
    )

    op.add_column("drug_catalog", sa.Column("form_code", sa.String(), nullable=True))
    op.add_column("drug_catalog", sa.Column("strength_raw", sa.String(), nullable=True))
    op.add_column("drug_catalog", sa.Column("strength_value", sa.Numeric(), nullable=True))
    op.add_column("drug_catalog", sa.Column("strength_unit", sa.String(), nullable=True))
    op.add_column("drug_catalog", sa.Column("retail_price", sa.Numeric(), nullable=True))
    op.add_column("drug_catalog", sa.Column("reference_price", sa.Numeric(), nullable=True))
    op.add_column("drug_catalog", sa.Column("eopyy_coverage", sa.Boolean(), nullable=True))
    op.add_column("drug_catalog", sa.Column("participation_pct", sa.Numeric(), nullable=True))
    op.add_column("drug_catalog", sa.Column("substance_code", sa.String(), nullable=True))
    op.add_column("drug_catalog", sa.Column("package_size", sa.String(), nullable=True))
    op.create_index(op.f("ix_drug_catalog_atc_code"), "drug_catalog", ["atc_code"])


def downgrade() -> None:
    op.drop_index(op.f("ix_drug_catalog_atc_code"), table_name="drug_catalog")
    for column in (
        "package_size",
        "substance_code",
        "participation_pct",
        "eopyy_coverage",
        "reference_price",
        "retail_price",
        "strength_unit",
        "strength_value",
        "strength_raw",
        "form_code",
    ):
        op.drop_column("drug_catalog", column)
    op.execute(
        "DROP TRIGGER IF EXISTS trg_b2b_patient_conditions_set_updated_at "
        "ON b2b_patient_conditions;"
    )
    op.drop_index(
        "uq_b2b_patient_conditions_location_amka_condition_active",
        table_name="b2b_patient_conditions",
    )
    op.drop_index(
        "ix_b2b_patient_conditions_location_amka_active",
        table_name="b2b_patient_conditions",
    )
    op.drop_table("b2b_patient_conditions")
