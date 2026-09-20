import math
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.security import require_crm_adapter_key
from app.db.session import get_db
from app.models import (
    Appointment,
    AuditEvent,
    CRMFaultRun,
    CRMWriteAttempt,
    CRMWriteJob,
    FollowUp,
    Lead,
    RecoveryIncident,
)
from app.providers.crm import DevelopmentCRMProvider
from app.schemas.lead import (
    AuditEventResponse,
    CRMCreateResponse,
    CRMLeadCreate,
    LeadResponse,
    TraceResponse,
)
from app.schemas.lifecycle import (
    BookingConfirmationResponse,
    BookingCreate,
    BookingCreateResponse,
    EmailDispatchResponse,
    FollowUpResponse,
)
from app.schemas.recovery import (
    AttemptRequest,
    ClaimRequest,
    CompleteRequest,
    DeferralRequest,
    FailureRequest,
    FaultRunCreate,
    FaultRunUpdate,
    IncidentCreate,
    QuotaPermissionRequest,
    ReconciliationFailureRequest,
    RecoveryAdmission,
    RecoveryJobResponse,
)
from app.services.crm_service import SubmissionConflictError
from app.services.lifecycle_service import (
    BookingConflictError,
    BookingValidationError,
    EmailDeliveryError,
    LifecycleService,
)
from app.services.recovery_service import (
    RecoveryConflictError,
    RecoveryService,
    StaleLeaseError,
)

router = APIRouter()
provider = DevelopmentCRMProvider()
lifecycle_service = LifecycleService()
recovery_service = RecoveryService()


