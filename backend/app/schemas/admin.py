"""Schemas for the company admin portal (/admin/*).

Plain snake_case BaseModels, consistent with schemas/auth.py. `*Out` schemas
set `from_attributes` so routers can `model_validate` ORM rows directly.
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


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


# Staff accounts
class StaffCreate(BaseModel):
    email: EmailStr
    full_name: str
    password: str = Field(min_length=8)


class StaffOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    email: str
    full_name: str
    role: str
    active: bool
    last_login_at: datetime | None
    created_at: datetime


class StaffListResponse(BaseModel):
    items: list[StaffOut]
    total: int


# Invitations
class InvitationOut(BaseModel):
    id: uuid.UUID
    email: str
    pharmacy_id: uuid.UUID
    pharmacy_name: str
    status: str  # pending | accepted | expired
    invite_url: str
    invited_by_name: str | None
    expires_at: datetime
    accepted_at: datetime | None
    created_at: datetime


class InvitationListResponse(BaseModel):
    items: list[InvitationOut]
    total: int


# Pharmacies
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


class PharmacyUpdate(BaseModel):
    name: str | None = None
    pharmapi_unit_id: int | None = None
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
    is_branch: bool | None = None
    tax_id: str | None = None
    active: bool | None = None


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


class PharmacyListResponse(BaseModel):
    items: list[PharmacyOut]
    total: int


# Pharmacists
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


class PharmacistListResponse(BaseModel):
    items: list[PharmacistOut]
    total: int


# Drug catalog
class DrugCreate(BaseModel):
    gns_code: str
    atc_code: str
    atc_class: str
    name_gr: str
    name_en: str | None = None
    interaction_group: str | None = None


class DrugUpdate(BaseModel):
    gns_code: str | None = None
    atc_code: str | None = None
    atc_class: str | None = None
    name_gr: str | None = None
    name_en: str | None = None
    interaction_group: str | None = None
    active: bool | None = None


class DrugOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    gns_code: str
    atc_code: str
    atc_class: str
    name_gr: str
    name_en: str | None
    interaction_group: str | None
    active: bool


class DrugListResponse(BaseModel):
    items: list[DrugOut]
    total: int


# Safety rules
class SafetyRuleCreate(BaseModel):
    rule_code: str
    check_type: str
    severity: str
    message_en: str
    trigger_atc: str | None = None
    trigger_condition_code: str | None = None
    conflicting_atc: str | None = None
    details_en: str | None = None
    recommended_action_en: str | None = None


class SafetyRuleUpdate(BaseModel):
    rule_code: str | None = None
    check_type: str | None = None
    severity: str | None = None
    message_en: str | None = None
    trigger_atc: str | None = None
    trigger_condition_code: str | None = None
    conflicting_atc: str | None = None
    details_en: str | None = None
    recommended_action_en: str | None = None
    active: bool | None = None


class SafetyRuleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    rule_code: str
    check_type: str
    severity: str
    message_en: str
    trigger_atc: str | None
    trigger_condition_code: str | None
    conflicting_atc: str | None
    details_en: str | None
    recommended_action_en: str | None
    active: bool


class SafetyRuleListResponse(BaseModel):
    items: list[SafetyRuleOut]
    total: int


# Demo seeder
class DemoSeedRequest(BaseModel):
    pharmacy_id: uuid.UUID


class DemoSeedResponse(BaseModel):
    pharmacy_id: uuid.UUID
    patient_conditions: int
    adr_reports: int
    documentation_logs: int


# Audit log
class AuditLogOut(BaseModel):
    id: int
    action: str
    resource_type: str | None
    resource_id: str | None
    actor_type: str  # staff | pharmacist | system
    actor_name: str | None
    pharmacy_name: str | None
    response_code: str | None
    ip_address: str | None
    request_body: dict | None
    occurred_at: datetime


class AuditLogListResponse(BaseModel):
    items: list[AuditLogOut]
    total: int
