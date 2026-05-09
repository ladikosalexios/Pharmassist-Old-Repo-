"""Prescription mutation schemas (PATCH /prescriptions/:id and friends)."""

from typing import Optional

from pydantic import BaseModel


class PrescriptionPatch(BaseModel):
    status: Optional[str] = None
    discrepancy_type: Optional[str] = None
    notes: Optional[str] = None
    notify_physician: Optional[bool] = None


class ApproveResponse(BaseModel):
    success: bool
    rxId: str
    status: str
    completedAt: str
    execId: str  # ΗΔΥΚΑ exec_ref returned by the (fake) dispense POST
    documentationLogId: str  # documentation_logs.id


class PatchResponse(BaseModel):
    success: bool
    rxId: str
    status: str
    discrepancyType: Optional[str] = None
    notes: Optional[str] = None
    notifyPhysician: Optional[bool] = None
    documentationLogId: Optional[str] = None  # only populated when status=FLAGGED
