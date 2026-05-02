"""Patient instructions generation + delivery schemas."""

from typing import Optional

from pydantic import BaseModel


class InstructionsGenerate(BaseModel):
    rxId: str
    language: str = "en"
    options: Optional[dict] = None


class InstructionsSend(BaseModel):
    patientId: Optional[str] = None
    rxId: str
    content: str
    method: str  # PRINT | DIGITAL | BOTH
