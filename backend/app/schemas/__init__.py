"""Pydantic schemas for the PharmAssist API.

Each domain has its own module — keep API contracts grouped by feature so a
reader looking at "what does PATCH /prescriptions/:id accept?" opens one file
instead of grepping main.py.
"""

from .auth import PharmacistMe, SessionStatus, TokenResponse
from .documentation import DocumentationCreate
from .instructions import InstructionsGenerate, InstructionsSend
from .messages import MessagePayload
from .notifications import PhysicianNotification
from .prescriptions import PrescriptionPatch

__all__ = [
    "DocumentationCreate",
    "InstructionsGenerate",
    "InstructionsSend",
    "MessagePayload",
    "PharmacistMe",
    "PhysicianNotification",
    "PrescriptionPatch",
    "SessionStatus",
    "TokenResponse",
]
