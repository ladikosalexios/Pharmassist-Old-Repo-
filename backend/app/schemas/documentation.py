"""Documentation & Legal Log schemas."""

from pydantic import BaseModel

from ..constants import Setting


class DocumentationCreate(BaseModel):
    rxId: str
    instructions: str
    language: str
    method: str
    setting: str | None = Setting.PRIVATE
