"""Side-effect (ADR) report mutation schemas (POST /side-effects)."""

from typing import Literal

from pydantic import BaseModel

# patientId is optional: the Reports form captures a free-text patient name,
# not an AMKA, so walk-in reports legitimately arrive without an id (the
# adr_reports.patient_amka column is nullable to match).


class CreateSideEffectBody(BaseModel):
    patientId: str | None = None
    patientName: str
    rxId: str | None = None
    drugName: str
    severity: Literal["MILD", "MODERATE", "SEVERE"]
    symptom: str
    onset: str
    causality: Literal["Certain", "Probable", "Possible", "Unlikely"] | None = None
