from pydantic import BaseModel

from .base import AppSchema


class RxHistoryItem(AppSchema):
    rx_id: str | None = None
    date: str | None = None
    drug_name: str | None = None
    prescriber_name: str | None = None
    status: str
    quantity_prescribed: str | None = None
    quantity_outstanding: str | None = None
    eu_dispensed: bool = False


class RxHistoryPage(AppSchema):
    items: list[RxHistoryItem]
    page: int
    total_pages: int
    last_page: bool
    total_entries: int
    blocked: bool


class ParticipationException(AppSchema):
    """One patient co-pay exemption record (ΗΔΥΚΑ `patientPartExceptions`).

    ΗΔΥΚΑ carries no numeric patient-level co-pay % anywhere in the read tier
    (verified by the FT-2 probe — docs/b2b-core/insurances-probe.md); what it
    does carry is this exemption list: the reason a patient deviates from the
    drug-level participation % and the window it applies in. The effective
    rate is computed per prescription line at dispense time, upstream.
    """

    id: int | None = None
    reason: str | None = None  # upstream `exceptionReason` (Greek free text)
    effective_from: str | None = None
    effective_to: str | None = None


class PatientPayload(BaseModel):
    id: str
    amka: str | None = None
    ekaa: str | None = None
    first_name: str
    last_name: str
    date_of_birth: str
    age: int
    sex: str
    phone: str
    nationality: str | None = None
    address: str | None = None
    email: str | None = None
    conditions: list | None = None
    allergies: list | None = None
    intolerances: list | None = None
    safety_flags: dict | None = None
    # Co-pay exemptions from /common/getpatient (None when upstream omits the
    # key — mock parity keeps the same tri-state: absent vs empty vs populated).
    participation_exceptions: list[ParticipationException] | None = None
