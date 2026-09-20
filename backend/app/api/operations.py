import re
import uuid
from datetime import datetime, timezone
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.config import settings
from app.db.session import get_db
from app.models import CRMWriteAttempt, CRMWriteJob, Lead, RecoveryIncident
from app.schemas.operations import (
    CurrentJobCounts,
    IncidentFilter,
    JobState,
    LookupKind,
    OperationsAttempt,
    OperationsIncident,
    OperationsIncidentPage,
    OperationsJobDetail,
    OperationsJobListItem,
    OperationsJobPage,
    OperationsLeadReference,
    OperationsSummary,
)

router = APIRouter(prefix="/api/operations", tags=["operations"])

JOB_STATES = (
    "pending",
    "processing",
    "retry_wait",
    "completed",
    "blocked",
    "needs_review",
)
MAX_PAGE = 10_000
EXECUTION_ID_RE = re.compile(r"^[0-9]+$")
SENSITIVE_RECORDED_VALUE_RE = re.compile(
    r"(?:authorization\s*:|bearer\s+|(?:api|adapter|crm)[ _-]?key|credential|secret|token|"
    r"password|payload(?:_json)?|provider[ _-]?(?:body|response))",
    re.IGNORECASE,
)
REDACTED_RECORDED_VALUE = "Redacted unsafe recorded value"


def _observed_at() -> datetime:
    return datetime.now(timezone.utc)


def _execution_url(reference: str | None) -> str | None:
    """Only construct editor links from the configured local n8n editor origin."""
    if not reference or not EXECUTION_ID_RE.fullmatch(reference):
        return None
    base = urlsplit(settings.n8n_editor_base_url)
    try:
        port = base.port
    except ValueError:
        return None
    if (
        base.scheme != "http"
        or base.hostname not in {"localhost", "127.0.0.1"}
        or port != 5678
        or base.path not in {"", "/"}
        or base.username
        or base.password
        or base.query
        or base.fragment
    ):
        return None
    return f"{settings.n8n_editor_base_url.rstrip('/')}/execution/{reference}"


def _next_eligible_at(job: CRMWriteJob) -> datetime | None:
    return job.due_at if job.state == "retry_wait" else None


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _safe_recorded_text(value: str | None) -> str | None:
    """Keep useful bounded operational text without serializing credential-like values."""
    if value is None:
        return None
    if (
        not value
        or len(value) > 300
        or any(character in value for character in "\r\n\x00")
        or value.lstrip().startswith(("{", "["))
        or SENSITIVE_RECORDED_VALUE_RE.search(value)
    ):
        return REDACTED_RECORDED_VALUE
    return value


def _incident_projection(incident: RecoveryIncident, *, linked: bool) -> OperationsIncident:
    return OperationsIncident(
        id=incident.id,
        job_id=incident.job_id,
        correlation_id=incident.correlation_id,
        workflow_reference=_safe_recorded_text(incident.workflow_reference),
        execution_reference=_safe_recorded_text(incident.execution_reference),
        execution_url=_execution_url(incident.execution_reference),
        failed_node=_safe_recorded_text(incident.failed_node),
        error_class=_safe_recorded_text(incident.error_class) or REDACTED_RECORDED_VALUE,
        state=incident.state,
        resolved_at=incident.resolved_at,
        created_at=incident.created_at,
        linked=linked,
    )


@router.get("/summary", response_model=OperationsSummary)
def operations_summary(db: Session = Depends(get_db)) -> OperationsSummary:
    counts = {state: 0 for state in JOB_STATES}
    for state, count in db.execute(
        select(CRMWriteJob.state, func.count()).group_by(CRMWriteJob.state)
    ):
        if state in counts:
            counts[state] = count
    return OperationsSummary(
        observed_at=_observed_at(),
        job_counts=CurrentJobCounts(**counts),
        open_incident_count=db.scalar(
            select(func.count())
            .select_from(RecoveryIncident)
            .where(RecoveryIncident.state == "open")
        )
        or 0,
    )