def _fault_run_for(
    db: Session, submission_id: uuid.UUID, *, lock: bool = True
) -> CRMFaultRun | None:
    candidate = next(
        (
            run
            for run in db.scalars(
                select(CRMFaultRun)
                .where(CRMFaultRun.active.is_(True))
                .order_by(CRMFaultRun.created_at, CRMFaultRun.run_id)
            )
            if str(submission_id) in {str(value) for value in run.submission_ids}
        ),
        None,
    )
    if not candidate or not lock:
        return candidate
    run = db.scalar(
        select(CRMFaultRun)
        .where(CRMFaultRun.run_id == candidate.run_id, CRMFaultRun.active.is_(True))
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if not run or str(submission_id) not in {str(value) for value in run.submission_ids}:
        return None
    return run


def _apply_fault_quota(
    db: Session,
    submission_id: uuid.UUID,
    lease_token: uuid.UUID | None = None,
) -> None:
    job = db.scalar(
        select(CRMWriteJob)
        .where(CRMWriteJob.submission_id == submission_id)
        .with_for_update()
    )
    now = datetime.now(timezone.utc)
    if lease_token and (
        not job
        or job.state != "processing"
        or job.lease_token != lease_token
        or job.lease_expires_at is None
        or RecoveryService._aware(job.lease_expires_at) <= now
    ):
        db.rollback()
        raise HTTPException(status_code=409, detail="Recovery write lease is stale.")
    run = _fault_run_for(db, submission_id)
    if not run:
        db.rollback()
        return
    if run.hold_delivery:
        db.rollback()
        raise HTTPException(
            status_code=503, detail="Synthetic batch delivery is held for preparation."
        )
    if (
        lease_token
        and job
        and job.quota_permit_lease_token == lease_token
        and job.quota_permit_until is not None
        and RecoveryService._aware(job.quota_permit_until) >= now
    ):
        job.quota_permit_until = None
        job.quota_permit_lease_token = None
        db.commit()
        return
    if job:
        job.quota_permit_until = None
        job.quota_permit_lease_token = None
    window_start = run.window_started_at
    if window_start is not None and window_start.tzinfo is None:
        window_start = window_start.replace(tzinfo=timezone.utc)
    if window_start is None or now >= window_start + timedelta(seconds=run.window_seconds):
        run.window_started_at = now
        run.window_count = 0
        window_start = now
    if run.window_count >= run.request_limit:
        retry_after = max(
            1,
            math.ceil((window_start + timedelta(seconds=run.window_seconds) - now).total_seconds()),
        )
        db.commit()
        raise HTTPException(
            status_code=429,
            detail="Controlled local CRM write quota exceeded.",
            headers={"Retry-After": str(retry_after)},
        )
    run.window_count += 1
    db.commit()


def _crm_response(result) -> CRMCreateResponse:
    lead = result.lead
    follow_up = result.follow_up
    return CRMCreateResponse(
        crm_lead_id=lead.id,
        submission_id=lead.submission_id,
        correlation_id=lead.correlation_id,
        submission_fingerprint=lead.submission_fingerprint,
        pipeline_stage=lead.pipeline_stage,
        ai_status=lead.ai_status,
        intake_state="created" if result.created else "replayed",
        follow_up_status=follow_up.status if follow_up else None,
        follow_up_due_at=follow_up.due_at if follow_up else None,
    )


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.post(
    "/api/crm/leads", response_model=CRMCreateResponse, status_code=status.HTTP_201_CREATED
)
def create_crm_lead(
    payload: CRMLeadCreate,
    response: Response,
    x_n8n_execution_reference: str | None = Header(default=None),
    x_recovery_lease_token: uuid.UUID | None = Header(default=None),
    x_crm_diagnostic: str | None = Header(default=None),
    _: None = Depends(require_crm_adapter_key),
    db: Session = Depends(get_db),
) -> CRMCreateResponse:
    diagnostic = None
    if x_crm_diagnostic == "controlled-local-fault":
        try:
            diagnostic = recovery_service.begin_diagnostic_attempt(
                db, payload.submission_id, x_n8n_execution_reference
            )
        except RecoveryConflictError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
    owning_lease = diagnostic[0].lease_token if diagnostic else x_recovery_lease_token
    try:
        _apply_fault_quota(db, payload.submission_id, owning_lease)
        result = provider.create_lead(db, payload)
    except HTTPException as error:
        if diagnostic:
            retry_after = error.headers.get("Retry-After") if error.headers else None
            recovery_service.fail(
                db,
                diagnostic[0].id,
                diagnostic[0].lease_token,
                diagnostic[1].id,
                error.status_code,
                f"http_{error.status_code}",
                "Development CRM write did not complete.",
                retry_after,
                x_n8n_execution_reference,
            )
        raise
    except SubmissionConflictError as error:
        if diagnostic:
            recovery_service.fail(
                db,
                diagnostic[0].id,
                diagnostic[0].lease_token,
                diagnostic[1].id,
                409,
                "submission_conflict",
                "Submission identity conflicts with CRM data.",
                None,
                x_n8n_execution_reference,
            )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Submission identifier is already associated with different lead data.",
        ) from error
    if diagnostic:
        recovery_service.complete(
            db,
            diagnostic[0].id,
            diagnostic[0].lease_token,
            result.lead.id,
            diagnostic[1].id,
            201 if result.created else 200,
        )
    response.status_code = status.HTTP_201_CREATED if result.created else status.HTTP_200_OK
    return _crm_response(result)


