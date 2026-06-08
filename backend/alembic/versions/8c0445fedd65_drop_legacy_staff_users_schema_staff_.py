"""drop legacy staff_users schema (staff->pharmacist migration cleanup)

Revision ID: 8c0445fedd65
Revises: 30e3fdb66cbc
Create Date: 2026-06-08 16:28:35.038062

Reconciles pre-existing schema drift: the app migrated its identity model from
``staff_users`` to ``pharmacists`` long ago, but the DB was never cleaned up.
Nothing in app/ or scripts/ references ``staff_users``, ``audit_log.staff_id`` or
``invitations.invited_by_staff_id`` (the current models define neither), so every
``alembic revision --autogenerate`` kept proposing to drop them. This migration
makes that drop deliberate and reviewed, so autogenerate produces an empty diff.

Data safety (verified before writing): both stale FK columns are 100% NULL, and
``invitations.invited_by`` has no NULL rows, so the NOT NULL tightening is safe.
The 4 leftover ``staff_users`` rows are unused dev/admin remnants — no live FK
points at them.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "8c0445fedd65"
down_revision: Union[str, Sequence[str], None] = "30e3fdb66cbc"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Drop the legacy staff_users table and its dangling FK columns."""
    # 1. audit_log.staff_id (superseded by pharmacist_id/pharmacy_id).
    op.drop_constraint(
        op.f("fk_audit_log_staff_id_staff_users"), "audit_log", type_="foreignkey"
    )
    op.drop_column("audit_log", "staff_id")

    # 2. invitations.invited_by_staff_id (superseded by invited_by -> pharmacists).
    op.drop_constraint(
        op.f("fk_invitations_invited_by_staff_id_staff_users"),
        "invitations",
        type_="foreignkey",
    )
    op.drop_column("invitations", "invited_by_staff_id")

    # 3. Tighten invited_by to match the model (Mapped[uuid.UUID], nullable=False).
    op.alter_column("invitations", "invited_by", existing_type=sa.UUID(), nullable=False)

    # 4. The now-unreferenced legacy table.
    op.drop_table("staff_users")


def downgrade() -> None:
    """Recreate the legacy staff_users table and its FK columns."""
    op.create_table(
        "staff_users",
        sa.Column(
            "id",
            sa.UUID(),
            server_default=sa.text("gen_random_uuid()"),
            autoincrement=False,
            nullable=False,
        ),
        sa.Column("email", sa.VARCHAR(), autoincrement=False, nullable=False),
        sa.Column("password_hash", sa.VARCHAR(), autoincrement=False, nullable=False),
        sa.Column("full_name", sa.VARCHAR(), autoincrement=False, nullable=False),
        sa.Column(
            "role",
            sa.VARCHAR(),
            server_default=sa.text("'admin'::character varying"),
            autoincrement=False,
            nullable=False,
        ),
        sa.Column(
            "active",
            sa.BOOLEAN(),
            server_default=sa.text("true"),
            autoincrement=False,
            nullable=False,
        ),
        sa.Column(
            "last_login_at", postgresql.TIMESTAMP(timezone=True), autoincrement=False, nullable=True
        ),
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            autoincrement=False,
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            autoincrement=False,
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_staff_users")),
        sa.UniqueConstraint("email", name=op.f("uq_staff_users_email")),
    )
    op.alter_column("invitations", "invited_by", existing_type=sa.UUID(), nullable=True)
    op.add_column(
        "invitations",
        sa.Column("invited_by_staff_id", sa.UUID(), autoincrement=False, nullable=True),
    )
    op.create_foreign_key(
        op.f("fk_invitations_invited_by_staff_id_staff_users"),
        "invitations",
        "staff_users",
        ["invited_by_staff_id"],
        ["id"],
    )
    op.add_column(
        "audit_log", sa.Column("staff_id", sa.UUID(), autoincrement=False, nullable=True)
    )
    op.create_foreign_key(
        op.f("fk_audit_log_staff_id_staff_users"),
        "audit_log",
        "staff_users",
        ["staff_id"],
        ["id"],
    )