@router.get("/jobs", response_model=OperationsJobPage)
def operations_jobs(
    state: JobState | None = None,
    lookup_kind: LookupKind | None = None,
    lookup_id: uuid.UUID | None = None,
    page: int = Query(default=1, ge=1, le=MAX_PAGE),
    page_size: int = Query(default=25, ge=1, le=100),
    db: Session = Depends(get_db),
) -> OperationsJobPage:
    if (lookup_kind is None) != (lookup_id is None):
        raise HTTPException(
            status_code=422, detail="lookup_kind and lookup_id must be supplied together"
        )
    statement = select(CRMWriteJob)
    if state:
        statement = statement.where(CRMWriteJob.state == state)
    if lookup_kind == "job_id":
        statement = statement.where(CRMWriteJob.id == lookup_id)
    elif lookup_kind == "submission_id":
        statement = statement.where(CRMWriteJob.submission_id == lookup_id)
    elif lookup_kind == "correlation_id":
        statement = statement.where(CRMWriteJob.correlation_id == lookup_id)
    total = db.scalar(select(func.count()).select_from(statement.subquery())) or 0
    jobs = db.scalars(
        statement.order_by(CRMWriteJob.created_at.desc(), CRMWriteJob.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return OperationsJobPage(
        observed_at=_observed_at(),
        total=total,
        page=page,
        page_size=page_size,
        items=[
            OperationsJobListItem(
                id=job.id,
                submission_id=job.submission_id,
                correlation_id=job.correlation_id,
                operation_kind=job.operation_kind,
                state=job.state,
                created_at=job.created_at,
                attempt_count=job.attempt_count,
                next_eligible_at=_next_eligible_at(job),
                last_error_class=_safe_recorded_text(job.last_error_class),
            )
            for job in jobs
        ],
    )


@router.get("/jobs/{job_id}", response_model=OperationsJobDetail)
def operations_job_detail(job_id: uuid.UUID, db: Session = Depends(get_db)) -> OperationsJobDetail:
    job = db.get(CRMWriteJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Operations job not found.")
    lead = db.get(Lead, job.completed_lead_id) if job.completed_lead_id else None
    attempts = list(
        db.scalars(
            select(CRMWriteAttempt)
            .where(CRMWriteAttempt.job_id == job.id)
            .order_by(CRMWriteAttempt.attempt_number.asc())
        )
    )
    incidents = list(
        db.scalars(
            select(RecoveryIncident)
            .where(
                or_(
                    RecoveryIncident.job_id == job.id,
                    RecoveryIncident.correlation_id == job.correlation_id,
                )
            )
            .order_by(RecoveryIncident.created_at.desc(), RecoveryIncident.id.desc())
        )
    )
    observed_at = _observed_at()
    lease_expired = bool(
        job.state == "processing"
        and job.lease_expires_at
        and _as_utc(job.lease_expires_at) <= observed_at
    )
    return OperationsJobDetail(
        observed_at=observed_at,
        id=job.id,
        submission_id=job.submission_id,
        correlation_id=job.correlation_id,
        operation_kind=job.operation_kind,
        state=job.state,
        created_at=job.created_at,
        updated_at=job.updated_at,
        attempt_count=job.attempt_count,
        reconciliation_failure_count=job.reconciliation_failure_count,
        next_eligible_at=_next_eligible_at(job),
        last_error_class=_safe_recorded_text(job.last_error_class),
        last_error_message=_safe_recorded_text(job.last_error_message),
        completed_lead=(
            OperationsLeadReference(
                id=lead.id, full_name=lead.full_name, pipeline_stage=lead.pipeline_stage
            )
            if lead
            else None
        ),
        lease_expired_at_observation=lease_expired,
        source_execution_reference=_safe_recorded_text(job.source_execution_reference),
        source_execution_url=_execution_url(job.source_execution_reference),
        attempts=[
            OperationsAttempt(
                attempt_number=attempt.attempt_number,
                started_at=attempt.started_at,
                finished_at=attempt.finished_at,
                outcome=attempt.outcome,
                status_code=attempt.status_code,
                error_class=_safe_recorded_text(attempt.error_class),
                retry_after_raw=_safe_recorded_text(attempt.retry_after_raw),
                retry_after_seconds=attempt.retry_after_seconds,
                execution_reference=_safe_recorded_text(attempt.execution_reference),
                execution_url=_execution_url(attempt.execution_reference),
            )
            for attempt in attempts
        ],
        incidents=[_incident_projection(incident, linked=True) for incident in incidents],
    )


@router.get("/incidents", response_model=OperationsIncidentPage)
def operations_incidents(
    state: IncidentFilter = "all",
    page: int = Query(default=1, ge=1, le=MAX_PAGE),
    page_size: int = Query(default=25, ge=1, le=100),
    db: Session = Depends(get_db),
) -> OperationsIncidentPage:
    statement = select(RecoveryIncident)
    if state != "all":
        statement = statement.where(RecoveryIncident.state == state)
    total = db.scalar(select(func.count()).select_from(statement.subquery())) or 0
    incidents = list(
        db.scalars(
            statement.order_by(RecoveryIncident.created_at.desc(), RecoveryIncident.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    )
    job_ids = {incident.job_id for incident in incidents if incident.job_id}
    correlation_ids = {incident.correlation_id for incident in incidents if incident.correlation_id}
    linked_job_ids = set(
        db.scalars(select(CRMWriteJob.id).where(CRMWriteJob.id.in_(job_ids)))
    ) if job_ids else set()
    linked_correlation_ids = set(
        db.scalars(
            select(CRMWriteJob.correlation_id).where(CRMWriteJob.correlation_id.in_(correlation_ids))
        )
    ) if correlation_ids else set()
    return OperationsIncidentPage(
        observed_at=_observed_at(),
        total=total,
        page=page,
        page_size=page_size,
        items=[
            _incident_projection(
                incident,
                linked=(
                    incident.job_id in linked_job_ids
                    or incident.correlation_id in linked_correlation_ids
                ),
            )
            for incident in incidents
        ],
    )
