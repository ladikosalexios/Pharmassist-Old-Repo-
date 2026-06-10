from .base import AppSchema


class InsuranceMemberType(AppSchema):
    id: int
    name: str


class InsuranceFund(AppSchema):
    id: int
    name: str
    short_name: str | None = None
    # Fund-is-ΕΟΠΥΥ flag from the upstream `socialInsurance.eopyy` field —
    # the "ΕΟΠΥΥ coverage" signal the pricing doc promises on insurance
    # details (surfaced by the FT-2 probe; previously dropped by this schema).
    eopyy: bool | None = None


class PatientInsurancePayload(AppSchema):
    id: int
    member_type: InsuranceMemberType | None = None
    ama: str | None = None
    update_date: str | None = None
    directly_insured_amka: str | None = None
    from_emaes: bool | None = None
    last_active: bool | None = None
    is_retired: bool | None = None
    social_insurance: InsuranceFund | None = None
