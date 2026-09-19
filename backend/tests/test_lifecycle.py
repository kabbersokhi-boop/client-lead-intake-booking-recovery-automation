import uuid
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import select
from test_leads import payload

from app.api.routes import get_trace
from app.config import settings
from app.models import Appointment, AuditEvent, FollowUp, Lead
from app.providers.crm import DevelopmentCRMProvider
from app.schemas.lead import CRMLeadCreate
from app.schemas.lifecycle import BookingCreate
from app.services.lifecycle_service import BookingConflictError, LifecycleService


class RecordingEmailGateway:
    def __init__(self):
        self.messages = []

    def send(self, recipient, subject, body):
        self.messages.append({"recipient": recipient, "subject": subject, "body": body})


def create_lead(db, **changes):
    request = CRMLeadCreate.model_validate(payload(**changes))
    return DevelopmentCRMProvider().create_lead(db, request)


def booking_for(lead, **changes):
    local_future = datetime.now(ZoneInfo(settings.business_timezone)).replace(
        second=0, microsecond=0
    ) + timedelta(days=2)
    value = {
        "booking_request_id": uuid.uuid4(),
        "correlation_id": lead.correlation_id,
        "appointment_local": local_future.replace(tzinfo=None),
        "business_timezone": settings.business_timezone,
    }
    value.update(changes)
    return BookingCreate.model_validate(value)


def test_due_follow_up_sends_once_and_moves_pipeline_to_contacted(db):
    created = create_lead(db)
    created.follow_up.due_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    db.commit()
    gateway = RecordingEmailGateway()
    service = LifecycleService(gateway)

    first = service.dispatch_follow_up(db, created.follow_up.id)
    second = service.dispatch_follow_up(db, created.follow_up.id)

    assert first.state == "sent"
    assert second.state == "sent"
    assert len(gateway.messages) == 1
    assert db.get(FollowUp, created.follow_up.id).sent_at is not None
    assert db.get(Lead, created.lead.id).pipeline_stage == "contacted"
    event_types = [event.event_type for event in db.scalars(select(AuditEvent))]
    assert "follow_up.sent" in event_types
    assert "pipeline.stage_changed" in event_types


def test_follow_up_cannot_send_before_due(db):
    created = create_lead(db)
    gateway = RecordingEmailGateway()

    result = LifecycleService(gateway).dispatch_follow_up(db, created.follow_up.id)

    assert result.state == "not_due"
    assert gateway.messages == []
    assert created.lead.pipeline_stage == "new_lead"


def test_booking_transaction_cancels_pending_follow_up_and_replay_is_idempotent(db):
    created = create_lead(db)
    service = LifecycleService(RecordingEmailGateway())
    booking = booking_for(created.lead)

    first = service.create_booking(db, booking)
    replay = service.create_booking(db, booking)

    assert first.created is True
    assert replay.created is False
    assert first.appointment.id == replay.appointment.id
    assert len(list(db.scalars(select(Appointment)))) == 1
    assert db.get(Lead, created.lead.id).pipeline_stage == "appointment_booked"
    assert db.get(FollowUp, created.follow_up.id).status == "cancelled"
    assert db.get(FollowUp, created.follow_up.id).cancelled_at is not None
    event_types = [event.event_type for event in db.scalars(select(AuditEvent))]
    assert "appointment.booked" in event_types
    assert "follow_up.cancelled" in event_types


def test_different_second_booking_is_a_controlled_conflict(db):
    created = create_lead(db)
    service = LifecycleService(RecordingEmailGateway())
    service.create_booking(db, booking_for(created.lead))

    with pytest.raises(BookingConflictError):
        service.create_booking(db, booking_for(created.lead))

    assert len(list(db.scalars(select(Appointment)))) == 1


def test_booking_confirmation_sends_once_on_replay(db):
    created = create_lead(db)
    gateway = RecordingEmailGateway()
    service = LifecycleService(gateway)
    result = service.create_booking(db, booking_for(created.lead))

    first = service.send_booking_confirmation(db, result.appointment.id)
    replay = service.send_booking_confirmation(db, result.appointment.id)

    assert first.state == "sent"
    assert replay.state == "already_sent"
    assert len(gateway.messages) == 1
    assert db.get(Appointment, result.appointment.id).confirmation_sent_at is not None


def test_cancelled_follow_up_never_sends_after_due(db):
    created = create_lead(db)
    gateway = RecordingEmailGateway()
    service = LifecycleService(gateway)
    service.create_booking(db, booking_for(created.lead))
    created.follow_up.due_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    db.commit()

    result = service.dispatch_follow_up(db, created.follow_up.id)

    assert result.state == "cancelled"
    assert gateway.messages == []
    assert db.get(Lead, created.lead.id).pipeline_stage == "appointment_booked"


def test_trace_contains_follow_up_appointment_and_lifecycle_audits(db):
    created = create_lead(db)
    service = LifecycleService(RecordingEmailGateway())
    booked = service.create_booking(db, booking_for(created.lead))
    service.send_booking_confirmation(db, booked.appointment.id)

    trace = get_trace(created.lead.correlation_id, db)

    assert trace.lead.pipeline_stage == "appointment_booked"
    assert trace.follow_ups[0].status == "cancelled"
    assert trace.appointments[0].status == "booked"
    assert trace.appointments[0].confirmation_sent_at is not None
    assert "booking_confirmation.sent" in [event.event_type for event in trace.audit_events]
