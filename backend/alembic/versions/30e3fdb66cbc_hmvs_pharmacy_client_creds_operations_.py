"""hmvs: pharmacy client creds + operations table

Revision ID: 30e3fdb66cbc
Revises: e1f3b9a25c47
Create Date: 2026-06-08 16:17:29.608718

Adds the HMVS (EU-FMD) integration's persistence:
  - two encrypted OAuth2-client-credential columns on pharmacist_pharmacies,
  - the hmvs_operations idempotency-guard / store-and-forward table.

NOTE: autogenerate also surfaced unrelated pre-existing drift (a leftover
``staff_users`` table + its FKs on audit_log/invitations). That drift is NOT
this ticket's concern and would be destructive, so it was intentionally stripped
from this migration — track it separately.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "30e3fdb66cbc"
down_revision: Union[str, Sequence[str], None] = "e1f3b9a25c47"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "hmvs_operations",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("idempotency_key", sa.String(), nullable=False),
        sa.Column("pharmacist_id", sa.UUID(), nullable=False),
        sa.Column("pharmacy_id", sa.UUID(), nullable=False),
        sa.Column("gtin", sa.String(), nullable=False),
        sa.Column("serial", sa.String(), nullable=False),
        sa.Column("batch", sa.String(), nullable=False),
        sa.Column("expiry", sa.String(), nullable=True),
        sa.Column("target_state", sa.String(), nullable=False),
        sa.Column("status", sa.String(), server_default=sa.text("'pending'"), nullable=False),
        sa.Column("operation_code", sa.String(), nullable=True),
        sa.Column("response_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("attempts", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["pharmacist_id"],
            ["pharmacists.id"],
            name=op.f("fk_hmvs_operations_pharmacist_id_pharmacists"),
        ),
        sa.ForeignKeyConstraint(
            ["pharmacy_id"],
            ["pharmacies.id"],
            name=op.f("fk_hmvs_operations_pharmacy_id_pharmacies"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_hmvs_operations")),
        sa.UniqueConstraint("idempotency_key", name=op.f("uq_hmvs_operations_idempotency_key")),
    )
    op.add_column("pharmacist_pharmacies", sa.Column("hmvs_client_id", sa.String(), nullable=True))
    op.add_column(
        "pharmacist_pharmacies", sa.Column("hmvs_client_secret", sa.String(), nullable=True)
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("pharmacist_pharmacies", "hmvs_client_secret")
    op.drop_column("pharmacist_pharmacies", "hmvs_client_id")
    op.drop_table("hmvs_operations")
