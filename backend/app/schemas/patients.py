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
    conditions: list
    allergies: list
    intolerances: list
    safety_flags: dict
