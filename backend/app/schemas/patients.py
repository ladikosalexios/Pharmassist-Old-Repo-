from pydantic import BaseModel


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
    conditions: list | None = None
    allergies: list | None = None
    intolerances: list | None = None
    safety_flags: dict | None = None
