"""Schemas for the company admin portal (/admin/*).

Plain snake_case BaseModels, consistent with schemas/auth.py. `*Out` schemas
set `from_attributes` so routers can `model_validate` ORM rows directly.
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr


# Staff auth
class StaffLoginRequest(BaseModel):
    email: EmailStr
    password: str


class StaffLoginResponse(BaseModel):
    staff_id: str
    name: str
    email: str
    role: str


class StaffMe(BaseModel):
    staff_id: str
    name: str
    email: str
    role: str


# Pharmacy — created as part of onboarding
class PharmacyCreate(BaseModel):
    name: str
    pharmapi_unit_id: int
    address: str | None = None
    street_name: str | None = None
    street_number: str | None = None
    area: str | None = None
    city: str | None = None
    postal_code: str | None = None
    phone: str | None = None
    fax: str | None = None
    email: str | None = None
    geographic_region: str | None = None
    accounting_category: str | None = None
    is_branch: bool = False
    tax_id: str | None = None


class PharmacyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    name: str
    pharmapi_unit_id: int
    address: str | None
    street_name: str | None
    street_number: str | None
    area: str | None
    city: str | None
    postal_code: str | None
    phone: str | None
    fax: str | None
    email: str | None
    geographic_region: str | None
    accounting_category: str | None
    is_branch: bool
    tax_id: str | None
    active: bool
    created_at: datetime


# Onboarding — create a pharmacy and invite its first pharmacist in one step
class OnboardRequest(BaseModel):
    pharmacist_email: EmailStr
    pharmacy: PharmacyCreate


# Pharmacy list — read-only browse
class PharmacyListItem(BaseModel):
    id: uuid.UUID
    name: str
    city: str | None
    pharmacist_count: int
    pending_invite_count: int


class PharmacyListResponse(BaseModel):
    items: list[PharmacyListItem]
    total: int


# Pharmacy detail — operational records for one pharmacy
class PharmacistOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    email: str
    full_name: str
    eof_licence_no: str
    phone: str | None
    role: str
    active: bool
    last_login_at: datetime | None
    created_at: datetime


class InvitationOut(BaseModel):
    id: uuid.UUID
    email: str
    status: str  # pending | accepted | expired
    invite_url: str
    expires_at: datetime
    accepted_at: datetime | None
    created_at: datetime


class AuditLogOut(BaseModel):
    id: int
    action: str
    resource_type: str | None
    resource_id: str | None
    actor_type: str  # staff | pharmacist | system
    actor_name: str | None
    occurred_at: datetime


class PharmacyDetail(BaseModel):
    pharmacy: PharmacyOut
    pharmacists: list[PharmacistOut]
    invitations: list[InvitationOut]
    audit: list[AuditLogOut]
