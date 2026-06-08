"""patient_conditions: partial unique active (amka, condition_code)

Revision ID: 4a91c2b5e3df
Revises: 8c0445fedd65
Create Date: 2026-06-08 14:00:00.000000

Stops a double-click on the patient-profile "Save condition" modal from
inserting two active rows for the same (amka, condition_code).

Pre-existing active duplicates are deactivated (kept for audit, dropped from
the GET list and the safety engine) before creating the index, otherwise the
index build would fail on the conflict. The most recently created row per pair
is retained.

The unique key spans amka + condition_code only (no pharmacy_id): a single
patient should have one canonical active record of a given condition across
the system, mirroring the safety engine's de-duplication by condition_code.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "4a91c2b5e3df"
down_revision: Union[str, Sequence[str], None] = "8c0445fedd65"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

INDEX_NAME = "uq_patient_conditions_amka_condition_active"


def upgrade() -> None:
    op.execute(
        """
        WITH ranked AS (
            SELECT
                id,
                ROW_NUMBER() OVER (
                    PARTITION BY amka, condition_code
                    ORDER BY created_at DESC, id DESC
                ) AS rn
            FROM patient_conditions
            WHERE active = TRUE
        )
        UPDATE patient_conditions
           SET active = FALSE
         WHERE id IN (SELECT id FROM ranked WHERE rn > 1);
        """
    )
    op.create_index(
        INDEX_NAME,
        "patient_conditions",
        ["amka", "condition_code"],
        unique=True,
        postgresql_where=sa.text("active = true"),
    )


def downgrade() -> None:
    op.drop_index(INDEX_NAME, table_name="patient_conditions")
