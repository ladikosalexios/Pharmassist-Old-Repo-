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
    # Resolver-readiness triad (services/substance_resolver) — live intolerance /
    # co-medication checks stay silent unless a drug name resolves to an ATC.
    with_atc: int
    with_inn_name: int


class SyncDrugCatalogStatusResponse(BaseModel):
    runs: list[CatalogSyncRunPayload]
    coverage: CatalogCoveragePayload


class SpcDocumentPayload(BaseModel):
    """One spc_documents row — upload response + admin listing."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    barcode: str | None = None
    atc_code: str
    doc_type: str
    source: str
    source_url: str | None = None
    sha256: str
    language: str
    extraction_method: str
    parse_status: str
    verified: bool
    fetched_at: datetime


class SpcSyncRunPayload(BaseModel):
    """One spc_sync_runs row — admin status surface."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    mode: str
    status: str
    started_at: datetime
    finished_at: datetime | None = None
    examined: int
    fetched_docs: int
    parsed_docs: int
    failed: int
    error: str | None = None
    triggered_by: str | None = None


class SpcCoveragePayload(BaseModel):
    total_docs: int
    parsed_docs: int
    verified_docs: int
    atcs_covered: int
    catalog_atcs: int


class SpcStatusResponse(BaseModel):
    runs: list[SpcSyncRunPayload]
    coverage: SpcCoveragePayload


class SpcFetchRequest(BaseModel):
    """Either a single product fetch (barcode) or a batch over the top-N
    most-scanned uncovered products."""

    barcode: str | None = None
    top: int | None = None
