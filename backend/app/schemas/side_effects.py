"""Side-effect (ADR) report schemas (POST /side-effects)."""

from typing import Literal

from pydantic import BaseModel

from ..constants import AdrCausality

# patientId is optional: the Reports form captures a free-text patient name,
# not an AMKA, so walk-in reports legitimately arrive without an id (the
# adr_reports.patient_amka column is nullable to match).

Causality = Literal[
    AdrCausality.CERTAIN,
    AdrCausality.PROBABLE,
    AdrCausality.POSSIBLE,
    AdrCausality.UNLIKELY,
]


class CreateSideEffectBody(BaseModel):
    patientId: str | None = None
    patientName: str
    rxId: str | None = None
    drugName: str
    severity: Literal["MILD", "MODERATE", "SEVERE"]
    symptom: str
    onset: str
    causality: Causality | None = None


class SideEffectReportOut(BaseModel):
    """The camelCase report shape both list and create return (see get_adr_report_dict)."""

    id: str
    patientId: str | None = None
    patientName: str | None = None
    patientPhone: str | None = None
    rxId: str | None = None
    drugName: str | None = None
    severity: str | None = None
    status: str
    reportedAt: str
    symptom: str
    onset: str | None = None
    causality: Causality | None = None
