"""Prescription mutation schemas (PATCH /prescriptions/:id and friends)."""

from typing import Optional

from pydantic import BaseModel


class PrescriptionPatch(BaseModel):
    status: Optional[str] = None
    discrepancy_type: Optional[str] = None
    notes: Optional[str] = None
    notify_physician: Optional[bool] = None
