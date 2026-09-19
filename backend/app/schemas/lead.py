import re
import uuid
from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

PHONE_RE = re.compile(r"^[0-9+().\-\s]{7,50}$")


class ServiceType(StrEnum):
    furnace_service = "furnace_service"
    air_conditioning_service = "air_conditioning_service"
    plumbing_service = "plumbing_service"
    electrical_service = "electrical_service"
    general_home_service = "general_home_service"
    unknown = "unknown"


class Urgency(StrEnum):
    low = "low"
    medium = "medium"
    high = "high"
    urgent = "urgent"


def clean_optional(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value or None


class AIEnrichment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    service_type: ServiceType
    location: str | None = Field(default=None, max_length=160)
    preferred_time: str | None = Field(default=None, max_length=160)
    urgency: Urgency
    summary: str = Field(min_length=1, max_length=600)

    _clean_location = field_validator("location", "preferred_time", mode="before")(clean_optional)
    _clean_summary = field_validator("summary", mode="before")(
        lambda value: value.strip() if isinstance(value, str) else value
    )


class CRMLeadCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    submission_id: uuid.UUID
    correlation_id: uuid.UUID
    received_at: datetime
    full_name: str = Field(max_length=160)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=50)
    original_message: str = Field(max_length=5000)
    enrichment: AIEnrichment | None = None
    ai_status: str = Field(pattern="^(enriched|fallback_invalid|fallback_unavailable)$")
    needs_review: bool
    enrichment_diagnostic: str | None = Field(default=None, max_length=300)

    @field_validator("full_name", "original_message", mode="before")
    @classmethod
    def required_trimmed(cls, value: str) -> str:
        if not isinstance(value, str) or not (cleaned := value.strip()):
            raise ValueError("must be a non-empty string")
        return cleaned

    @field_validator("email", mode="before")
    @classmethod
    def normalized_email(cls, value: str | None) -> str | None:
        value = clean_optional(value)
        return value.lower() if value else None

    @field_validator("phone", mode="before")
    @classmethod
    def normalized_phone(cls, value: str | None) -> str | None:
        value = clean_optional(value)
        if value and not PHONE_RE.fullmatch(value):
            raise ValueError("must be a usable phone number")
        return value

    @model_validator(mode="after")
    def must_have_contact_method(self):
        if not self.email and not self.phone:
            raise ValueError("at least one contact method is required")
        return self


class LeadResponse(BaseModel):
    id: uuid.UUID
    submission_id: uuid.UUID
    correlation_id: uuid.UUID
    full_name: str
    email: str | None
    phone: str | None
    original_message: str
    service_type: ServiceType | None
    location: str | None
    preferred_time: str | None
    urgency: Urgency | None
    summary: str | None
    ai_status: str
    needs_review: bool
    pipeline_stage: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CRMCreateResponse(BaseModel):
    crm_lead_id: uuid.UUID
    submission_id: uuid.UUID
    correlation_id: uuid.UUID
    pipeline_stage: str
    ai_status: str


class AuditEventResponse(BaseModel):
    id: uuid.UUID
    correlation_id: uuid.UUID
    lead_id: uuid.UUID | None
    event_type: str
    status: str
    metadata_json: dict
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
