"""add_causality_to_adr_reports

Revision ID: c4e2a7f1d903
Revises: b81649811cdb
Create Date: 2026-06-07 00:00:00.000000

Adds a pharmacovigilance causality assessment column to adr_reports
(WHO-UMC style: Certain | Probable | Possible | Unlikely). Nullable —
legacy reports and walk-in reports where causality is undetermined.

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c4e2a7f1d903'
down_revision: Union[str, Sequence[str], None] = 'b81649811cdb'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "adr_reports",
        sa.Column("causality", sa.String(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("adr_reports", "causality")
