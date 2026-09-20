import re
import uuid
from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

from app.schemas.lifecycle import AppointmentResponse, FollowUpResponse

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


def clean_optional(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("must be a string or null")
    value = value.strip()
    return value or None


def clean_required(value: object) -> str:
    if not isinstance(value, str) or not (cleaned := value.strip()):
        raise ValueError("must be a non-empty string")
    return cleaned


def validate_phone_shape(value: str) -> str:
    if not PHONE_RE.fullmatch(value) or len(re.sub(r"\D", "", value)) < 7:
        raise ValueError("must contain at least seven digits and only common phone formatting")
    return value


class AIEnrichment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    service_type: ServiceType
    location: str | None = Field(default=None, max_length=160)
    preferred_time: str | None = Field(default=None, max_length=160)
    urgency: Urgency
    summary: str = Field(min_length=1, max_length=600)

    _clean_location = field_validator("location", "preferred_time", mode="before")(clean_optional)
    _clean_summary = field_validator("summary", mode="before")(clean_required)


class ProviderMetadata(BaseModel):
    """Safe, bounded diagnostic fields supplied by the orchestration layer."""

    model_config = ConfigDict(extra="forbid")

    provider: str = Field(min_length=1, max_length=80)
    model_id: str | None = Field(default=None, max_length=160)
    outcome_class: str = Field(
        pattern="^(enriched|invalid_output|provider_error|not_attempted)$"
    )
    status_code: int | None = Field(default=None, ge=100, le=599)
    error_code: str | None = Field(default=None, max_length=100)
    request_id: str | None = Field(default=None, max_length=160)
    execution_reference: str | None = Field(default=None, max_length=160)

    _clean_strings = field_validator(
        "provider", "model_id", "error_code", "request_id", "execution_reference", mode="before"
    )(clean_optional)


class CRMLeadCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    submission_id: uuid.UUID
    correlation_id: uuid.UUID
    received_at: datetime
    full_name: str = Field(max_length=160)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=50)
    original_message: str = Field(max_length=5000)
    normalized_message: str = Field(max_length=5000)
    enrichment: AIEnrichment | None = None
    ai_status: str = Field(pattern="^(enriched|fallback_invalid|fallback_unavailable)$")
    needs_review: bool
    enrichment_diagnostic: str | None = Field(default=None, max_length=300)
    provider_metadata: ProviderMetadata | None = None

    @field_validator("full_name", "normalized_message", mode="before")
    @classmethod
    def required_trimmed(cls, value: object) -> str:
        return clean_required(value)

    @field_validator("original_message", mode="before")
    @classmethod
    def original_message_is_present(cls, value: object) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("must be a non-empty string")
        return value

    @field_validator("email", mode="before")
    @classmethod
    def normalized_email(cls, value: object) -> str | None:
        value = clean_optional(value)
        return value.lower() if value else None

    @field_validator("phone", mode="before")
    @classmethod
    def normalized_phone(cls, value: object) -> str | None:
        value = clean_optional(value)
        return validate_phone_shape(value) if value else None

    @model_validator(mode="after")
    def must_have_contact_method(self):
        if not self.email and not self.phone:
            raise ValueError("at least one contact method is required")
        if self.ai_status == "enriched" and not self.enrichment:
            raise ValueError("enrichment is required when ai_status is enriched")
        if self.ai_status.startswith("fallback_"):
            if not self.needs_review:
                raise ValueError("needs_review must be true for fallback AI status")
            if self.enrichment is not None:
                raise ValueError("enrichment must be null for fallback AI status")
        return self


class LeadResponse(BaseModel):
    id: uuid.UUID
    submission_id: uuid.UUID
    correlation_id: uuid.UUID
    full_name: str
    email: str | None
    phone: str | None
    original_message: str
    normalized_message: str
    service_type: ServiceType | None
    location: str | None
    preferred_time: str | None
    urgency: Urgency | None
    summary: str | None
    provider_metadata: dict | None
    ai_status: str
    needs_review: bool
    pipeline_stage: str
    client_received_at: datetime
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CRMCreateResponse(BaseModel):
    crm_lead_id: uuid.UUID
    submission_id: uuid.UUID
    correlation_id: uuid.UUID
    submission_fingerprint: str = Field(min_length=64, max_length=64)
    pipeline_stage: str
    ai_status: str
    intake_state: str
    follow_up_status: str | None
    follow_up_due_at: datetime | None


class AuditEventResponse(BaseModel):
    id: uuid.UUID
    correlation_id: uuid.UUID
    lead_id: uuid.UUID | None
    event_type: str
    status: str
    metadata_json: dict
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TraceResponse(BaseModel):
    correlation_id: uuid.UUID
    lead: LeadResponse | None
    follow_ups: list[FollowUpResponse]
    appointments: list[AppointmentResponse]
    audit_events: list[AuditEventResponse]
    recovery_jobs: list[dict] = Field(default_factory=list)
    recovery_incidents: list[dict] = Field(default_factory=list)
