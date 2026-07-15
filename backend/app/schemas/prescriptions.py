"""Prescription mutation schemas (PATCH /prescriptions/:id)."""

from pydantic import BaseModel


class PrescriptionPatch(BaseModel):
    status: str | None = None
    discrepancy_type: str | None = None
    notes: str | None = None
    notify_physician: bool | None = None


class PatchResponse(BaseModel):
    success: bool
    rxId: str
    status: str
    discrepancyType: str | None = None
    notes: str | None = None
    notifyPhysician: bool | None = None
    documentationLogId: str | None = None  # only populated when status=FLAGGED
