"""Notification schemas (physician notifications, etc.)."""

from pydantic import BaseModel


class PhysicianNotification(BaseModel):
    rxId: str
    message: str
