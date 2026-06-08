"""Domain-wide string constants.

Status values, severity levels, action types, delivery methods, and similar
literals that show up in more than one router/service live here so a rename
propagates everywhere.
"""

from enum import StrEnum


class AdrStatus:
    PENDING_REVIEW = "PENDING_REVIEW"
    ESCALATED = "ESCALATED"
    EOF_REPORTED = "EOF_REPORTED"
    CLOSED = "CLOSED"


class AdrSeverity:
    MILD = "MILD"
    MODERATE = "MODERATE"
    SEVERE = "SEVERE"


class AdrEventType:
    REPORT_CREATED = "REPORT_CREATED"
    STATUS_CHANGED = "STATUS_CHANGED"


class AdrCausality:
    CERTAIN = "Certain"
    PROBABLE = "Probable"
    POSSIBLE = "Possible"
    UNLIKELY = "Unlikely"


class ActionType:
    APPROVE = "APPROVE"
    FLAG = "FLAG"


class DeliveryMethod:
    PRINT = "PRINT"
    DIGITAL = "DIGITAL"
    BOTH = "BOTH"


class Setting:
    PRIVATE = "Private"
    HOSPITAL = "Hospital"


class PrescriptionStatus:
    PENDING = "PENDING"
    COMPLETED = "COMPLETED"
    FLAGGED = "FLAGGED"
    UNKNOWN = "UNKNOWN"


class CheckType(StrEnum):
    INTERACTIONS = "interactions"
    DUPLICATE_THERAPY = "duplicate_therapy"
    CONTRAINDICATIONS = "contraindications"
    DOSE_VALIDATION = "dose_validation"
    SPC_ALIGNMENT = "spc_alignment"
    PREGNANCY = "pregnancy"
    G6PD = "G6PD"


class AlertStatus(StrEnum):
    OK = "ok"
    REVIEW = "review"
    BLOCK = "block"