@router.post("/api/recovery/intake")
def durable_intake(
    admission: RecoveryAdmission,
    response: Response,
    _: None = Depends(require_crm_adapter_key),
    db: Session = Depends(get_db),
) -> dict:
    try:
        job, _ = recovery_service.admit(db, admission.payload, admission.execution_reference)
    except RecoveryConflictError as error:
        raise HTTPException(
            status_code=409, detail="Recovery identity conflicts with stored data."
        ) from error
    if job.state == "completed" and job.completed_lead_id:
        result = provider.create_lead(db, admission.payload)
        response.status_code = 200
        return _crm_response(result).model_dump(mode="json")
    fault_run = _fault_run_for(db, admission.payload.submission_id, lock=False)
    if fault_run and fault_run.hold_delivery:
        db.rollback()
        response.status_code = 202
        return {
            "state": "received",
            "intake_state": "queued",
            "submission_id": str(job.submission_id),
            "correlation_id": str(job.correlation_id),
            "recovery_job_id": str(job.id),
            "recovery_state": job.state,
        }
    db.rollback()
    try:
        claimed = recovery_service.claim_specific(
            db, job.id, "intake-workflow", admission.execution_reference
        )
        attempt = recovery_service.start_attempt(
            db, job.id, claimed.lease_token, admission.execution_reference
        )
    except RecoveryConflictError:
        db.rollback()
        db.refresh(job)
        response.status_code = 202
        return {
            "state": "received",
            "intake_state": "queued",
            "submission_id": str(job.submission_id),
            "correlation_id": str(job.correlation_id),
            "recovery_job_id": str(job.id),
            "recovery_state": job.state,
        }
    try:
        _apply_fault_quota(db, admission.payload.submission_id, claimed.lease_token)
        result = provider.create_lead(db, admission.payload)
    except HTTPException as error:
        retry_after = error.headers.get("Retry-After") if error.headers else None
        failed = recovery_service.fail(
            db,
            job.id,
            claimed.lease_token,
            attempt.id,
            error.status_code,
            f"http_{error.status_code}",
            "Development CRM write did not complete.",
            retry_after,
            admission.execution_reference,
        )
        response.status_code = 202
        if retry_after:
            response.headers["Retry-After"] = retry_after
        return {
            "state": "received",
            "intake_state": "queued",
            "submission_id": str(job.submission_id),
            "correlation_id": str(job.correlation_id),
            "recovery_job_id": str(job.id),
            "recovery_state": failed.state,
        }
    except SubmissionConflictError as error:
        recovery_service.fail(
            db,
            job.id,
            claimed.lease_token,
            attempt.id,
            409,
            "submission_conflict",
            "Submission identity conflicts with CRM data.",
            None,
            admission.execution_reference,
        )
        raise HTTPException(
            status_code=409, detail="Submission identity conflicts with CRM data."
        ) from error
    recovery_service.complete(
        db,
        job.id,
        claimed.lease_token,
        result.lead.id,
        attempt.id,
        201 if result.created else 200,
    )
    response.status_code = 201 if result.created else 200
    return _crm_response(result).model_dump(mode="json")


@router.get("/api/crm/leads/by-submission/{submission_id}", response_model=CRMCreateResponse)
def lookup_crm_lead(
    submission_id: uuid.UUID,
    _: None = Depends(require_crm_adapter_key),
    db: Session = Depends(get_db),
) -> CRMCreateResponse:
    lead = db.scalar(select(Lead).where(Lead.submission_id == submission_id))
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    follow_up = db.scalar(select(FollowUp).where(FollowUp.lead_id == lead.id))
    return CRMCreateResponse(
        crm_lead_id=lead.id,
        submission_id=lead.submission_id,
        correlation_id=lead.correlation_id,
        submission_fingerprint=lead.submission_fingerprint,
        pipeline_stage=lead.pipeline_stage,
        ai_status=lead.ai_status,
        intake_state="replayed",
        follow_up_status=follow_up.status if follow_up else None,
        follow_up_due_at=follow_up.due_at if follow_up else None,
    )


@router.post("/api/recovery/jobs", response_model=RecoveryJobResponse)
def admit_recovery_job(
    admission: RecoveryAdmission,
    response: Response,
    _: None = Depends(require_crm_adapter_key),
    db: Session = Depends(get_db),
) -> RecoveryJobResponse:
    try:
        job, created = recovery_service.admit(
            db, admission.payload, admission.execution_reference
        )
    except RecoveryConflictError as error:
        raise HTTPException(
            status_code=409, detail="Recovery identity conflicts with stored data."
        ) from error
    response.status_code = 201 if created else 200
    return job


@router.post("/api/recovery/jobs/claim", response_model=RecoveryJobResponse | None)
def claim_recovery_job(
    request: ClaimRequest,
    _: None = Depends(require_crm_adapter_key),
    db: Session = Depends(get_db),
) -> CRMWriteJob | None:
    return recovery_service.claim(db, request.worker_id, request.execution_reference)


@router.post("/api/recovery/jobs/{job_id}/claim", response_model=RecoveryJobResponse)
def claim_specific_recovery_job(
    job_id: uuid.UUID,
    request: ClaimRequest,
    _: None = Depends(require_crm_adapter_key),
    db: Session = Depends(get_db),
) -> CRMWriteJob:
    try:
        return recovery_service.claim_specific(
            db, job_id, request.worker_id, request.execution_reference
        )
    except RecoveryConflictError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.post("/api/recovery/jobs/{job_id}/attempt")
