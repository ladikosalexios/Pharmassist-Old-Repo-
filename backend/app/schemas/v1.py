"""B2B /v1 response/request contracts (camelCase on the wire via AppSchema).

These models are the partner-facing contract — field names here are frozen by
the Postman collection + contract tests. Deliberate naming honesty: the drug
identifier is exposed as ``barcode`` (what drug_catalog.gns_code actually
stores) and the substance field as ``activeSubstance`` (the INN description),
so the /v1 contract never inherits the misleading internal column names.
"""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import field_validator, model_validator

from ..constants import AlertStatus
from .base import AppSchema
from .patients import ParticipationException
from .safety import SafetyAlertPayload


class V1Patient(AppSchema):
    id: str
    amka: str | None = None
    ekaa: str | None = None
    first_name: str
    last_name: str
    date_of_birth: str
    age: int
    sex: str
    phone: str = ""
    nationality: str | None = None
    address: str | None = None
    # Patient co-pay exemption records (D-9): ΗΔΥΚΑ supplies no numeric
    # patient-level co-pay % — these exemptions + the drug-level
    # participationPct on /v1/drugs are what the read tier actually carries
    # (probe evidence: docs/b2b-core/insurances-probe.md). None = upstream
    # did not supply the key; [] = supplied and empty (no exemptions).
    participation_exceptions: list[ParticipationException] | None = None


class V1Intolerance(AppSchema):
    active_substance: str | None = None
    intolerance: str | None = None
    remarks: str | None = None


class V1PrescriptionItem(AppSchema):
    rx_id: str | None = None
    patient_name: str | None = None
    patient_amka: str | None = None
    medication: str | None = None
    medicine_barcode: str | None = None
    physician: str | None = None
    date: str | None = None
    expiry_date: str | None = None
    status: str
    social_insurance: str | None = None
    pharm_api_status: str | None = None
    repeat_no: int | None = None
    total_repeats: int | None = None


class V1PrescriptionPage(AppSchema):
    items: list[V1PrescriptionItem]
    count: int


class V1Drug(AppSchema):
    barcode: str
    atc_code: str | None = None
    name: str
    active_substance: str | None = None
    substance_code: str | None = None
    form_code: str | None = None
    strength: str | None = None
    retail_price: Decimal | None = None
    reference_price: Decimal | None = None
    eopyy_coverage: bool | None = None
    participation_pct: Decimal | None = None
    package_size: str | None = None
    active: bool


class V1DrugPage(AppSchema):
    items: list[V1Drug]
    total: int
    page: int
    size: int
    last_page: bool


class V1Alternative(AppSchema):
    drug: V1Drug
    tier: Literal["generic_equivalent", "therapeutic_class"]
    dose_note: str


class V1AlternativesResponse(AppSchema):
    source: V1Drug | None = None
    source_atc: str
    coverage_filter: Literal["strict", "lenient"]
    alternatives: list[V1Alternative]
    data_caveats: list[str]


class V1MedicationInput(AppSchema):
    barcode: str | None = None
    atc: str | None = None

    @model_validator(mode="after")
    def _exactly_one(self):
        if bool(self.barcode) == bool(self.atc):
            raise ValueError("provide exactly one of barcode or atc")
        return self


class V1SafetyPatient(AppSchema):
    amka: str | None = None

    @field_validator("amka")
    @classmethod
    def _amka_shape(cls, v: str | None) -> str | None:
        if v is None:
            return v
        v = v.strip()
        if not (v.isdigit() and len(v) == 11):
            raise ValueError("AMKA must be exactly 11 digits")
        return v


class V1SafetyCheckRequest(AppSchema):
    patient: V1SafetyPatient | None = None
    medications: list[V1MedicationInput]
    comedications: list[V1MedicationInput] = []

    @field_validator("medications")
    @classmethod
    def _non_empty(cls, v: list) -> list:
        if not v:
            raise ValueError("at least one medication is required")
        return v


class V1MedicationResult(AppSchema):
    input: V1MedicationInput
    atc_code: str | None = None
    # True when a barcode could not be resolved against the drug catalogue —
    # surfaced explicitly because "no alert" must never be mistaken for "safe".
    unknown_drug: bool = False
    checks: list[SafetyAlertPayload]


class V1SafetyCheckResponse(AppSchema):
    status: AlertStatus
    results: list[V1MedicationResult]
    conditions_considered: int
    # Transparency about what this endpoint does NOT screen — same principle as
    # unknownDrug and the formulary dataCaveats: a clean status must never be
    # mistaken for "everything was checked".
    data_caveats: list[str]


class V1SafetyExplainRequest(AppSchema):
    # The rule codes a /v1/safety/check result produced (e.g. WARFARIN_ASPIRIN_BLEED).
    # Optional condition codes describe the patient's clinical profile (e.g. PREGNANCY)
    # so the rationale is condition-aware — never any patient identity.
    rule_codes: list[str]
    condition_codes: list[str] = []

    @field_validator("rule_codes")
    @classmethod
    def _non_empty(cls, v: list[str]) -> list[str]:
        if not v:
            raise ValueError("at least one ruleCode is required")
        return v


class V1SafetyExplanation(AppSchema):
    rule_code: str
    # Always "el": the rationale/mechanism/alternatives are generated in Greek.
    language: str
    rationale: str
    mechanism: str
    # Greek label mapped from the rule's severity (Υψηλός/Μέτριος/Χαμηλός) — anchored
    # to the deterministic engine, not generated, so it can never be hallucinated.
    risk_level: str
    alternatives: list[str]
    # True when this rule+condition-profile was served from the AI response cache
    # (zero LLM calls) rather than freshly generated.
    cached: bool


class V1SafetyExplainResponse(AppSchema):
    explanations: list[V1SafetyExplanation]


class V1Condition(AppSchema):
    id: uuid.UUID
    amka: str
    condition_code: str
    name: str
    severity: str | None = None
    notes: str | None = None
    active: bool
    created_at: datetime
    updated_at: datetime
