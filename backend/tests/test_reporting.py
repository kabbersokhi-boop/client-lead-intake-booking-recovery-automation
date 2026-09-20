import uuid
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import func, select

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


def add_lead(db, *, created_at, service_type=None, needs_review=False):
    lead = Lead(
        id=uuid.uuid4(),
        submission_id=uuid.uuid4(),
        correlation_id=uuid.uuid4(),
        full_name="Synthetic Reporting Lead",
        email="reporting@example.test",
        phone=None,
        original_message="Synthetic reporting fixture",
        normalized_message="Synthetic reporting fixture",
        submission_fingerprint=uuid.uuid4().hex * 2,
        client_received_at=created_at - timedelta(minutes=10),
        service_type=service_type,
        ai_status="enriched" if service_type else "fallback_invalid",
        needs_review=needs_review,
        pipeline_stage="new_lead",
        created_at=created_at,
        updated_at=created_at,
    )
    db.add(lead)
    db.flush()
    return lead


def test_zero_state_report_is_authenticated_and_minimized(client):
    response = client.get("/api/reporting/management-summary?business_date=2026-09-20")
    assert response.status_code == 200
    assert response.json() == {
        "report_version": 1,
        "report_type": "hvac_management_snapshot",
        "report_key": "hvac-daily:2026-09-20",
        "business_date": "2026-09-20",
        "business_timezone": "America/Vancouver",
        "window_start_utc": "2026-09-20T07:00:00Z",
        "window_end_utc": "2026-09-21T07:00:00Z",
        "generated_at": response.json()["generated_at"],
        "leads_received": 0,
        "furnace_requests": 0,
        "air_conditioning_requests": 0,
        "other_or_unknown_requests": 0,
        "needs_review": 0,
        "appointments_booked": 0,
        "follow_ups_sent": 0,
        "open_recovery_incidents_at_generated_at": 0,
    }
    assert client.get(
        "/api/reporting/management-summary", headers={"X-CRM-Adapter-Key": "wrong"}
    ).status_code == 401


def test_non_empty_report_counts_independent_events_without_pii_or_internals(client, db):
    window_start, window_end = business_day_window_utc(date(2026, 9, 20))
    furnace = add_lead(
        db,
        created_at=window_start,
        service_type="furnace_service",
        needs_review=True,
    )
    air_conditioning = add_lead(
        db,
        created_at=window_start + timedelta(hours=1),
        service_type="air_conditioning_service",
    )
    plumbing = add_lead(
        db,
        created_at=window_end - timedelta(microseconds=1),
        service_type="plumbing_service",
    )
    add_lead(db, created_at=window_start + timedelta(hours=2), service_type=None)
    add_lead(
        db,
        created_at=window_start - timedelta(microseconds=1),
        service_type="furnace_service",
    )
    add_lead(db, created_at=window_end, service_type="air_conditioning_service")

    db.add_all(
        [
            Appointment(
                id=uuid.uuid4(),
                booking_request_id=uuid.uuid4(),
                lead_id=furnace.id,
                correlation_id=furnace.correlation_id,
                appointment_at=window_end + timedelta(days=2),
                business_timezone="America/Vancouver",
                booking_fingerprint="a" * 64,
                status="booked",
                created_at=window_start,
                updated_at=window_start,
            ),
            FollowUp(
                id=uuid.uuid4(),
                lead_id=air_conditioning.id,
                correlation_id=air_conditioning.correlation_id,
                status="sent",
                due_at=window_start,
                sent_at=window_end - timedelta(microseconds=1),
                created_at=window_start,
                updated_at=window_start,
            ),
            FollowUp(
                id=uuid.uuid4(),
                lead_id=plumbing.id,
                correlation_id=plumbing.correlation_id,
                status="cancelled",
                due_at=window_start,
                sent_at=None,
                cancelled_at=window_start,
                created_at=window_start,
                updated_at=window_start,
            ),
            RecoveryIncident(
                id=uuid.uuid4(),
                event_key="reporting-open-incident",
                error_class="controlled_fixture",
                state="open",
                created_at=window_start - timedelta(days=30),
            ),
            RecoveryIncident(
                id=uuid.uuid4(),
                event_key="reporting-resolved-incident",
                error_class="controlled_fixture",
                state="resolved",
                resolved_at=window_start,
                created_at=window_start,
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
    before = {
        model.__tablename__: db.scalar(select(func.count()).select_from(model))
        for model in durable_models
    }

    first = client.get("/api/reporting/management-summary?business_date=2026-09-20")
    second = client.get("/api/reporting/management-summary?business_date=2026-09-20")
    assert first.status_code == second.status_code == 200
    report = first.json()
    assert {
        "leads_received": report["leads_received"],
        "furnace_requests": report["furnace_requests"],
        "air_conditioning_requests": report["air_conditioning_requests"],
        "other_or_unknown_requests": report["other_or_unknown_requests"],
        "needs_review": report["needs_review"],
        "appointments_booked": report["appointments_booked"],
        "follow_ups_sent": report["follow_ups_sent"],
        "open_recovery_incidents_at_generated_at": report[
            "open_recovery_incidents_at_generated_at"
        ],
    } == {
        "leads_received": 4,
        "furnace_requests": 1,
        "air_conditioning_requests": 1,
        "other_or_unknown_requests": 2,
        "needs_review": 1,
        "appointments_booked": 1,
        "follow_ups_sent": 1,
        "open_recovery_incidents_at_generated_at": 1,
    }
    assert report["furnace_requests"] + report["air_conditioning_requests"] + report[
        "other_or_unknown_requests"
    ] == report["leads_received"]
    stable_fields = set(report) - {"generated_at"}
    assert {key: first.json()[key] for key in stable_fields} == {
        key: second.json()[key] for key in stable_fields
    }
    forbidden = {
        "full_name",
        "email",
        "phone",
        "original_message",
        "normalized_message",
        "summary",
        "provider_metadata",
        "payload_json",
        "lease_token",
        "authorization",
        "api_key",
        "webhook_url",
    }
    assert not forbidden.intersection(report)
    assert "Synthetic Reporting Lead" not in first.text
    assert "reporting@example.test" not in first.text
    after = {
        model.__tablename__: db.scalar(select(func.count()).select_from(model))
        for model in durable_models
    }
    assert after == before


def test_vancouver_day_windows_follow_both_dst_transitions():
    spring_start, spring_end = business_day_window_utc(date(2026, 3, 8))
    assert spring_start == datetime(2026, 3, 8, 8, tzinfo=timezone.utc)
    assert spring_end == datetime(2026, 3, 9, 7, tzinfo=timezone.utc)
    assert spring_end - spring_start == timedelta(hours=23)

    fall_start, fall_end = business_day_window_utc(date(2025, 11, 2))
    assert fall_start == datetime(2025, 11, 2, 7, tzinfo=timezone.utc)
    assert fall_end == datetime(2025, 11, 3, 8, tzinfo=timezone.utc)
    assert fall_end - fall_start == timedelta(hours=25)


def test_default_report_date_uses_vancouver_date(db):
    report = ReportingService().management_summary(
        db, generated_at=datetime(2026, 9, 20, 6, 59, tzinfo=timezone.utc)
    )
    assert report.business_date == date(2026, 9, 19)
    assert report.report_key == "hvac-daily:2026-09-19"
