import uuid
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import delete, func, select
from test_leads import payload

from app.config import settings
from app.models import Appointment, AuditEvent, FollowUp, Lead
from app.schemas.lifecycle import BookingCreate
from app.services.lifecycle_service import LifecycleService


class RecordingEmailGateway:
    def __init__(self):
        self.messages = []

    def send(self, recipient, subject, plain_text, html_text):
        self.messages.append(
            {
                "recipient": recipient,
                "subject": subject,
                "plain_text": plain_text,
                "html_text": html_text,
            }
        )


def booking_for(correlation_id):
    return BookingCreate(
        booking_request_id=uuid.uuid4(),
        correlation_id=correlation_id,
        appointment_local=(
            datetime.now(ZoneInfo(settings.business_timezone)) + timedelta(days=2)
        ).replace(tzinfo=None, second=0, microsecond=0),
        business_timezone=settings.business_timezone,
    )


def row_counts(db):
    return {
        model.__tablename__: db.scalar(select(func.count()).select_from(model))
        for model in [Lead, FollowUp, Appointment, AuditEvent]
    }


def test_invalid_http_input_returns_safe_422_not_500(client):
    response = client.post("/api/crm/leads", json=payload(email=123))

    assert response.status_code == 422
    body = response.json()
    assert "detail" in body
    assert "AttributeError" not in str(body)


def test_punctuation_only_phone_returns_safe_422(client):
    response = client.post("/api/crm/leads", json=payload(email=None, phone="+++++++"))
    assert response.status_code == 422


def test_crm_contract_replay_and_conflict_responses(client):
    request = payload()
    created = client.post("/api/crm/leads", json=request)
    assert created.status_code == 201
    assert created.json()["intake_state"] == "created"

    replayed = client.post("/api/crm/leads", json=request)
    assert replayed.status_code == 200
    assert replayed.json()["intake_state"] == "replayed"
    assert replayed.json()["crm_lead_id"] == created.json()["crm_lead_id"]

    changed = {
        **request,
        "original_message": "Different message",
        "normalized_message": "Different message",
    }
    conflict = client.post("/api/crm/leads", json=changed)
    assert conflict.status_code == 409
    assert "different lead data" in conflict.json()["detail"]


def test_lifecycle_write_endpoints_require_adapter_auth(client):
    identifier = "00000000-0000-4000-8000-000000000000"
    for method, path, request_body in [
        ("get", "/api/crm/follow-ups/due", None),
        ("post", f"/api/crm/follow-ups/{identifier}/dispatch", None),
        (
            "post",
            "/api/crm/bookings",
            {
                "booking_request_id": identifier,
                "correlation_id": identifier,
                "appointment_local": "2099-01-01T10:00",
                "business_timezone": "America/Vancouver",
            },
        ),
        ("post", f"/api/crm/appointments/{identifier}/confirmation", None),
    ]:
        response = client.request(
            method.upper(),
            path,
            headers={"X-CRM-Adapter-Key": "wrong-key"},
            json=request_body,
        )
        assert response.status_code == 401


def test_intake_replay_after_follow_up_returns_persisted_state_without_side_effects(client, db):
    request = payload()
    assert client.post("/api/crm/leads", json=request).status_code == 201
    lead = db.scalar(select(Lead).where(Lead.submission_id == uuid.UUID(request["submission_id"])))
    follow_up = db.scalar(select(FollowUp).where(FollowUp.lead_id == lead.id))
    follow_up.due_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    db.commit()
    gateway = RecordingEmailGateway()
    LifecycleService(gateway).dispatch_follow_up(db, follow_up.id)
    before = row_counts(db)
    replay_payload = {
        **request,
        "enrichment": None,
        "ai_status": "fallback_invalid",
        "needs_review": True,
        "provider_metadata": {
            "provider": "nvidia_nim",
            "outcome_class": "invalid_output",
            "error_code": "invalid_model_output",
        },
    }

    replay = client.post("/api/crm/leads", json=replay_payload)

    assert replay.status_code == 200
    assert replay.json()["intake_state"] == "replayed"
    assert replay.json()["ai_status"] == "enriched"
    assert replay.json()["pipeline_stage"] == "contacted"
    assert replay.json()["follow_up_status"] == "sent"
    assert row_counts(db) == before
    assert len(gateway.messages) == 1


def test_intake_replay_after_booking_preserves_appointment_and_cancelled_follow_up(client, db):
    request = payload()
    assert client.post("/api/crm/leads", json=request).status_code == 201
    lead = db.scalar(select(Lead).where(Lead.submission_id == uuid.UUID(request["submission_id"])))
    LifecycleService(RecordingEmailGateway()).create_booking(db, booking_for(lead.correlation_id))
    before = row_counts(db)

    replay = client.post("/api/crm/leads", json=request)

    assert replay.status_code == 200
    assert replay.json()["pipeline_stage"] == "appointment_booked"
    assert replay.json()["follow_up_status"] == "cancelled"
    assert row_counts(db) == before


def test_legacy_intake_replay_does_not_backfill_or_schedule_a_follow_up(client, db):
    request = payload()
    assert client.post("/api/crm/leads", json=request).status_code == 201
    lead = db.scalar(select(Lead).where(Lead.submission_id == uuid.UUID(request["submission_id"])))
    db.execute(delete(FollowUp).where(FollowUp.lead_id == lead.id))
    db.commit()
    before = row_counts(db)

    replay = client.post("/api/crm/leads", json=request)

    assert replay.status_code == 200
    assert replay.json()["follow_up_status"] is None
    assert replay.json()["follow_up_due_at"] is None
    assert row_counts(db) == before


def test_booking_api_rejects_datetime_seconds_outside_minute_contract(client):
    identifier = "00000000-0000-4000-8000-000000000000"
    response = client.post(
        "/api/crm/bookings",
        json={
            "booking_request_id": identifier,
            "correlation_id": identifier,
            "appointment_local": "2099-01-01T10:00:00",
            "business_timezone": "America/Vancouver",
        },
    )

    assert response.status_code == 422


def test_phone_only_booking_confirmation_is_bound_and_explicitly_skipped(client, db):
    request = payload(email=None)
    created = client.post("/api/crm/leads", json=request)
    assert created.status_code == 201
    appointment_local = (
        datetime.now(ZoneInfo(settings.business_timezone)) + timedelta(days=2)
    ).strftime("%Y-%m-%dT%H:%M")
    booking = client.post(
        "/api/crm/bookings",
        json={
            "booking_request_id": str(uuid.uuid4()),
            "correlation_id": request["correlation_id"],
            "appointment_local": appointment_local,
            "business_timezone": settings.business_timezone,
        },
    )
    appointment_id = booking.json()["appointment_id"]

    confirmation = client.post(f"/api/crm/appointments/{appointment_id}/confirmation")

    assert confirmation.status_code == 200
    assert confirmation.json() == {
        "appointment_id": appointment_id,
        "correlation_id": request["correlation_id"],
        "state": "skipped_no_email",
        "pipeline_stage": "appointment_booked",
        "sent_at": None,
    }
