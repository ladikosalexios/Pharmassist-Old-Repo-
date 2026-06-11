"""add ai_response_cache

Revision ID: b7d3f5a18c40
Revises: a1f4e8c2b7d9
Create Date: 2026-06-11 12:00:00.000000

Response cache for the Tier-2 LLM seam (T2-2). A deterministic content hash of
(prompt_kind + the whitelisted prompt input) maps to the model's structured
output, so a repeated AI request (e.g. the same safety rule under the same
condition profile — PharmAssist_Pricing.md:92) is served without a second
upstream call. A DB table, not an in-process dict, so it survives a restart and
the single-worker constraint (D-8).

cache_key is UNIQUE — lookups are a single indexed hit and a concurrent
double-miss can't insert two rows for one request. Standard BEFORE UPDATE
updated_at trigger (set_updated_at_now() exists since 463cc54e7949) for
consistency, even though rows are append-on-miss and not updated in normal
operation. No PII is stored: see the model docstring.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b7d3f5a18c40"
down_revision: str | Sequence[str] | None = "a1f4e8c2b7d9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "ai_response_cache",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("cache_key", sa.String(), nullable=False),
        sa.Column("prompt_kind", sa.String(), nullable=False),
        sa.Column("model", sa.String(), nullable=True),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ai_response_cache")),
        sa.UniqueConstraint("cache_key", name=op.f("uq_ai_response_cache_cache_key")),
    )
    op.execute(
        "CREATE TRIGGER trg_ai_response_cache_set_updated_at "
        "BEFORE UPDATE ON ai_response_cache "
        "FOR EACH ROW EXECUTE FUNCTION set_updated_at_now();"
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DROP TRIGGER IF EXISTS trg_ai_response_cache_set_updated_at ON ai_response_cache;")
    op.drop_table("ai_response_cache")
