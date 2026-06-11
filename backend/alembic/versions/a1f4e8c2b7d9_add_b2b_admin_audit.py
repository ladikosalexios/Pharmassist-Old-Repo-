"""add b2b_admin_audit

Revision ID: a1f4e8c2b7d9
Revises: c9e1a7b4f203
Create Date: 2026-06-11 11:00:00.000000

Durable audit trail for the b2b_admin CLI's privileged operator mutations
(create-customer, set-tier, create-location, mint-key, rotate-key, revoke-key)
— raised as review finding #2 on PR #142 (T2-1 tier gate), where set-tier moved
billing entitlement with only a stdout print.

Append-only, BigInteger SERIAL id like audit_log. Deliberately FK-free: target_id
is plain text so a row survives its target's removal and never rides a reseed's
TRUNCATE ... CASCADE — same posture as the tenancy tables. Standard BEFORE UPDATE
updated_at trigger (set_updated_at_now() exists since 463cc54e7949), even though
rows are never updated in normal operation — consistency with every other table.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a1f4e8c2b7d9"
down_revision: str | Sequence[str] | None = "c9e1a7b4f203"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "b2b_admin_audit",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("actor", sa.String(), nullable=False),
        sa.Column("action", sa.String(), nullable=False),
        sa.Column("target_type", sa.String(), nullable=True),
        sa.Column("target_id", sa.String(), nullable=True),
        sa.Column("details", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "occurred_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_b2b_admin_audit")),
    )
    op.create_index(
        "ix_b2b_admin_audit_target", "b2b_admin_audit", ["target_type", "target_id"]
    )
    op.execute(
        "CREATE TRIGGER trg_b2b_admin_audit_set_updated_at "
        "BEFORE UPDATE ON b2b_admin_audit "
        "FOR EACH ROW EXECUTE FUNCTION set_updated_at_now();"
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DROP TRIGGER IF EXISTS trg_b2b_admin_audit_set_updated_at ON b2b_admin_audit;")
    op.drop_index("ix_b2b_admin_audit_target", table_name="b2b_admin_audit")
    op.drop_table("b2b_admin_audit")
