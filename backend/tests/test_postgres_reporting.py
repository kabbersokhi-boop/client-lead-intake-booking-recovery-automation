import os
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

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
from app.services.reporting_service import ReportingService, business_day_window_utc

POSTGRES_URL = os.getenv("TEST_POSTGRES_URL")
pytestmark = pytest.mark.skipif(not POSTGRES_URL, reason="requires disposable PostgreSQL")


def postgres_lead(*, created_at, service_type, needs_review=False):
    return Lead(
        id=uuid.uuid4(),
        submission_id=uuid.uuid4(),
        correlation_id=uuid.uuid4(),
        full_name="Synthetic PostgreSQL Reporting Lead",
        email=None,
        phone="+1 604 555 0100",
        original_message="Synthetic PostgreSQL fixture",
        normalized_message="Synthetic PostgreSQL fixture",
        submission_fingerprint=uuid.uuid4().hex * 2,
        client_received_at=created_at - timedelta(days=10),
        service_type=service_type,
        ai_status="enriched" if service_type else "fallback_unavailable",
        needs_review=needs_review,
        pipeline_stage="new_lead",
        created_at=created_at,
        updated_at=created_at,
    )


def test_postgres_reporting_boundaries_and_independent_aggregates():
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    config.attributes["database_url"] = POSTGRES_URL
    command.downgrade(config, "base")
    command.upgrade(config, "head")
    engine = create_engine(POSTGRES_URL)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    window_start, window_end = business_day_window_utc(date(2026, 3, 8))

    with sessions() as db:
        before = postgres_lead(
            created_at=window_start - timedelta(microseconds=1),
            service_type="furnace_service",
        )
        furnace = postgres_lead(
            created_at=window_start,
            service_type="furnace_service",
            needs_review=True,
        )
        air_conditioning = postgres_lead(
            created_at=window_start + timedelta(hours=22),
            service_type="air_conditioning_service",
        )
        unknown = postgres_lead(
            created_at=window_end - timedelta(microseconds=1), service_type=None
        )
        after = postgres_lead(
            created_at=window_end, service_type="air_conditioning_service"
        )
        db.add_all([before, furnace, air_conditioning, unknown, after])
        db.flush()
        db.add_all(
            [
                FollowUp(
                    id=uuid.uuid4(),
                    lead_id=furnace.id,
                    correlation_id=furnace.correlation_id,
                    status="sent",
                    due_at=window_start,
                    sent_at=window_start,
                    created_at=window_start,
                    updated_at=window_start,
                ),
                Appointment(
                    id=uuid.uuid4(),
                    booking_request_id=uuid.uuid4(),
                    lead_id=air_conditioning.id,
                    correlation_id=air_conditioning.correlation_id,
                    appointment_at=window_end + timedelta(days=1),
                    business_timezone="America/Vancouver",
                    booking_fingerprint="b" * 64,
                    status="booked",
                    created_at=window_end - timedelta(microseconds=1),
                    updated_at=window_end - timedelta(microseconds=1),
                ),
                RecoveryIncident(
                    id=uuid.uuid4(),
                    event_key="postgres-reporting-open",
                    error_class="controlled_fixture",
                    state="open",
                    created_at=window_start - timedelta(days=30),
                ),
            ]
        )
        db.commit()
        durable_models = [
            Lead,
            Appointment,
            FollowUp,
            AuditEvent,
            CRMWriteJob,
            CRMWriteAttempt,
            RecoveryIncident,
            CRMFaultRun,
        ]
        before_counts = tuple(db.query(model).count() for model in durable_models)
        report = ReportingService().management_summary(
            db,
            business_date=date(2026, 3, 8),
            generated_at=datetime(2026, 3, 9, 8, tzinfo=timezone.utc),
        )
        after_counts = tuple(db.query(model).count() for model in durable_models)

    engine.dispose()
    assert report.window_end_utc - report.window_start_utc == timedelta(hours=23)
    assert report.leads_received == 3
    assert report.furnace_requests == 1
    assert report.air_conditioning_requests == 1
    assert report.other_or_unknown_requests == 1
    assert report.needs_review == 1
    assert report.appointments_booked == 1
    assert report.follow_ups_sent == 1
    assert report.open_recovery_incidents_at_generated_at == 1
    assert before_counts == after_counts