def start_recovery_attempt(
    job_id: uuid.UUID,
    request: AttemptRequest,
    _: None = Depends(require_crm_adapter_key),
    db: Session = Depends(get_db),
) -> dict:
    try:
        attempt = recovery_service.start_attempt(
            db, job_id, request.lease_token, request.execution_reference
        )
    except StaleLeaseError as error:
        raise HTTPException(
            status_code=409, detail="Lease is stale or no longer owns this job."
        ) from error
    except RecoveryConflictError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return {"attempt_id": attempt.id, "attempt_number": attempt.attempt_number}


@router.post("/api/recovery/jobs/{job_id}/quota-permission")
def recovery_quota_permission(
    job_id: uuid.UUID,
    request: QuotaPermissionRequest,
    _: None = Depends(require_crm_adapter_key),
    db: Session = Depends(get_db),
) -> dict:
    try:
        job = recovery_service._leased_job(db, job_id, request.lease_token)
    except StaleLeaseError as error:
        raise HTTPException(
            status_code=409, detail="Lease is stale or no longer owns this job."
        ) from error
    run = _fault_run_for(db, job.submission_id)
    if not run:
        db.rollback()
        return {"granted": True, "retry_after_seconds": 0}
    if run.hold_delivery:
        db.rollback()
        return {"granted": False, "retry_after_seconds": run.window_seconds}
    now = datetime.now(timezone.utc)
    window_start = RecoveryService._aware(run.window_started_at)
    if window_start is None or now >= window_start + timedelta(seconds=run.window_seconds):
        run.window_started_at = now
        run.window_count = 0
        window_start = now
    if run.window_count >= run.request_limit:
        delay = max(
            1,
            math.ceil((window_start + timedelta(seconds=run.window_seconds) - now).total_seconds()),
        )
        db.commit()
        return {"granted": False, "retry_after_seconds": delay}
    run.window_count += 1
    window_end = window_start + timedelta(seconds=run.window_seconds)
    lease_end = RecoveryService._aware(job.lease_expires_at)
    job.quota_permit_until = min(now + timedelta(seconds=5), window_end, lease_end)
    job.quota_permit_lease_token = request.lease_token
    db.commit()
    return {"granted": True, "retry_after_seconds": 0}


@router.post("/api/recovery/jobs/{job_id}/defer", response_model=RecoveryJobResponse)
def defer_recovery_job(
    job_id: uuid.UUID,
    request: DeferralRequest,
    _: None = Depends(require_crm_adapter_key),
    db: Session = Depends(get_db),
) -> CRMWriteJob:
    try:
        return recovery_service.defer(
            db, job_id, request.lease_token, request.retry_after_seconds
        )
    except StaleLeaseError as error:
        raise HTTPException(
            status_code=409, detail="Lease is stale or no longer owns this job."
        ) from error


@router.post("/api/recovery/jobs/{job_id}/complete", response_model=RecoveryJobResponse)
def complete_recovery_job(
    job_id: uuid.UUID,
    request: CompleteRequest,
    _: None = Depends(require_crm_adapter_key),
    db: Session = Depends(get_db),
) -> CRMWriteJob:
    try:
        return recovery_service.complete(
            db,
            job_id,
            request.lease_token,
            request.crm_lead_id,
            request.attempt_id,
            request.status_code,
        )
    except StaleLeaseError as error:
        raise HTTPException(
            status_code=409, detail="Lease is stale or no longer owns this job."
        ) from error
    except RecoveryConflictError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.post("/api/recovery/jobs/{job_id}/fail", response_model=RecoveryJobResponse)
def fail_recovery_job(
    job_id: uuid.UUID,
    request: FailureRequest,
    _: None = Depends(require_crm_adapter_key),
    db: Session = Depends(get_db),
) -> CRMWriteJob:
    try:
        return recovery_service.fail(
            db,
            job_id,
            request.lease_token,
            request.attempt_id,
            request.status_code,
            request.error_class,
            request.safe_message,
            request.retry_after,
            request.execution_reference,
        )
    except StaleLeaseError as error:
        raise HTTPException(
            status_code=409, detail="Lease is stale or no longer owns this job."
        ) from error
    except RecoveryConflictError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.post(
    "/api/recovery/jobs/{job_id}/reconciliation-absent",
    response_model=RecoveryJobResponse,
)
def confirm_recovery_reconciliation_absent(
    job_id: uuid.UUID,
    request: AttemptRequest,
    _: None = Depends(require_crm_adapter_key),
    db: Session = Depends(get_db),
) -> CRMWriteJob:
    try:
        return recovery_service.confirm_absent(db, job_id, request.lease_token)
    except StaleLeaseError as error:
        raise HTTPException(
            status_code=409, detail="Lease is stale or no longer owns this job."
        ) from error


