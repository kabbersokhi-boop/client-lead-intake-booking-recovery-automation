import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.db.base import Base

JsonType = JSON().with_variant(JSONB, "postgresql")


class Lead(Base):
    __tablename__ = "leads"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    submission_id: Mapped[uuid.UUID] = mapped_column(unique=True, nullable=False, index=True)
    correlation_id: Mapped[uuid.UUID] = mapped_column(nullable=False, index=True)
    full_name: Mapped[str] = mapped_column(String(160), nullable=False)
    email: Mapped[str | None] = mapped_column(String(254))
    phone: Mapped[str | None] = mapped_column(String(50))
    original_message: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_message: Mapped[str] = mapped_column(Text, nullable=False)
    submission_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    client_received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    service_type: Mapped[str | None] = mapped_column(String(80))
    location: Mapped[str | None] = mapped_column(String(160))
    preferred_time: Mapped[str | None] = mapped_column(String(160))
    urgency: Mapped[str | None] = mapped_column(String(20))
    summary: Mapped[str | None] = mapped_column(Text)
    provider_metadata: Mapped[dict | None] = mapped_column(JsonType)
    ai_status: Mapped[str] = mapped_column(String(30), nullable=False)
    needs_review: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    pipeline_stage: Mapped[str] = mapped_column(String(40), nullable=False, default="new_lead")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    correlation_id: Mapped[uuid.UUID] = mapped_column(nullable=False, index=True)
    lead_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("leads.id"), index=True)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    metadata_json: Mapped[dict] = mapped_column(JsonType, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class FollowUp(Base):
    __tablename__ = "follow_ups"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    lead_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("leads.id"), nullable=False, unique=True, index=True
    )
    correlation_id: Mapped[uuid.UUID] = mapped_column(nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="pending")
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Appointment(Base):
    __tablename__ = "appointments"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    booking_request_id: Mapped[uuid.UUID] = mapped_column(unique=True, nullable=False, index=True)
    lead_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("leads.id"), nullable=False, unique=True, index=True
    )
    correlation_id: Mapped[uuid.UUID] = mapped_column(nullable=False, index=True)
    appointment_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    business_timezone: Mapped[str] = mapped_column(String(80), nullable=False)
    booking_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="booked")
    confirmation_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class CRMWriteJob(Base):
    __tablename__ = "crm_write_jobs"
    __table_args__ = (UniqueConstraint("submission_id", "operation_kind"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    submission_id: Mapped[uuid.UUID] = mapped_column(nullable=False, index=True)
    correlation_id: Mapped[uuid.UUID] = mapped_column(nullable=False, index=True)
    operation_kind: Mapped[str] = mapped_column(String(40), nullable=False, default="create_lead")
    payload_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    payload_json: Mapped[dict] = mapped_column(JsonType, nullable=False)
    state: Mapped[str] = mapped_column(String(30), nullable=False, default="pending", index=True)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    reconciliation_failure_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    manual_attempt_authorized: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    lease_token: Mapped[uuid.UUID | None] = mapped_column(index=True)
    lease_owner: Mapped[str | None] = mapped_column(String(160))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    quota_permit_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    quota_permit_lease_token: Mapped[uuid.UUID | None] = mapped_column()
    completed_lead_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("leads.id"))
    last_error_class: Mapped[str | None] = mapped_column(String(80))
    last_error_message: Mapped[str | None] = mapped_column(String(300))
    source_execution_reference: Mapped[str | None] = mapped_column(String(160))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class CRMWriteAttempt(Base):
    __tablename__ = "crm_write_attempts"
    __table_args__ = (UniqueConstraint("job_id", "attempt_number"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    job_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("crm_write_jobs.id"), index=True)
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    outcome: Mapped[str] = mapped_column(String(40), nullable=False, default="started")
    lease_token: Mapped[uuid.UUID | None] = mapped_column(index=True)
    status_code: Mapped[int | None] = mapped_column(Integer)
    error_class: Mapped[str | None] = mapped_column(String(80))
    retry_after_raw: Mapped[str | None] = mapped_column(String(160))
    retry_after_seconds: Mapped[int | None] = mapped_column(Integer)
    execution_reference: Mapped[str | None] = mapped_column(String(160))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RecoveryIncident(Base):
    __tablename__ = "recovery_incidents"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    event_key: Mapped[str] = mapped_column(String(200), unique=True, nullable=False)
    job_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("crm_write_jobs.id"), index=True)
    correlation_id: Mapped[uuid.UUID | None] = mapped_column(index=True)
    workflow_reference: Mapped[str | None] = mapped_column(String(160))
    execution_reference: Mapped[str | None] = mapped_column(String(160))
    failed_node: Mapped[str | None] = mapped_column(String(160))
    error_class: Mapped[str] = mapped_column(String(80), nullable=False)
    state: Mapped[str] = mapped_column(String(30), nullable=False, default="open")
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CRMFaultRun(Base):
    __tablename__ = "crm_fault_runs"

    run_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    submission_ids: Mapped[list] = mapped_column(JsonType, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    hold_delivery: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    request_limit: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    window_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=10)
    window_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    window_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
