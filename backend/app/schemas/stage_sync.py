import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class StageSyncJobResponse(BaseModel):
    id: uuid.UUID
    lead_id: uuid.UUID
    submission_id: uuid.UUID
    correlation_id: uuid.UUID
    desired_stage: str
    desired_rank: int
    desired_version: int
    state: str
    due_at: datetime
    attempt_count: int
    lease_token: uuid.UUID | None
    verified_remote_stage: str | None
    last_error_class: str | None

    model_config = ConfigDict(from_attributes=True)


class StageSyncProcessResponse(BaseModel):
    state: str
    desired_stage: str
    desired_version: int
    verified_remote_stage: str | None
