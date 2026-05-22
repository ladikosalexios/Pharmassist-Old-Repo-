from pydantic import BaseModel


class SyncDrugCatalogRequest(BaseModel):
    since: str | None = None  # YYYY-MM-DD; omit for full sync


class SyncDrugCatalogResponse(BaseModel):
    fetched: int
    upserted: int
    skipped: int