@router.post(
    "/api/recovery/jobs/{job_id}/reconciliation-fail",
    response_model=RecoveryJobResponse,
)
def fail_recovery_reconciliation(
    job_id: uuid.UUID,
    request: ReconciliationFailureRequest,
    _: None = Depends(require_crm_adapter_key),
    db: Session = Depends(get_db),
) -> CRMWriteJob:
    try:
        return recovery_service.fail_reconciliation(
            db,
            job_id,
            request.lease_token,
            request.status_code,
            request.error_class,
            request.safe_message,
            request.retry_after,
        )
    except StaleLeaseError as error:
        raise HTTPException(
            status_code=409, detail="Lease is stale or no longer owns this job."
        ) from error


@router.post("/api/recovery/jobs/{job_id}/requeue", response_model=RecoveryJobResponse)
def requeue_recovery_job(
    job_id: uuid.UUID,
    _: None = Depends(require_crm_adapter_key),
    db: Session = Depends(get_db),
) -> CRMWriteJob:
    try:
        return recovery_service.requeue(db, job_id)
    except RecoveryConflictError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.post("/api/recovery/incidents")
def record_recovery_incident(
    request: IncidentCreate,
    response: Response,
    _: None = Depends(require_crm_adapter_key),
    db: Session = Depends(get_db),
) -> dict:
    incident, created = recovery_service.record_incident(db, **request.model_dump())
    response.status_code = 201 if created else 200
    return {"incident_id": incident.id, "state": incident.state, "created": created}


@router.post("/api/recovery/fault-runs")
def create_fault_run(
    request: FaultRunCreate,
    _: None = Depends(require_crm_adapter_key),
    db: Session = Depends(get_db),
) -> dict:
    if db.get(CRMFaultRun, request.run_id):
        raise HTTPException(status_code=409, detail="Fault run already exists.")
    run = CRMFaultRun(
        run_id=request.run_id,
        submission_ids=[str(value) for value in request.submission_ids],
        request_limit=request.request_limit,
        window_seconds=request.window_seconds,
        hold_delivery=request.hold_delivery,
        active=False,
    )
    db.add(run)
    db.commit()
    return {"run_id": run.run_id, "active": run.active, "hold_delivery": run.hold_delivery}


@router.patch("/api/recovery/fault-runs/{run_id}")
def update_fault_run(
    run_id: uuid.UUID,
    request: FaultRunUpdate,
    _: None = Depends(require_crm_adapter_key),
    db: Session = Depends(get_db),
) -> dict:
    runs = list(
        db.scalars(select(CRMFaultRun).order_by(CRMFaultRun.run_id).with_for_update())
    )
    run = next((candidate for candidate in runs if candidate.run_id == run_id), None)
    if not run:
        raise HTTPException(status_code=404, detail="Fault run not found.")
    if request.active is not None:
        if request.active:
            scoped_ids = {str(value) for value in run.submission_ids}
            overlap = next(
                (
                    candidate
                    for candidate in runs
                    if candidate.run_id != run.run_id
                    and candidate.active
                    and scoped_ids.intersection(str(value) for value in candidate.submission_ids)
                ),
                None,
            )
            if overlap:
                db.rollback()
                raise HTTPException(
                    status_code=409,
                    detail="Another active fault run already owns part of this synthetic batch.",
                )
        run.active = request.active
    if request.hold_delivery is not None:
        run.hold_delivery = request.hold_delivery
    if request.reset_window:
        run.window_started_at = None
        run.window_count = 0
    db.commit()
    return {
        "run_id": run.run_id,
        "active": run.active,
        "hold_delivery": run.hold_delivery,
        "window_count": run.window_count,
    }


