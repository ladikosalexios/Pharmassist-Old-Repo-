"""Documentation & Legal Log schemas."""

from pydantic import BaseModel


class DocumentationCreate(BaseModel):
    rxId: str
    instructions: str
    language: str
    method: str
    setting: str | None = "Private"
