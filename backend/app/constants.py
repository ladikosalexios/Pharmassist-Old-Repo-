"""Domain-wide string constants.

Status values, severity levels, action types, delivery methods, and similar
literals that show up in more than one router/service live here so a rename
propagates everywhere.
"""


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
    STATUS_CHANGED = "STATUS_CHANGED"


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
