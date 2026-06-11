"""add tier to customers

Revision ID: c9e1a7b4f203
Revises: dfbbaa41c915
Create Date: 2026-06-11 09:00:00.000000

Tier-2 foundation (docs/b2b-core/TIER2-AUDIT.md T2-1 / D-14: customer-level).

One additive column: customers.tier (core | clinical | platform), the
entitlement that the /v1 require_tier() gate reads through the customer row
get_api_context already loads per request. server_default 'core' so the ALTER
backfills every existing tenant to the base tier (the least-privileged,
fail-safe default); the explicit UPDATE documents that intent and is a no-op
once the default has filled the rows.

No trigger change: customers already carries the standard BEFORE UPDATE
updated_at trigger (from f2a8c4d91b03). No new model module, so no
alembic/env.py / models/__init__ / main.py registration is needed — Customer
is already registered in all three.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c9e1a7b4f203"
down_revision: str | Sequence[str] | None = "dfbbaa41c915"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "customers",
        sa.Column("tier", sa.String(), server_default=sa.text("'core'"), nullable=False),
    )
    # Belt-and-braces backfill: the NOT-NULL add above already fills existing
    # rows with the server_default, so this matches nothing — it just makes the
    # "existing tenants → core" intent explicit and survives a manual replay.
    op.execute("UPDATE customers SET tier = 'core' WHERE tier IS NULL")
    # DB-level guard on the entitlement (billing-relevant) column: a raw SQL
    # write can't smuggle an unknown tier past the CLI's choices= validation.
    # The gate already fails safe (_tier_rank → core for unknowns), so this is
    # integrity-in-depth, not a security fix. Mirrored on the model's
    # __table_args__. Adding a future tier means altering this constraint.
    op.create_check_constraint(
        op.f("ck_customers_tier"),
        "customers",
        "tier IN ('core', 'clinical', 'platform')",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint(op.f("ck_customers_tier"), "customers", type_="check")
    op.drop_column("customers", "tier")
