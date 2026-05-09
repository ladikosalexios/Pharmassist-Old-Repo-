"""add_action_audit_to_documentation_logs

Revision ID: 0b7e15adb339
Revises: 463cc54e7949
Create Date: 2026-05-08 21:34:42.152720

Promotes documentation_logs from a strict dispense record into a unified
audit log for both approve (dispense) and flag (discrepancy) actions.

  - action_type discriminator: APPROVE | FLAG
  - safety_check_snapshot JSONB: the SC list as it stood at action time
  - discrepancy_type / notes: populated only on FLAG rows
  - info_provided / delivery_method now nullable (FLAG rows leave them NULL —
    they're not dispenses, so there's no counselling to record).

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = '0b7e15adb339'
down_revision: Union[str, Sequence[str], None] = '463cc54e7949'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "documentation_logs",
        sa.Column(
            "action_type",
            sa.String(),
            nullable=False,
            server_default="APPROVE",
        ),
    )
    # Drop the server_default after backfill — every new row must set it explicitly.
    op.alter_column("documentation_logs", "action_type", server_default=None)

    op.add_column(
        "documentation_logs",
        sa.Column(
            "safety_check_snapshot",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.alter_column("documentation_logs", "safety_check_snapshot", server_default=None)

    op.add_column(
        "documentation_logs",
        sa.Column("discrepancy_type", sa.String(), nullable=True),
    )
    op.add_column(
        "documentation_logs",
        sa.Column("notes", sa.Text(), nullable=True),
    )

    op.alter_column(
        "documentation_logs",
        "info_provided",
        existing_type=sa.String(),
        nullable=True,
    )
    op.alter_column(
        "documentation_logs",
        "delivery_method",
        existing_type=sa.String(),
        nullable=True,
    )

    op.create_check_constraint(
        "action_type_valid",
        "documentation_logs",
        "action_type IN ('APPROVE', 'FLAG')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_documentation_logs_action_type_valid", "documentation_logs", type_="check")

    op.alter_column(
        "documentation_logs",
        "delivery_method",
        existing_type=sa.String(),
        nullable=False,
    )
    op.alter_column(
        "documentation_logs",
        "info_provided",
        existing_type=sa.String(),
        nullable=False,
    )

    op.drop_column("documentation_logs", "notes")
    op.drop_column("documentation_logs", "discrepancy_type")
    op.drop_column("documentation_logs", "safety_check_snapshot")
    op.drop_column("documentation_logs", "action_type")
