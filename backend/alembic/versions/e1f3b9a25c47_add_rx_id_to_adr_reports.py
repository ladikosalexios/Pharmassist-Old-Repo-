"""add_rx_id_to_adr_reports

Revision ID: e1f3b9a25c47
Revises: c4e2a7f1d903
Create Date: 2026-06-08 00:00:00.000000

Adds the originating prescription barcode (ΗΔΥΚΑ rx_id) to adr_reports so a
report created against a specific prescription round-trips the same in live
mode as it already does in mock mode. Nullable — walk-in / spontaneous
reports have no prescription.

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'e1f3b9a25c47'
down_revision: Union[str, Sequence[str], None] = 'c4e2a7f1d903'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "adr_reports",
        sa.Column("rx_id", sa.String(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("adr_reports", "rx_id")
