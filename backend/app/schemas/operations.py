import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel

JobState = Literal[
    "pending", "processing", "retry_wait", "completed", "blocked", "needs_review"
]
IncidentFilter = Literal["all", "open", "resolved"]
LookupKind = Literal["job_id", "submission_id", "correlation_id"]


class CurrentJobCounts(BaseModel):
    pending: int = 0
    processing: int = 0
    retry_wait: int = 0
    completed: int = 0
    blocked: int = 0
    needs_review: int = 0


class OperationsSummary(BaseModel):
    observed_at: datetime
    job_counts: CurrentJobCounts
    open_incident_count: int


class OperationsJobListItem(BaseModel):
    id: uuid.UUID
    submission_id: uuid.UUID
    correlation_id: uuid.UUID
    operation_kind: str
    state: JobState
    created_at: datetime
    attempt_count: int
    next_eligible_at: datetime | None = None
    last_error_class: str | None = None


class OperationsJobPage(BaseModel):
    observed_at: datetime
    total: int
    page: int
    page_size: int
    items: list[OperationsJobListItem]


class OperationsLeadReference(BaseModel):
    id: uuid.UUID
    full_name: str
    pipeline_stage: str


class OperationsAttempt(BaseModel):
    attempt_number: int
    started_at: datetime
    finished_at: datetime | None
    outcome: str
    status_code: int | None
    error_class: str | None
    retry_after_raw: str | None
    retry_after_seconds: int | None
    execution_reference: str | None
    execution_url: str | None


class OperationsIncident(BaseModel):
    id: uuid.UUID
    job_id: uuid.UUID | None
    correlation_id: uuid.UUID | None
    workflow_reference: str | None
    execution_reference: str | None
    execution_url: str | None
    failed_node: str | None
    error_class: str
    state: str
    resolved_at: datetime | None
    created_at: datetime
    linked: bool


class OperationsJobDetail(BaseModel):
    observed_at: datetime
    id: uuid.UUID
    submission_id: uuid.UUID
    correlation_id: uuid.UUID
    operation_kind: str
    state: JobState
    created_at: datetime
    updated_at: datetime
    attempt_count: int
    reconciliation_failure_count: int
    next_eligible_at: datetime | None = None
    last_error_class: str | None
    last_error_message: str | None
    completed_lead: OperationsLeadReference | None
    lease_expired_at_observation: bool
    source_execution_reference: str | None
    source_execution_url: str | None
    attempts: list[OperationsAttempt]
    incidents: list[OperationsIncident]


class OperationsIncidentPage(BaseModel):
    observed_at: datetime
    total: int
    page: int
    page_size: int
    items: list[OperationsIncident]
