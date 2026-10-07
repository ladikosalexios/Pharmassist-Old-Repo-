"""Private Yellow Card drafts, artifacts, signatures and transactional mail outbox."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg

revision = "f6c2d8e14b30"
down_revision = "e5b1c9d47a20"
branch_labels = depends_on = None


def owned():
    return [
        sa.Column("id", pg.UUID(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("pharmacist_id", pg.UUID(), sa.ForeignKey("pharmacists.id"), nullable=False),
        sa.Column("pharmacy_id", pg.UUID(), sa.ForeignKey("pharmacies.id"), nullable=False),
    ]


def times():
    return [
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    ]


def upgrade():
    op.create_table(
        "yellow_signatures",
        *owned(),
        *times(),
        sa.Column("image", sa.LargeBinary(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
    )
    op.create_table(
        "yellow_reports",
        *owned(),
        *times(),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("payload", sa.LargeBinary(), nullable=False),
        sa.CheckConstraint("revision > 0", name=op.f("ck_yellow_reports_positive_revision")),
    )
    op.create_table(
        "yellow_previews",
        *owned(),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("report_id", pg.UUID(), sa.ForeignKey("yellow_reports.id"), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("signature_id", pg.UUID(), sa.ForeignKey("yellow_signatures.id"), nullable=False),
        sa.Column("payload", sa.LargeBinary(), nullable=False),
        sa.Column("pdf", sa.LargeBinary(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("template_version", sa.String(), nullable=False),
        sa.Column("envelope", sa.LargeBinary(), nullable=False),
        sa.Column("envelope_sha256", sa.String(64), nullable=False),
    )
    op.create_table(
        "yellow_submissions",
        *owned(),
        *times(),
        sa.Column("preview_id", pg.UUID(), sa.ForeignKey("yellow_previews.id"), nullable=False),
        sa.Column("idempotency_key", sa.String(100), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("transport", sa.String(), nullable=False),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("approval_version", sa.String(), nullable=False),
        sa.Column("attempted_at", sa.DateTime(timezone=True)),
        sa.Column("failure_code", sa.String()),
        sa.UniqueConstraint("preview_id"),
        sa.UniqueConstraint("pharmacist_id", "pharmacy_id", "idempotency_key"),
        sa.CheckConstraint(
            "status IN ('QUEUED','SENDING','CAPTURED_LOCAL','FAILED','UNKNOWN','CANCELLED')",
            name=op.f("ck_yellow_submissions_status"),
        ),
    )
    op.create_table(
        "yellow_events",
        sa.Column("id", pg.UUID(), primary_key=True),
        sa.Column(
            "submission_id", pg.UUID(), sa.ForeignKey("yellow_submissions.id"), nullable=False
        ),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    for table in ["yellow_signatures", "yellow_reports", "yellow_submissions"]:
        op.execute(
            f"CREATE TRIGGER trg_{table}_updated_at BEFORE UPDATE ON {table} FOR EACH ROW EXECUTE FUNCTION set_updated_at_now()"
        )


def downgrade():
    for table in [
        "yellow_events",
        "yellow_submissions",
        "yellow_previews",
        "yellow_reports",
        "yellow_signatures",
    ]:
        op.drop_table(table)
