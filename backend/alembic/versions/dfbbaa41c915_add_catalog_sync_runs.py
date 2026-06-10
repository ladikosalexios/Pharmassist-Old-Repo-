"""add catalog_sync_runs

Revision ID: dfbbaa41c915
Revises: a7c31e09d4f2
Create Date: 2026-06-10 16:22:39.652713

FT-4 (docs/b2b-core/FINISH-TIER1.md): one row per drug-catalogue masterdata
sync run — status/counters/error — so sync failures surface via
GET /admin/sync-drug-catalog/status instead of vanishing into a container-log
print. Standard BEFORE UPDATE updated_at trigger (set_updated_at_now() exists
since 463cc54e7949). No FKs into seed-truncated tables.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "dfbbaa41c915"
down_revision: str | Sequence[str] | None = "a7c31e09d4f2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "catalog_sync_runs",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("mode", sa.String(length=16), nullable=False),
        sa.Column("since", sa.String(length=10), nullable=True),
        sa.Column(
            "status", sa.String(length=16), server_default=sa.text("'running'"), nullable=False
        ),
        sa.Column(
            "started_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("fetched", sa.Integer(), server_default="0", nullable=False),
        sa.Column("upserted", sa.Integer(), server_default="0", nullable=False),
        sa.Column("skipped", sa.Integer(), server_default="0", nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("triggered_by", sa.String(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_catalog_sync_runs")),
    )
    op.execute(
        "CREATE TRIGGER trg_catalog_sync_runs_set_updated_at "
        "BEFORE UPDATE ON catalog_sync_runs "
        "FOR EACH ROW EXECUTE FUNCTION set_updated_at_now();"
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.execute(
        "DROP TRIGGER IF EXISTS trg_catalog_sync_runs_set_updated_at ON catalog_sync_runs;"
    )
    op.drop_table("catalog_sync_runs")
