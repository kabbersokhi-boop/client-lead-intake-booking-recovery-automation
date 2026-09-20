import math
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import settings
from app.models import CRMWriteAttempt, CRMWriteJob, Lead, RecoveryIncident
from app.schemas.lead import CRMLeadCreate
from app.services.crm_service import submission_fingerprint


class RecoveryConflictError(Exception):
    pass


class StaleLeaseError(Exception):
    pass


@dataclass(frozen=True)
class RetryDecision:
    state: str
    due_at: datetime
    retry_after_seconds: int | None


def retry_after_seconds(value: str | None, now: datetime) -> int | None:
    if not value:
        return None
    value = value.strip()
    if value.isdigit():
        return int(value)
    try:
        parsed = parsedate_to_datetime(value)
    except (TypeError, ValueError, OverflowError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return max(0, math.ceil((parsed.astimezone(timezone.utc) - now).total_seconds()))


def retry_decision(
    status_code: int | None,
    attempt_count: int,
    retry_after: str | None,
    now: datetime,
) -> RetryDecision:
    parsed_retry = retry_after_seconds(retry_after, now)
    if status_code in {400, 404, 409, 422}:
        return RetryDecision("needs_review", now, parsed_retry)
    if status_code in {401, 403}:
        return RetryDecision("blocked", now, parsed_retry)
    if attempt_count >= settings.crm_recovery_max_attempts:
        return RetryDecision("needs_review", now, parsed_retry)
    if status_code == 429:
        delay = parsed_retry if parsed_retry is not None else settings.crm_retry_fallback_seconds
    elif status_code is None or status_code >= 500:
        delay = settings.crm_retry_fallback_seconds * (2 ** max(0, attempt_count - 1))
    else:
        return RetryDecision("needs_review", now, parsed_retry)
    return RetryDecision("retry_wait", now + timedelta(seconds=delay), parsed_retry)


class RecoveryService:
    @staticmethod
    def _aware(value: datetime | None) -> datetime | None:
        if value is not None and value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value

    @staticmethod
    def _credential_pause_exists(db: Session) -> bool:
        return (
            db.scalar(
                select(CRMWriteJob.id)
                .where(
                    CRMWriteJob.state == "blocked",
                    CRMWriteJob.last_error_class.in_(
                        [
                            "http_401",
                            "http_403",
                            "reconciliation_http_401",
                            "reconciliation_http_403",
                        ]
                    ),
                )
                .limit(1)
            )
            is not None
        )

    def admit(
        self,
        db: Session,
        payload: CRMLeadCreate,
        execution_reference: str | None = None,
        now: datetime | None = None,
    ) -> tuple[CRMWriteJob, bool]:
        now = now or datetime.now(timezone.utc)
        fingerprint = submission_fingerprint(payload)
        existing = db.scalar(
            select(CRMWriteJob).where(
                CRMWriteJob.submission_id == payload.submission_id,
                CRMWriteJob.operation_kind == "create_lead",
            )
        )
        if existing:
            if (
                existing.payload_fingerprint != fingerprint
                or existing.correlation_id != payload.correlation_id
            ):
                raise RecoveryConflictError
            return existing, False
        lead = db.scalar(select(Lead).where(Lead.submission_id == payload.submission_id))
        if lead and (
            lead.submission_fingerprint != fingerprint
            or lead.correlation_id != payload.correlation_id
        ):
            raise RecoveryConflictError
        job = CRMWriteJob(
            submission_id=payload.submission_id,
            correlation_id=payload.correlation_id,
            payload_fingerprint=fingerprint,
            payload_json=payload.model_dump(mode="json", exclude_none=False),
            state="completed" if lead else "pending",
            due_at=now,
            completed_lead_id=lead.id if lead else None,
            source_execution_reference=execution_reference,
        )
        db.add(job)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            existing = db.scalar(
                select(CRMWriteJob).where(
                    CRMWriteJob.submission_id == payload.submission_id,
                    CRMWriteJob.operation_kind == "create_lead",
                )
            )
            if (
                not existing
                or existing.payload_fingerprint != fingerprint
                or existing.correlation_id != payload.correlation_id
            ):
                raise RecoveryConflictError
            return existing, False
        db.refresh(job)
        return job, True

    def claim(
        self,
        db: Session,
        worker_id: str,
        execution_reference: str | None = None,
        now: datetime | None = None,
    ) -> CRMWriteJob | None:
        now = now or datetime.now(timezone.utc)
        if self._credential_pause_exists(db):
            db.rollback()
            return None
        statement = (
            select(CRMWriteJob)
            .where(
                or_(
                    CRMWriteJob.state.in_(["pending", "retry_wait"]),
                    (CRMWriteJob.state == "processing")
                    & (CRMWriteJob.lease_expires_at <= now),
                ),
                CRMWriteJob.due_at <= now,
            )
            .order_by(CRMWriteJob.due_at, CRMWriteJob.created_at)
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        job = db.scalar(statement)
        if not job:
            db.rollback()
            return None
        job.state = "processing"
        job.lease_token = uuid.uuid4()
        job.lease_owner = worker_id
        job.lease_expires_at = now + timedelta(seconds=settings.crm_recovery_lease_seconds)
        job.quota_permit_until = None
        job.quota_permit_lease_token = None
        if execution_reference:
            job.source_execution_reference = execution_reference
        db.commit()
        db.refresh(job)
        return job

    def claim_specific(
        self,
        db: Session,
        job_id: uuid.UUID,
        worker_id: str,
        execution_reference: str | None = None,
        now: datetime | None = None,
    ) -> CRMWriteJob:
        now = now or datetime.now(timezone.utc)
        if self._credential_pause_exists(db):
            db.rollback()
            raise RecoveryConflictError(
                "CRM recovery is paused after a credential or permission failure"
            )
        job = db.scalar(select(CRMWriteJob).where(CRMWriteJob.id == job_id).with_for_update())
        eligible = job and (
            job.state in {"pending", "retry_wait"}
            or (
                job.state == "processing"
                and job.lease_expires_at is not None
                and self._aware(job.lease_expires_at) <= now
            )
        )
        if not eligible or self._aware(job.due_at) > now:
            raise RecoveryConflictError("Recovery job is not currently claimable")
        job.state = "processing"
        job.lease_token = uuid.uuid4()
        job.lease_owner = worker_id
        job.lease_expires_at = now + timedelta(seconds=settings.crm_recovery_lease_seconds)
        job.quota_permit_until = None
        job.quota_permit_lease_token = None
        if execution_reference:
            job.source_execution_reference = execution_reference
        db.commit()
        db.refresh(job)
        return job

    def _leased_job(
        self, db: Session, job_id: uuid.UUID, lease_token: uuid.UUID
    ) -> CRMWriteJob:
        job = db.scalar(select(CRMWriteJob).where(CRMWriteJob.id == job_id).with_for_update())
        now = datetime.now(timezone.utc)
        if (
            not job
            or job.state != "processing"
            or job.lease_token != lease_token
            or job.lease_expires_at is None
            or self._aware(job.lease_expires_at) <= now
        ):
            raise StaleLeaseError
        return job

    def start_attempt(
        self,
        db: Session,
        job_id: uuid.UUID,
        lease_token: uuid.UUID,
        execution_reference: str | None = None,
        now: datetime | None = None,
    ) -> CRMWriteAttempt:
        now = now or datetime.now(timezone.utc)
        job = self._leased_job(db, job_id, lease_token)
        unfinished = db.scalar(
            select(CRMWriteAttempt)
            .where(
                CRMWriteAttempt.job_id == job.id,
                CRMWriteAttempt.finished_at.is_(None),
            )
            .order_by(CRMWriteAttempt.attempt_number.desc())
        )
        if unfinished:
            if unfinished.lease_token == lease_token:
                db.rollback()
                return unfinished
            raise RecoveryConflictError(
                "An earlier uncertain attempt must be reconciled before another write."
            )
        if (
            job.attempt_count >= settings.crm_recovery_max_attempts
            and not job.manual_attempt_authorized
        ):
            job.state = "needs_review"
            job.lease_token = None
            job.lease_owner = None
            job.lease_expires_at = None
            db.commit()
            raise RecoveryConflictError("Automatic attempt budget exhausted")
        job.manual_attempt_authorized = False
        job.attempt_count += 1
        attempt = CRMWriteAttempt(
            job_id=job.id,
            attempt_number=job.attempt_count,
            started_at=now,
            lease_token=lease_token,
            execution_reference=execution_reference,
        )
        db.add(attempt)
        db.commit()
        db.refresh(attempt)
        return attempt

    def begin_diagnostic_attempt(
        self,
        db: Session,
        submission_id: uuid.UUID,
        execution_reference: str | None,
        now: datetime | None = None,
    ) -> tuple[CRMWriteJob, CRMWriteAttempt] | None:
        now = now or datetime.now(timezone.utc)
        job = db.scalar(
            select(CRMWriteJob)
            .where(CRMWriteJob.submission_id == submission_id)
            .with_for_update()
        )
        if not job or job.state == "completed":
            db.rollback()
            return None
        eligible = job.state in {"pending", "retry_wait"} or (
            job.state == "processing"
            and job.lease_expires_at is not None
            and self._aware(job.lease_expires_at) <= now
        )
        if not eligible or self._aware(job.due_at) > now:
            raise RecoveryConflictError("Recovery job is not currently claimable")
        if job.attempt_count >= settings.crm_recovery_max_attempts:
            raise RecoveryConflictError("Automatic attempt budget exhausted")
        unfinished = db.scalar(
            select(CRMWriteAttempt).where(
                CRMWriteAttempt.job_id == job.id,
                CRMWriteAttempt.finished_at.is_(None),
            )
        )
        if unfinished:
            raise RecoveryConflictError(
                "An earlier uncertain attempt must be reconciled before another write."
            )
        lease_token = uuid.uuid4()
        job.state = "processing"
        job.lease_token = lease_token
        job.lease_owner = "n8n-diagnostic"
        job.lease_expires_at = now + timedelta(seconds=settings.crm_recovery_lease_seconds)
        job.quota_permit_until = None
        job.quota_permit_lease_token = None
        job.attempt_count += 1
        attempt = CRMWriteAttempt(
            job_id=job.id,
            attempt_number=job.attempt_count,
            started_at=now,
            lease_token=lease_token,
            execution_reference=execution_reference,
        )
        db.add(attempt)
        db.commit()
        db.refresh(job)
        db.refresh(attempt)
        return job, attempt

    def defer(
        self,
        db: Session,
        job_id: uuid.UUID,
        lease_token: uuid.UUID,
        delay_seconds: int,
        now: datetime | None = None,
    ) -> CRMWriteJob:
        now = now or datetime.now(timezone.utc)
        job = self._leased_job(db, job_id, lease_token)
        job.state = "retry_wait"
        job.due_at = now + timedelta(seconds=delay_seconds)
        job.lease_token = None
        job.lease_owner = None
        job.lease_expires_at = None
        job.quota_permit_until = None
        job.quota_permit_lease_token = None
        job.last_error_class = "quota_deferred"
        job.last_error_message = "Shared CRM quota deferred this operation without an API attempt."
        db.commit()
        db.refresh(job)
        return job

    def complete(
        self,
        db: Session,
        job_id: uuid.UUID,
        lease_token: uuid.UUID,
        lead_id: uuid.UUID,
        attempt_id: uuid.UUID | None = None,
        status_code: int = 200,
        now: datetime | None = None,
    ) -> CRMWriteJob:
        now = now or datetime.now(timezone.utc)
        job = self._leased_job(db, job_id, lease_token)
        lead = db.get(Lead, lead_id)
        if not lead or (
            lead.submission_id != job.submission_id
            or lead.correlation_id != job.correlation_id
            or lead.submission_fingerprint != job.payload_fingerprint
        ):
            raise RecoveryConflictError("CRM result does not match the recovery operation")
        attempt = None
        if attempt_id:
            attempt = db.scalar(
                select(CRMWriteAttempt).where(
                    CRMWriteAttempt.id == attempt_id,
                    CRMWriteAttempt.job_id == job.id,
                )
            )
            if (
                not attempt
                or attempt.finished_at is not None
                or attempt.lease_token != lease_token
            ):
                raise RecoveryConflictError("Attempt does not belong to this active lease")
        job.state = "completed"
        job.completed_lead_id = lead.id
        job.last_error_class = None
        job.last_error_message = None
        job.manual_attempt_authorized = False
        job.lease_token = None
        job.lease_owner = None
        job.lease_expires_at = None
        job.quota_permit_until = None
        job.quota_permit_lease_token = None
        job.reconciliation_failure_count = 0
        if attempt:
            attempt.finished_at = now
            attempt.outcome = "completed"
            attempt.status_code = status_code
        else:
            for attempt in db.scalars(
                select(CRMWriteAttempt).where(
                    CRMWriteAttempt.job_id == job.id,
                    CRMWriteAttempt.finished_at.is_(None),
                )
            ):
                attempt.finished_at = now
                attempt.outcome = "reconciled"
                attempt.status_code = 200
        for incident in db.scalars(
            select(RecoveryIncident).where(
                RecoveryIncident.job_id == job.id, RecoveryIncident.state == "open"
            )
        ):
            incident.state = "resolved"
            incident.resolved_at = now
        db.commit()
        db.refresh(job)
        return job

    def fail(
        self,
        db: Session,
        job_id: uuid.UUID,
        lease_token: uuid.UUID,
        attempt_id: uuid.UUID,
        status_code: int | None,
        error_class: str,
        safe_message: str,
        retry_after: str | None,
        execution_reference: str | None = None,
        now: datetime | None = None,
    ) -> CRMWriteJob:
        now = now or datetime.now(timezone.utc)
        job = self._leased_job(db, job_id, lease_token)
        decision = retry_decision(status_code, job.attempt_count, retry_after, now)
        attempt = db.scalar(
            select(CRMWriteAttempt).where(
                CRMWriteAttempt.id == attempt_id,
                CRMWriteAttempt.job_id == job.id,
            )
        )
        if (
            not attempt
            or attempt.finished_at is not None
            or attempt.lease_token != lease_token
        ):
            raise RecoveryConflictError("Attempt does not belong to this active lease")
        attempt.finished_at = now
        attempt.outcome = "failed"
        attempt.status_code = status_code
        attempt.error_class = error_class
        attempt.retry_after_raw = retry_after
        attempt.retry_after_seconds = decision.retry_after_seconds
        attempt.execution_reference = execution_reference or attempt.execution_reference
        job.state = decision.state
        job.due_at = decision.due_at
        job.last_error_class = error_class
        job.last_error_message = safe_message
        job.lease_token = None
        job.lease_owner = None
        job.lease_expires_at = None
        job.quota_permit_until = None
        job.quota_permit_lease_token = None
        db.commit()
        db.refresh(job)
        return job

    def confirm_absent(
        self,
        db: Session,
        job_id: uuid.UUID,
        lease_token: uuid.UUID,
        now: datetime | None = None,
    ) -> CRMWriteJob:
        now = now or datetime.now(timezone.utc)
        job = self._leased_job(db, job_id, lease_token)
        for attempt in db.scalars(
            select(CRMWriteAttempt).where(
                CRMWriteAttempt.job_id == job.id,
                CRMWriteAttempt.finished_at.is_(None),
            )
        ):
            attempt.finished_at = now
            attempt.outcome = "verified_absent"
            attempt.status_code = 404
        job.reconciliation_failure_count = 0
        db.commit()
        db.refresh(job)
        return job

    def fail_reconciliation(
        self,
        db: Session,
        job_id: uuid.UUID,
        lease_token: uuid.UUID,
        status_code: int | None,
        error_class: str,
        safe_message: str,
        retry_after: str | None,
        now: datetime | None = None,
    ) -> CRMWriteJob:
        now = now or datetime.now(timezone.utc)
        job = self._leased_job(db, job_id, lease_token)
        job.reconciliation_failure_count += 1
        parsed_retry = retry_after_seconds(retry_after, now)
        if status_code in {401, 403}:
            state = "blocked"
            due_at = now
        elif status_code in {400, 404, 409, 422} or (
            status_code is not None and status_code < 500 and status_code != 429
        ):
            state = "needs_review"
            due_at = now
        elif job.reconciliation_failure_count >= settings.crm_recovery_max_attempts:
            state = "needs_review"
            due_at = now
        elif status_code == 429:
            delay = (
                parsed_retry
                if parsed_retry is not None
                else settings.crm_retry_fallback_seconds
            )
            state = "retry_wait"
            due_at = now + timedelta(seconds=delay)
        else:
            delay = settings.crm_retry_fallback_seconds * (
                2 ** max(0, job.reconciliation_failure_count - 1)
            )
            state = "retry_wait"
            due_at = now + timedelta(seconds=delay)
        job.state = state
        job.due_at = due_at
        job.last_error_class = error_class
        job.last_error_message = safe_message
        job.lease_token = None
        job.lease_owner = None
        job.lease_expires_at = None
        job.quota_permit_until = None
        job.quota_permit_lease_token = None
        db.commit()
        db.refresh(job)
        return job

    def requeue(self, db: Session, job_id: uuid.UUID, now: datetime | None = None) -> CRMWriteJob:
        job = db.get(CRMWriteJob, job_id)
        if not job or job.state not in {"needs_review", "blocked"}:
            raise RecoveryConflictError("Only held work can be manually requeued")
        job.state = "pending"
        job.due_at = now or datetime.now(timezone.utc)
        job.last_error_class = None
        job.last_error_message = None
        job.manual_attempt_authorized = True
        job.reconciliation_failure_count = 0
        db.commit()
        db.refresh(job)
        return job

    def record_incident(self, db: Session, **values) -> tuple[RecoveryIncident, bool]:
        existing = db.scalar(
            select(RecoveryIncident).where(RecoveryIncident.event_key == values["event_key"])
        )
        if existing:
            return existing, False
        job = db.get(CRMWriteJob, values.get("job_id")) if values.get("job_id") else None
        if not job and values.get("execution_reference"):
            attempt = db.scalar(
                select(CRMWriteAttempt)
                .where(
                    CRMWriteAttempt.execution_reference == values["execution_reference"],
                    CRMWriteAttempt.outcome == "failed",
                )
                .order_by(CRMWriteAttempt.finished_at.desc())
            )
            if not attempt:
                attempt = db.scalar(
                    select(CRMWriteAttempt)
                    .where(
                        CRMWriteAttempt.execution_reference
                        == values["execution_reference"]
                    )
                    .order_by(CRMWriteAttempt.created_at.desc())
                )
            if attempt:
                job = db.get(CRMWriteJob, attempt.job_id)
                values["job_id"] = job.id
        if job:
            values["correlation_id"] = job.correlation_id
            if job.state == "completed":
                values["state"] = "resolved"
                values["resolved_at"] = datetime.now(timezone.utc)
        incident = RecoveryIncident(**values)
        db.add(incident)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            return db.scalar(
                select(RecoveryIncident).where(
                    RecoveryIncident.event_key == values["event_key"]
                )
            ), False
        db.refresh(incident)
        return incident, True
