"""hmvs: store Retry-After hint on hmvs_operations

Revision ID: 0e474b463e5d
Revises: 30e3fdb66cbc
Create Date: 2026-06-08 18:00:00.000000

Adds the ``retry_after_seconds`` column captured from a 429 Retry-After header,
so the replay loop never re-hits the registry before the throttle window
expires (an ITE compliance requirement). Nullable: only 429 responses set it.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0e474b463e5d"
down_revision: Union[str, Sequence[str], None] = "30e3fdb66cbc"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "hmvs_operations",
        sa.Column("retry_after_seconds", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("hmvs_operations", "retry_after_seconds")
