"""add_setting_to_documentation_logs

Revision ID: b3e9c24f1a7d
Revises: 077777e70a09
Create Date: 2026-05-19 00:00:00.000000

Adds the ``setting`` column (Private | Hospital) to documentation_logs.
Previously the field was accepted by the schema but never persisted.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b3e9c24f1a7d"
down_revision: Union[str, Sequence[str], None] = "077777e70a09"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "documentation_logs",
        sa.Column("setting", sa.String(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("documentation_logs", "setting")
