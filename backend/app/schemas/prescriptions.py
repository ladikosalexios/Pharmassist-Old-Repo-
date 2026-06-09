"""Prescription mutation schemas (PATCH /prescriptions/:id and friends)."""

from pydantic import BaseModel


class PrescriptionPatch(BaseModel):
    status: str | None = None
    discrepancy_type: str | None = None
    notes: str | None = None
    notify_physician: bool | None = None


class ApproveResponse(BaseModel):
    success: bool
    rxId: str
    status: str
    completedAt: str
    execId: str  # ΗΔΥΚΑ exec_ref — kept for back-compat with older callers
    # `executionNo` is the field the frontend (DispenseWizard) reads; same
    # value as `execId`. Both populated to make the wire contract explicit.
    executionNo: str
    documentationLogId: str  # documentation_logs.id
    dispenseLogId: str  # dispense_logs.id — the upstream-receipt audit row


class PatchResponse(BaseModel):
    success: bool
    rxId: str
    status: str
    discrepancyType: str | None = None
    notes: str | None = None
    notifyPhysician: bool | None = None
    documentationLogId: str | None = None  # only populated when status=FLAGGED
