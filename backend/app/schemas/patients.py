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
