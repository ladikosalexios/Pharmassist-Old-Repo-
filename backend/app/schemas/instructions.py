"""Patient instructions generation + delivery schemas."""


from pydantic import BaseModel


class InstructionsGenerate(BaseModel):
    rxId: str
    language: str = "en"
    options: dict | None = None


class InstructionsSend(BaseModel):
    patientId: str | None = None
    rxId: str
    content: str
    method: str  # PRINT | DIGITAL | BOTH
