from datetime import date

from pydantic import BaseModel


class SyncDrugCatalogRequest(BaseModel):
    since: date | None = None  # omit for full sync; Pydantic enforces YYYY-MM-DD


class SyncDrugCatalogResponse(BaseModel):
    fetched: int
    upserted: int
    skipped: int
