"""Documentation & Legal Log schemas."""

from typing import Literal

from pydantic import BaseModel

from ..constants import Setting


class DocumentationCreate(BaseModel):
    rxId: str
    instructions: str
    language: str
    method: str
    setting: Literal["Private", "Hospital"] | None = Setting.PRIVATE
