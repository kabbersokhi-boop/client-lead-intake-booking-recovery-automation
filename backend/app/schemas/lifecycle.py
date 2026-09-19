import uuid
from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class FollowUpStatus(StrEnum):
    pending = "pending"
    sent = "sent"
    cancelled = "cancelled"


class PipelineStage(StrEnum):
    new_lead = "new_lead"
    contacted = "contacted"
    appointment_booked = "appointment_booked"


class AppointmentStatus(StrEnum):
    booked = "booked"


class FollowUpResponse(BaseModel):
    id: uuid.UUID
    lead_id: uuid.UUID
    correlation_id: uuid.UUID
    status: FollowUpStatus
    due_at: datetime
    sent_at: datetime | None
    cancelled_at: datetime | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AppointmentResponse(BaseModel):
    id: uuid.UUID
    booking_request_id: uuid.UUID
    lead_id: uuid.UUID
    correlation_id: uuid.UUID
    appointment_at: datetime
    business_timezone: str
    status: AppointmentStatus
    confirmation_sent_at: datetime | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class BookingCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    booking_request_id: uuid.UUID
    correlation_id: uuid.UUID
    appointment_local: datetime
    business_timezone: str = Field(min_length=1, max_length=80)

    @model_validator(mode="after")
    def local_time_must_not_have_an_offset(self):
        if self.appointment_local.tzinfo is not None:
            raise ValueError("appointment_local must be a business-local time without an offset")
        return self


class BookingCreateResponse(BaseModel):
    appointment_id: uuid.UUID
    booking_request_id: uuid.UUID
    correlation_id: uuid.UUID
    booking_state: str
    appointment_status: AppointmentStatus
    appointment_at: datetime
    business_timezone: str
    pipeline_stage: PipelineStage
    follow_up_status: FollowUpStatus | None
    confirmation_state: str


class EmailDispatchResponse(BaseModel):
    state: str
    pipeline_stage: PipelineStage
    sent_at: datetime | None = None
