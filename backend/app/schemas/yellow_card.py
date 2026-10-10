"""Only information destined for the form; no patient or prescription identifiers."""

from datetime import date
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Reaction(Strict):
    description: str = Field(default="", max_length=12000)
    onset: date | None = None
    onset_unknown: bool = False
    end: date | None = None
    outcome: Literal[1, 2, 3, 4, 5, 6] = 6

    @model_validator(mode="after")
    def dates(self):
        if self.onset and self.onset_unknown:
            raise ValueError("Η έναρξη δεν μπορεί να είναι γνωστή και άγνωστη μαζί")
        if self.onset and self.end and self.end < self.onset:
            raise ValueError("Η λήξη προηγείται της έναρξης")
        return self


class Medicine(Strict):
    name: str = Field(default="", max_length=1000)
    lot: str = Field(default="", max_length=200)
    route: str = Field(default="", max_length=200)
    dose: str = Field(default="", max_length=1000)
    start: date | None = None
    end: date | None = None
    indication: str = Field(default="", max_length=2000)

    @model_validator(mode="after")
    def dates(self):
        if self.start and self.end and self.end < self.start:
            raise ValueError("Η λήξη προηγείται της έναρξης")
        return self


class ReportData(Strict):
    initials: str = Field(default="", max_length=20)
    age: str = Field(default="", max_length=30)
    weight: str = Field(default="", max_length=20)
    height: str = Field(default="", max_length=20)
    sex: Literal["", "male", "female"] = ""
    reactions: list[Reaction] = Field(default_factory=lambda: [Reaction()], max_length=30)
    serious: bool | None = None
    seriousness: list[
        Literal["death", "life_threatening", "hospitalisation", "disability", "congenital", "other"]
    ] = Field(default_factory=list, max_length=6)
    death_date: date | None = None
    death_cause: str = Field(default="", max_length=2000)
    suspected: list[Medicine] = Field(default_factory=lambda: [Medicine()], max_length=30)
    concomitant: list[Medicine] = Field(default_factory=list, max_length=30)
    observations: str = Field(default="", max_length=20000)
    reporter_name: str = Field(default="", max_length=300)
    reporter_address: str = Field(default="", max_length=500)
    reporter_institution: str = Field(default="", max_length=300)
    reporter_phone: str = Field(default="", max_length=100)
    reporter_email: str = Field(default="", max_length=300)
    # The form's "Ιδιότητα Αναφέροντος" boxes. Doctors add a specialty; "other" says what.
    reporter_type: Literal[
        "hospital_doctor", "hospital_pharmacist", "private_doctor", "private_pharmacist", "other"
    ] = "private_pharmacist"
    reporter_specialty: str = Field(default="", max_length=200)
    reporter_other: str = Field(default="", max_length=200)
    report_date: date | None = None

    def missing(self) -> list[str]:
        fields = {
            "Αρχικά ασθενούς": self.initials,
            "Όνομα αναφέροντος": self.reporter_name,
            "Τηλέφωνο αναφέροντος": self.reporter_phone,
            "Ημερομηνία αναφοράς": self.report_date,
        }
        result = [k for k, v in fields.items() if not v]
        if not self.reactions or any(
            not r.description or not (r.onset or r.onset_unknown) for r in self.reactions
        ):
            result.append("Αντίδραση και έναρξη (ή ρητά άγνωστη)")
        if not self.suspected or any(not m.name for m in self.suspected):
            result.append("Ύποπτο φάρμακο")
        if any(not m.name for m in self.concomitant):
            result.append("Ονομασία συγχορηγούμενου φαρμάκου")
        if (
            self.serious is None
            or (self.serious and not self.seriousness)
            or (not self.serious and self.seriousness)
        ):
            result.append("Σοβαρότητα και συνεπή κριτήρια")
        doctor = self.reporter_type in ("hospital_doctor", "private_doctor")
        other = self.reporter_type == "other"
        if doctor != bool(self.reporter_specialty) or other != bool(self.reporter_other):
            result.append("Ιδιότητα αναφέροντος και συνεπή στοιχεία")
        return result


class UpdateReport(Strict):
    revision: int = Field(gt=0)
    data: ReportData


class PreviewRequest(Strict):
    synthetic_data: Literal[True]
    revision: int = Field(gt=0)
    signature_id: UUID


class SubmitRequest(Strict):
    preview_id: UUID
    approved: Literal[True]


class ImportAdr(Strict):
    adr_id: UUID
