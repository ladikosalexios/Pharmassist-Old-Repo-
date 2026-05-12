"""add_name_to_patient_conditions

Revision ID: 3f8a2b1c9d4e
Revises: 0b7e15adb339
Create Date: 2026-05-11 00:00:00.000000

Adds a display name column to patient_conditions (e.g. "G6PD Deficiency").

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '3f8a2b1c9d4e'
down_revision: Union[str, Sequence[str], None] = '0b7e15adb339'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "patient_conditions",
        sa.Column("name", sa.String(), nullable=False, server_default=""),
    )
    # Drop server_default — every new row must supply a name explicitly.
    op.alter_column("patient_conditions", "name", server_default=None)


def downgrade() -> None:
    op.drop_column("patient_conditions", "name")
