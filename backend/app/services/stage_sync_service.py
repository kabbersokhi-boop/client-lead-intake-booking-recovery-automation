"""Coalescing desired-state outbox for the managed HighLevel opportunity stages."""

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import or_, select, text
from sqlalchemy.orm import Session

from app.config import settings
from app.models import CRMWriteJob, Lead, StageSyncAttempt, StageSyncJob
from app.providers.highlevel import HighLevelClient, HighLevelProviderError
from app.services.recovery_service import RecoveryService, parse_retry_after, retry_decision

STAGE_RANK = {"new_lead": 0, "contacted": 1, "appointment_booked": 2}


class StageSyncLeaseError(Exception):
    pass


@dataclass(frozen=True)
class StageSyncResult:
    state: str
    desired_stage: str
    desired_version: int
    verified_remote_stage: str | None


class StageSyncService:
    @staticmethod
    def advance(db: Session, lead: Lead, stage: str) -> StageSyncJob | None:
        """Called while the Lead row is locked, before the lifecycle commit."""
        if settings.crm_provider_mode not in {"highlevel_live", "highlevel_simulator"}:
            return None
        rank = STAGE_RANK[stage]
        if rank == 0:
            return None
        job = db.scalar(
            select(StageSyncJob).where(StageSyncJob.lead_id == lead.id).with_for_update()
        )
        if job is None:
            job = StageSyncJob(
                lead_id=lead.id,
                submission_id=lead.submission_id,
                correlation_id=lead.correlation_id,
                desired_stage=stage,
                desired_rank=rank,
                desired_version=1,
                state="pending",
                due_at=datetime.now(timezone.utc),
            )
            db.add(job)
        elif rank > job.desired_rank:
            job.desired_stage = stage
            job.desired_rank = rank
            job.desired_version += 1
            job.generation_attempt_count = 0
            job.due_at = datetime.now(timezone.utc)
            if job.state not in {"processing", "blocked", "needs_review"}:
                job.state = "pending"
                job.last_error_class = None
                job.last_error_message = None
        return job

    @staticmethod
    def claim(db: Session, owner: str) -> StageSyncJob | None:
        now = datetime.now(timezone.utc)
        if db.scalar(
            select(StageSyncJob.id).where(
                StageSyncJob.state == "blocked",
                StageSyncJob.last_error_class == "highlevel_authentication",
            ).limit(1)
        ) is not None:
            return None
        job = db.scalar(
            select(StageSyncJob)
            .where(
                or_(
                    StageSyncJob.state.in_(("pending", "retry_wait"))
                    & (StageSyncJob.due_at <= now),
                    (StageSyncJob.state == "processing")
                    & (StageSyncJob.lease_expires_at <= now),
                )
            )
            .order_by(StageSyncJob.due_at, StageSyncJob.id)
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        if job is None:
            return None
        if job.state == "processing" and job.lease_token:
            for attempt in db.scalars(
                select(StageSyncAttempt).where(
                    StageSyncAttempt.job_id == job.id,
                    StageSyncAttempt.lease_token == job.lease_token,
                    StageSyncAttempt.finished_at.is_(None),
                )
            ):
                attempt.outcome = "lease_expired"
                attempt.finished_at = now
        job.state = "processing"
        job.lease_token = uuid.uuid4()
        job.lease_owner = owner[:160]
        job.lease_expires_at = now + timedelta(seconds=settings.stage_sync_lease_seconds)
        db.commit()
        db.refresh(job)
        return job

    @staticmethod
    def requeue(db: Session, job_id: uuid.UUID) -> StageSyncJob:
        job = db.scalar(select(StageSyncJob).where(StageSyncJob.id == job_id).with_for_update())
        if not job or job.state not in {"blocked", "needs_review"}:
            raise ValueError("Only held stage sync work can be requeued.")
        job.state = "pending"
        job.due_at = datetime.now(timezone.utc)
        job.generation_attempt_count = 0
        job.last_error_class = None
        job.last_error_message = None
        db.commit()
        db.refresh(job)
        return job

    @staticmethod
    def _owned(db: Session, job_id: uuid.UUID, token: uuid.UUID) -> StageSyncJob:
        job = db.scalar(
            select(StageSyncJob).where(StageSyncJob.id == job_id).with_for_update()
            .execution_options(populate_existing=True)
        )
        now = datetime.now(timezone.utc)
        if (
            not job or job.state != "processing" or job.lease_token != token
            or not job.lease_expires_at
            or RecoveryService._aware(job.lease_expires_at) <= now
        ):
            raise StageSyncLeaseError("Stage sync lease is stale.")
        return job

    @staticmethod
    def _release(job: StageSyncJob) -> None:
        job.lease_token = None
        job.lease_owner = None
        job.lease_expires_at = None

    def process(
        self, db: Session, job_id: uuid.UUID, token: uuid.UUID, client: HighLevelClient
    ) -> StageSyncResult:
        # A transaction-scoped advisory lock serializes remote writes even after a lease expires.
        # It does not lock the desired row, so booking can advance it during network work.
        engine = db.get_bind()
        with engine.connect() as guard:
            with guard.begin():
                if guard.dialect.name == "postgresql":
                    key = job_id.int & ((1 << 63) - 1)
                    acquired = guard.scalar(
                        text("SELECT pg_try_advisory_xact_lock(:key)"), {"key": key}
                    )
                    if not acquired:
                        return self._defer_busy(db, job_id, token)
                return self._process_guarded(db, job_id, token, client)

    def _defer_busy(self, db: Session, job_id: uuid.UUID, token: uuid.UUID) -> StageSyncResult:
        job = self._owned(db, job_id, token)
        active = db.scalar(select(StageSyncAttempt.id).where(
            StageSyncAttempt.job_id == job.id,
            StageSyncAttempt.lease_token == token,
            StageSyncAttempt.finished_at.is_(None),
        ).limit(1))
        if active:
            result = StageSyncResult(
                job.state, job.desired_stage, job.desired_version,
                job.verified_remote_stage,
            )
            db.rollback()
            return result
        job.state = "retry_wait"
        job.due_at = datetime.now(timezone.utc) + timedelta(seconds=5)
        self._release(job)
        result = StageSyncResult(job.state, job.desired_stage, job.desired_version,
                                 job.verified_remote_stage)
        db.commit()
        return result

    def _process_guarded(
        self, db: Session, job_id: uuid.UUID, token: uuid.UUID, client: HighLevelClient
    ) -> StageSyncResult:
        job = self._owned(db, job_id, token)
        create_job = db.scalar(select(CRMWriteJob).where(
            CRMWriteJob.submission_id == job.submission_id,
            CRMWriteJob.operation_kind == "create_lead",
        ))
        if create_job and create_job.state != "completed":
            now = datetime.now(timezone.utc)
            if create_job.state == "blocked":
                job.state = "blocked"
                job.last_error_class = "highlevel_create_blocked"
                job.last_error_message = "Initial HighLevel projection is blocked."
            elif create_job.state == "needs_review" or (
                now - RecoveryService._aware(job.created_at) >= timedelta(hours=24)
            ):
                job.state = "needs_review"
                job.last_error_class = "highlevel_create_unverified"
                job.last_error_message = "Initial HighLevel projection needs review."
            else:
                job.state = "retry_wait"
                job.due_at = max(
                    now + timedelta(seconds=15),
                    RecoveryService._aware(create_job.due_at),
                )
            self._release(job)
            result = StageSyncResult(
                job.state, job.desired_stage, job.desired_version, job.verified_remote_stage
            )
            db.commit()
            return result
        lead = db.get(Lead, job.lead_id)
        version = job.desired_version
        stage = job.desired_stage
        job.attempt_count += 1
        job.generation_attempt_count += 1
        attempt = StageSyncAttempt(
            job_id=job.id,
            attempt_number=job.attempt_count,
            desired_version=version,
            desired_stage=stage,
            lease_token=token,
            started_at=datetime.now(timezone.utc),
        )
        db.add(attempt)
        db.commit()
        try:
            verified_stage = client.sync_opportunity_stage(lead, stage)
        except HighLevelProviderError as error:
            return self._settle(db, job_id, token, attempt.id, version, None, error)
        return self._settle(db, job_id, token, attempt.id, version, verified_stage, None)

    def _settle(
        self, db: Session, job_id: uuid.UUID, token: uuid.UUID,
        attempt_id: uuid.UUID, version: int, verified_stage: str | None,
        error: HighLevelProviderError | None,
    ) -> StageSyncResult:
        job = self._owned(db, job_id, token)
        attempt = db.get(StageSyncAttempt, attempt_id)
        attempt.finished_at = datetime.now(timezone.utc)
        if error:
            attempt.outcome = "failed"
            attempt.error_class = error.error_class
            attempt.status_code = error.status_code
        else:
            attempt.outcome = "verified"
            attempt.verified_remote_stage = verified_stage
            job.verified_remote_stage = verified_stage
        if job.desired_version != version:
            attempt.outcome = "superseded" if not error else "failed_superseded"
            job.state = "pending"
            job.due_at = datetime.now(timezone.utc)
        elif error:
            now = datetime.now(timezone.utc)
            decision = retry_decision(
                error.status_code, job.generation_attempt_count,
                error.retry_after, now,
            )
            job.state = decision.state
            job.due_at = decision.due_at
            if error.status_code != 429 and error.retry_after and job.state == "retry_wait":
                parsed = parse_retry_after(error.retry_after, now)
                if parsed.unrepresentable:
                    job.state = "needs_review"
                elif parsed.seconds is not None:
                    job.due_at = max(job.due_at, now + timedelta(seconds=parsed.seconds))
            job.last_error_class = error.error_class
            job.last_error_message = error.safe_message
            attempt.retry_after_seconds = decision.retry_after_seconds
        else:
            job.state = "completed"
            job.last_error_class = None
            job.last_error_message = None
        self._release(job)
        result = StageSyncResult(job.state, job.desired_stage, job.desired_version,
                                 job.verified_remote_stage)
        db.commit()
        return result
