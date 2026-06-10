import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict


class SyncDrugCatalogRequest(BaseModel):
    since: date | None = None  # omit for full sync; Pydantic enforces YYYY-MM-DD


class SyncDrugCatalogResponse(BaseModel):
    message: str


class CatalogSyncRunPayload(BaseModel):
    """One catalog_sync_runs row (FT-4) — admin status surface."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    mode: str
    since: str | None = None
    status: str
    started_at: datetime
    finished_at: datetime | None = None
    fetched: int
    upserted: int
    skipped: int
    error: str | None = None
    triggered_by: str | None = None


class CatalogCoveragePayload(BaseModel):
    """Formulary data-quality counts over active rows (FT-3 launch gate)."""

    total_active: int
    with_coverage: int
    with_price: int
    with_participation: int
    with_form: int
    with_substance: int


class SyncDrugCatalogStatusResponse(BaseModel):
    runs: list[CatalogSyncRunPayload]
    coverage: CatalogCoveragePayload
