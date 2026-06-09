"""merge hmvs retry-after + patient_conditions unique branches

Revision ID: 5b2169e3d392
Revises: 0e474b463e5d, 4a91c2b5e3df
Create Date: 2026-06-09 01:42:27.607881

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5b2169e3d392'
down_revision: Union[str, Sequence[str], None] = ('0e474b463e5d', '4a91c2b5e3df')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
