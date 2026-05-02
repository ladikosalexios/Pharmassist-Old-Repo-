"""Pharmacist ↔ prescriber message thread schemas."""

from pydantic import BaseModel


class MessagePayload(BaseModel):
    to: str
    rxId: str
    body: str
