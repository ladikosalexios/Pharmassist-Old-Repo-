"""tier0: clinical_only tier + locations without ΗΔΥΚΑ credentials

Revision ID: e5b1c9d47a20
Revises: 1c615352b3b8
Create Date: 2026-09-26 09:00:00.000000

docs/b2b-core/TIER0-RETRIEVAL-FREE.md — T0-3 + T0-4, one migration.

* T0-3 / D-20: widen ck_customers_tier to admit the new base tier
  `clinical_only` (below `core`). The column default stays 'core' — existing
  tenants and the CLI default are untouched; clinical_only is always explicit.
* T0-4: locations.pharmapi_unit_id becomes nullable so a location can be
  provisioned with no ΗΔΥΚΑ identity at all (credentials were already
  nullable). A new check constraint keeps that state intentional rather than
  half-finished: username/password are both-or-neither, and set credentials
  require a unit id. A blank string counts as unset (NULLIF), matching the
  truthiness test get_api_context uses. Every row minted by scripts/b2b_admin.py
  so far carries all three, so the constraint validates cleanly against
  existing data; a row it rejects was already 500ing on every /v1 call under
  the old guard.

Downgrade refuses (rather than silently re-tiering or deleting tenants) while
any clinical_only customer or credential-less location exists. That check
needs a live connection, so offline (`--sql`) downgrade skips it and only
renders the DDL.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import context, op

# revision identifiers, used by Alembic.
revision: str = "e5b1c9d47a20"
down_revision: str | Sequence[str] | None = "1c615352b3b8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.drop_constraint(op.f("ck_customers_tier"), "customers", type_="check")
    op.create_check_constraint(
        op.f("ck_customers_tier"),
        "customers",
        "tier IN ('clinical_only', 'core', 'clinical', 'platform')",
    )

    op.alter_column("locations", "pharmapi_unit_id", existing_type=sa.Integer(), nullable=True)
    op.create_check_constraint(
        op.f("ck_locations_pharmapi_credentials"),
        "locations",
        "(NULLIF(pharmapi_username, '') IS NULL) = (NULLIF(pharmapi_password, '') IS NULL) "
        "AND (NULLIF(pharmapi_username, '') IS NULL OR pharmapi_unit_id IS NOT NULL)",
    )


def downgrade() -> None:
    """Downgrade schema."""
    # Offline (--sql) mode has no connection to count rows with (get_bind()
    # returns None there); whoever applies the rendered SQL owns that check.
    if not context.is_offline_mode():
        bind = op.get_bind()
        blockers = {
            "clinical_only customers": (
                "SELECT count(*) FROM customers WHERE tier = 'clinical_only'"
            ),
            "locations without a ΗΔΥΚΑ unit id": (
                "SELECT count(*) FROM locations WHERE pharmapi_unit_id IS NULL"
            ),
        }
        for label, sql in blockers.items():
            count = bind.execute(sa.text(sql)).scalar_one()
            if count:
                raise RuntimeError(
                    f"cannot downgrade e5b1c9d47a20: {count} {label} exist — re-tier or "
                    "re-provision them first (the pre-Tier-0 schema cannot represent them)"
                )

    op.drop_constraint(op.f("ck_locations_pharmapi_credentials"), "locations", type_="check")
    op.alter_column("locations", "pharmapi_unit_id", existing_type=sa.Integer(), nullable=False)

    op.drop_constraint(op.f("ck_customers_tier"), "customers", type_="check")
    op.create_check_constraint(
        op.f("ck_customers_tier"),
        "customers",
        "tier IN ('core', 'clinical', 'platform')",
    )
