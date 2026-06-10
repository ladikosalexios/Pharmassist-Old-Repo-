# B2B (/v1) patient conditions — the per-LOCATION twin of patient_conditions (D-3).
# A separate table, not a column on the B2C one: the B2C unique index is global by
# (amka, condition_code) and its semantics are load-bearing for the app + tests.
# Here the uniqueness key includes location_id, so tenants can never collide with —
# or infer the existence of — another tenant's record for the same patient.
import uuid

from sqlalchemy import Boolean, ForeignKey, Index, String, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base, TimestampMixin


class B2bPatientCondition(Base, TimestampMixin):
    __tablename__ = "b2b_patient_conditions"
    __table_args__ = (
        Index(
            "ix_b2b_patient_conditions_location_amka_active",
            "location_id",
            "amka",
            postgresql_where=text("active = true"),
        ),
        # One canonical active row per (location, amka, condition_code) —
        # per-location isolation by construction. Soft-deleted rows stay for audit.
        Index(
            "uq_b2b_patient_conditions_location_amka_condition_active",
            "location_id",
            "amka",
            "condition_code",
            unique=True,
            postgresql_where=text("active = true"),
        ),
    )
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    location_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("locations.id"), nullable=False
    )
    amka: Mapped[str] = mapped_column(String, nullable=False)
    condition_code: Mapped[str] = mapped_column(String, nullable=False)  # G6PD | PREGNANCY | ...
    name: Mapped[str] = mapped_column(String, nullable=False)
    severity: Mapped[str | None] = mapped_column(String)  # MILD | MODERATE | SEVERE
    notes: Mapped[str | None] = mapped_column(String)
    # API-key actor instead of B2C's recorded_by pharmacist FK — /v1 callers
    # have no pharmacist row. Nullable so key deletion never blocks on audit rows.
    created_via_api_key_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("api_keys.id"), nullable=True
    )
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
