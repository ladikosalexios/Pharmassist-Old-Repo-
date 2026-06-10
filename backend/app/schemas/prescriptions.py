"""Prescription mutation schemas (PATCH /prescriptions/:id and friends)."""

from pydantic import BaseModel


class PrescriptionPatch(BaseModel):
    status: str | None = None
    discrepancy_type: str | None = None
    notes: str | None = None
    notify_physician: bool | None = None


class DispensePack(BaseModel):
    """A verified + supplied HMVS pack the pharmacist scanned at dispense.

    GS1 fields straight off the 2D DataMatrix (AI 01/21/10/17). These populate
    the eDispensation supply line's HMVS-QR block (dispense_mode=1) so ΗΔΥΚΑ
    gets the real ΕΟΦ/QR serial instead of the synthetic placeholder.
    """

    gtin: str  # GS1 (01)
    serial: str  # GS1 (21)
    batch: str  # GS1 (10)
    expiry: str  # GS1 (17) — YYMMDD


class ApproveRequest(BaseModel):
    """Optional body for POST /prescriptions/{rx}/approve.

    ``packs`` are the scanned+supplied HMVS packs (one per dispensed unit). When
    present the eDispensation echoes real HMVS-QR data; when empty/omitted the
    flow falls back to the synthetic ΕΟΦ-strip line (mock + pre-scan parity).
    """

    packs: list[DispensePack] = []


class ApproveResponse(BaseModel):
    success: bool
    rxId: str
    status: str
    completedAt: str
    execId: str  # ΗΔΥΚΑ exec_ref — kept for back-compat with older callers
    # `executionNo` is the field the frontend (DispenseWizard) reads; same
    # value as `execId`. Both populated to make the wire contract explicit.
    executionNo: str
    # documentationLogId is None on an idempotent retry — the original counsel
    # log row remains the legal record; we don't write a second one when the
    # cached receipt is replayed (see approve_prescription idempotency branch).
    documentationLogId: str | None = None
    dispenseLogId: str  # dispense_logs.id — the upstream-receipt audit row
    idempotent: bool = False  # True when this response came from the cache


class PatchResponse(BaseModel):
    success: bool
    rxId: str
    status: str
    discrepancyType: str | None = None
    notes: str | None = None
    notifyPhysician: bool | None = None
    documentationLogId: str | None = None  # only populated when status=FLAGGED