@router.get("/api/recovery/fault-runs/{run_id}")
def get_fault_run(
    run_id: uuid.UUID,
    _: None = Depends(require_crm_adapter_key),
    db: Session = Depends(get_db),
) -> dict:
    run = db.get(CRMFaultRun, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Fault run not found.")
    return {
        "run_id": run.run_id,
        "submission_ids": run.submission_ids,
        "active": run.active,
        "hold_delivery": run.hold_delivery,
        "request_limit": run.request_limit,
        "window_seconds": run.window_seconds,
        "window_started_at": run.window_started_at,
        "window_count": run.window_count,
    }


@router.get("/api/recovery/jobs", response_model=list[RecoveryJobResponse])
def list_recovery_jobs(
    correlation_id: uuid.UUID | None = None,
    state: str | None = None,
    _: None = Depends(require_crm_adapter_key),
    db: Session = Depends(get_db),
) -> list[CRMWriteJob]:
    statement = select(CRMWriteJob).order_by(CRMWriteJob.created_at)
    if correlation_id:
        statement = statement.where(CRMWriteJob.correlation_id == correlation_id)
    if state:
        statement = statement.where(CRMWriteJob.state == state)
    return list(db.scalars(statement))


@router.get("/api/recovery/jobs/{job_id}/attempts")
def list_recovery_attempts(
    job_id: uuid.UUID,
    _: None = Depends(require_crm_adapter_key),
    db: Session = Depends(get_db),
) -> list[dict]:
    if not db.get(CRMWriteJob, job_id):
        raise HTTPException(status_code=404, detail="Recovery job not found.")
    attempts = db.scalars(
        select(CRMWriteAttempt)
        .where(CRMWriteAttempt.job_id == job_id)
        .order_by(CRMWriteAttempt.attempt_number)
    )
    return [
        {
            "attempt_id": attempt.id,
            "attempt_number": attempt.attempt_number,
            "started_at": attempt.started_at,
            "finished_at": attempt.finished_at,
            "outcome": attempt.outcome,
            "status_code": attempt.status_code,
            "error_class": attempt.error_class,
            "retry_after_raw": attempt.retry_after_raw,
            "retry_after_seconds": attempt.retry_after_seconds,
            "execution_reference": attempt.execution_reference,
        }
        for attempt in attempts
    ]


@router.get("/api/crm/follow-ups/due", response_model=list[FollowUpResponse])
def list_due_follow_ups(
    limit: int = 25,
    _: None = Depends(require_crm_adapter_key),
    db: Session = Depends(get_db),
) -> list[FollowUp]:
    if limit < 1 or limit > 100:
        raise HTTPException(status_code=422, detail="limit must be between 1 and 100")
    return lifecycle_service.due_follow_ups(db, limit)


@router.post(
    "/api/crm/follow-ups/{follow_up_id}/dispatch", response_model=EmailDispatchResponse
)
def dispatch_follow_up(
    follow_up_id: uuid.UUID,
    _: None = Depends(require_crm_adapter_key),
    db: Session = Depends(get_db),
) -> EmailDispatchResponse:
    try:
        result = lifecycle_service.dispatch_follow_up(db, follow_up_id)
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except BookingValidationError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except EmailDeliveryError as error:
        db.rollback()
        raise HTTPException(status_code=503, detail=str(error)) from error
    return EmailDispatchResponse(
        state=result.state, pipeline_stage=result.pipeline_stage, sent_at=result.sent_at
    )


@router.post(
    "/api/crm/bookings", response_model=BookingCreateResponse, status_code=status.HTTP_201_CREATED
)
def create_booking(
    payload: BookingCreate,
    response: Response,
    _: None = Depends(require_crm_adapter_key),
    db: Session = Depends(get_db),
) -> BookingCreateResponse:
    try:
        result = lifecycle_service.create_booking(db, payload)
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except BookingValidationError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except BookingConflictError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    appointment = result.appointment
    lead = db.get(Lead, appointment.lead_id)
    response.status_code = status.HTTP_201_CREATED if result.created else status.HTTP_200_OK
    confirmation_state = "sent" if appointment.confirmation_sent_at else "pending"
    if not lead.email:
        confirmation_state = "skipped_no_email"
    return BookingCreateResponse(
        appointment_id=appointment.id,
        booking_request_id=appointment.booking_request_id,
        correlation_id=appointment.correlation_id,
        booking_state="created" if result.created else "replayed",
        appointment_status=appointment.status,
        appointment_at=appointment.appointment_at,
        business_timezone=appointment.business_timezone,
        pipeline_stage=lead.pipeline_stage,
        follow_up_status=result.follow_up.status if result.follow_up else None,
        confirmation_state=confirmation_state,
    )


@router.post(
    "/api/crm/appointments/{appointment_id}/confirmation",
    response_model=BookingConfirmationResponse,
)
def send_booking_confirmation(
    appointment_id: uuid.UUID,
    _: None = Depends(require_crm_adapter_key),
    db: Session = Depends(get_db),
) -> BookingConfirmationResponse:
    try:
        result = lifecycle_service.send_booking_confirmation(db, appointment_id)
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except EmailDeliveryError as error:
        db.rollback()
        raise HTTPException(status_code=503, detail=str(error)) from error
    appointment = db.get(Appointment, appointment_id)
    return BookingConfirmationResponse(
        appointment_id=appointment.id,
        correlation_id=appointment.correlation_id,
        state=result.state,
        pipeline_stage=result.pipeline_stage,
        sent_at=result.sent_at,
    )


@router.get("/api/leads", response_model=list[LeadResponse])
def list_leads(
    correlation_id: uuid.UUID | None = None, db: Session = Depends(get_db)
) -> list[Lead]:
    statement = select(Lead).order_by(Lead.created_at.desc())
    if correlation_id:
        statement = statement.where(Lead.correlation_id == correlation_id)
    return list(db.scalars(statement))


@router.get("/api/audit-events", response_model=list[AuditEventResponse])
def list_audit_events(correlation_id: uuid.UUID, db: Session = Depends(get_db)) -> list[AuditEvent]:
    statement = (
        select(AuditEvent)
        .where(AuditEvent.correlation_id == correlation_id)
        .order_by(AuditEvent.created_at.asc())
    )
    return list(db.scalars(statement))


@router.get("/api/traces/{correlation_id}", response_model=TraceResponse)
def get_trace(correlation_id: uuid.UUID, db: Session = Depends(get_db)) -> TraceResponse:
    lead = db.scalar(select(Lead).where(Lead.correlation_id == correlation_id))
    follow_ups = list(
        db.scalars(
            select(FollowUp)
            .where(FollowUp.correlation_id == correlation_id)
            .order_by(FollowUp.created_at.asc())
        )
    )
    appointments = list(
        db.scalars(
            select(Appointment)
            .where(Appointment.correlation_id == correlation_id)
            .order_by(Appointment.created_at.asc())
        )
    )
    audit_events = list_audit_events(correlation_id=correlation_id, db=db)
    recovery_jobs = list(
        db.scalars(select(CRMWriteJob).where(CRMWriteJob.correlation_id == correlation_id))
    )
    incidents = list(
        db.scalars(
            select(RecoveryIncident).where(RecoveryIncident.correlation_id == correlation_id)
        )
    )
    return TraceResponse(
        correlation_id=correlation_id,
        lead=lead,
        follow_ups=follow_ups,
        appointments=appointments,
        audit_events=audit_events,
        recovery_jobs=[
            {
                "id": str(job.id), "submission_id": str(job.submission_id),
                "state": job.state, "attempt_count": job.attempt_count,
                "due_at": job.due_at.isoformat(),
                "completed_lead_id": str(job.completed_lead_id) if job.completed_lead_id else None,
                "last_error_class": job.last_error_class,
            }
            for job in recovery_jobs
        ],
        recovery_incidents=[
            {
                "id": str(incident.id), "state": incident.state,
                "execution_reference": incident.execution_reference,
                "failed_node": incident.failed_node, "error_class": incident.error_class,
            }
            for incident in incidents
        ],
    )


@router.get("/api/leads/{lead_id}", response_model=LeadResponse)
def get_lead(lead_id: uuid.UUID, db: Session = Depends(get_db)) -> Lead:
    lead = db.get(Lead, lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    return lead
