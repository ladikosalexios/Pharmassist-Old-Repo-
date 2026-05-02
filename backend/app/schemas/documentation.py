"""Documentation & Legal Log schemas."""

from typing import Optional

from pydantic import BaseModel


class DocumentationCreate(BaseModel):
    rxId: str
    instructions: str
    language: str
    method: str
    setting: Optional[str] = "Private"
