"""widen documentation_logs action_type for contact_prescriber

Revision ID: 1c615352b3b8
Revises: 31fd353d3ccc
Create Date: 2026-07-21 01:10:05.099974

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '1c615352b3b8'
down_revision: Union[str, Sequence[str], None] = '31fd353d3ccc'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Allow action_type=CONTACT_PRESCRIBER (pharmacist recorded contacting the
    prescriber) alongside the existing APPROVE / FLAG."""
    op.drop_constraint("action_type_valid", "documentation_logs", type_="check")
    op.create_check_constraint(
        "action_type_valid",
        "documentation_logs",
        "action_type IN ('APPROVE', 'FLAG', 'CONTACT_PRESCRIBER')",
    )


def downgrade() -> None:
    op.drop_constraint("action_type_valid", "documentation_logs", type_="check")
    op.create_check_constraint(
        "action_type_valid",
        "documentation_logs",
        "action_type IN ('APPROVE', 'FLAG')",
    )
