import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.lead import CRMLeadCreate


class RecoveryAdmission(BaseModel):
    payload: CRMLeadCreate
    operation_kind: Literal["create_lead"] = "create_lead"
    execution_reference: str | None = Field(default=None, max_length=160)


class RecoveryJobResponse(BaseModel):
    id: uuid.UUID
    submission_id: uuid.UUID
    correlation_id: uuid.UUID
    payload_fingerprint: str
    operation_kind: str
    state: str
    attempt_count: int
    reconciliation_failure_count: int
    due_at: datetime
    lease_token: uuid.UUID | None
    lease_expires_at: datetime | None
    completed_lead_id: uuid.UUID | None
    last_error_class: str | None
    last_error_message: str | None
    payload_json: dict | None = None

    model_config = ConfigDict(from_attributes=True)


class ClaimRequest(BaseModel):
    worker_id: str = Field(min_length=1, max_length=160)
    execution_reference: str | None = Field(default=None, max_length=160)


class AttemptRequest(BaseModel):
    lease_token: uuid.UUID
    execution_reference: str | None = Field(default=None, max_length=160)


class FailureRequest(AttemptRequest):
    attempt_id: uuid.UUID
    status_code: int | None = Field(default=None, ge=100, le=599)
    error_class: str = Field(min_length=1, max_length=80)
    safe_message: str = Field(min_length=1, max_length=300)
    retry_after: str | None = Field(default=None, max_length=160)


class CompleteRequest(AttemptRequest):
    crm_lead_id: uuid.UUID
    attempt_id: uuid.UUID | None = None
    status_code: int = Field(default=200, ge=200, le=299)


class ReconciliationFailureRequest(AttemptRequest):
    status_code: int | None = Field(default=None, ge=100, le=599)
    error_class: str = Field(min_length=1, max_length=80)
    safe_message: str = Field(min_length=1, max_length=300)
    retry_after: str | None = Field(default=None, max_length=160)


class DeferralRequest(AttemptRequest):
    retry_after_seconds: int = Field(ge=1, le=86400)


class QuotaPermissionRequest(AttemptRequest):
    pass


class IncidentCreate(BaseModel):
    event_key: str = Field(min_length=1, max_length=200)
    job_id: uuid.UUID | None = None
    correlation_id: uuid.UUID | None = None
    workflow_reference: str | None = Field(default=None, max_length=160)
    execution_reference: str | None = Field(default=None, max_length=160)
    failed_node: str | None = Field(default=None, max_length=160)
    error_class: str = Field(min_length=1, max_length=80)


class FaultRunCreate(BaseModel):
    run_id: uuid.UUID
    submission_ids: list[uuid.UUID] = Field(min_length=1, max_length=100)
    request_limit: int = Field(default=5, ge=1, le=100)
    window_seconds: int = Field(default=10, ge=1, le=3600)
    hold_delivery: bool = True


class FaultRunUpdate(BaseModel):
    active: bool | None = None
    hold_delivery: bool | None = None
    reset_window: bool = False
