import os
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from test_leads import payload

from app.config import settings
from app.models import Appointment, FollowUp, Lead
from app.providers.crm import DevelopmentCRMProvider
from app.schemas.lead import CRMLeadCreate
from app.schemas.lifecycle import BookingCreate
from app.services.lifecycle_service import LifecycleService

POSTGRES_URL = os.getenv("TEST_POSTGRES_URL")
pytestmark = pytest.mark.skipif(not POSTGRES_URL, reason="requires disposable PostgreSQL")


class CoordinatedEmailGateway:
    def __init__(self) -> None:
        self.entered = threading.Event()
        self.release = threading.Event()
        self.messages: list[dict[str, str]] = []
        self._lock = threading.Lock()

    def send(self, recipient: str, subject: str, body: str) -> None:
        self.entered.set()
        if not self.release.wait(timeout=5):
            raise TimeoutError("test email gateway was not released")
        with self._lock:
            self.messages.append({"recipient": recipient, "subject": subject, "body": body})


@pytest.fixture(scope="module")
def postgres_sessions():
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    config.attributes["database_url"] = POSTGRES_URL
    command.downgrade(config, "base")
    command.upgrade(config, "head")
    engine = create_engine(POSTGRES_URL)
    yield sessionmaker(autocommit=False, autoflush=False, bind=engine)
    engine.dispose()


def create_due_lead(session_factory):
    with session_factory() as session:
        request = CRMLeadCreate.model_validate(payload())
        created = DevelopmentCRMProvider().create_lead(session, request)
        created.follow_up.due_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        session.commit()
        return created.lead.id, created.follow_up.id, created.lead.correlation_id


def booking_request(correlation_id: uuid.UUID) -> BookingCreate:
    return BookingCreate(
        booking_request_id=uuid.uuid4(),
        correlation_id=correlation_id,
        appointment_local=(
            datetime.now(ZoneInfo(settings.business_timezone)) + timedelta(days=2)
        ).replace(tzinfo=None, second=0, microsecond=0),
        business_timezone=settings.business_timezone,
    )


def test_booking_lock_first_prevents_later_dispatch_email(postgres_sessions):
    lead_id, follow_up_id, correlation_id = create_due_lead(postgres_sessions)
    gateway = CoordinatedEmailGateway()
    lead_locked = threading.Event()
    continue_booking = threading.Event()

    def book_while_holding_lead_lock():
        with postgres_sessions() as session:
            session.scalar(select(Lead).where(Lead.id == lead_id).with_for_update())
            lead_locked.set()
            assert continue_booking.wait(timeout=5)
            return LifecycleService(gateway).create_booking(
                session, booking_request(correlation_id)
            )

    def dispatch():
        with postgres_sessions() as session:
            return LifecycleService(gateway).dispatch_follow_up(session, follow_up_id)

    with ThreadPoolExecutor(max_workers=2) as executor:
        booking_future = executor.submit(book_while_holding_lead_lock)
        assert lead_locked.wait(timeout=5)
        dispatch_future = executor.submit(dispatch)
        email_started_before_booking = gateway.entered.wait(timeout=0.5)
        continue_booking.set()
        gateway.release.set()
        booking_result = booking_future.result(timeout=8)
        dispatch_result = dispatch_future.result(timeout=8)

    assert email_started_before_booking is False
    assert booking_result.created is True
    assert dispatch_result.state == "cancelled"
    assert gateway.messages == []


def test_dispatch_lock_first_sends_once_then_booking_wins_pipeline(postgres_sessions):
    lead_id, follow_up_id, correlation_id = create_due_lead(postgres_sessions)
    gateway = CoordinatedEmailGateway()

    def dispatch():
        with postgres_sessions() as session:
            return LifecycleService(gateway).dispatch_follow_up(session, follow_up_id)

    def book():
        with postgres_sessions() as session:
            return LifecycleService(gateway).create_booking(
                session, booking_request(correlation_id)
            )

    with ThreadPoolExecutor(max_workers=2) as executor:
        dispatch_future = executor.submit(dispatch)
        assert gateway.entered.wait(timeout=5)
        booking_future = executor.submit(book)
        time.sleep(0.25)
        assert booking_future.done() is False
        gateway.release.set()
        assert dispatch_future.result(timeout=8).state == "sent"
        assert booking_future.result(timeout=8).created is True

    with postgres_sessions() as session:
        assert session.get(Lead, lead_id).pipeline_stage == "appointment_booked"
        assert session.get(FollowUp, follow_up_id).status == "sent"
        assert len(gateway.messages) == 1


def test_two_dispatchers_send_one_email(postgres_sessions):
    _, follow_up_id, _ = create_due_lead(postgres_sessions)
    gateway = CoordinatedEmailGateway()

    def dispatch():
        with postgres_sessions() as session:
            return LifecycleService(gateway).dispatch_follow_up(session, follow_up_id)

    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(dispatch)
        assert gateway.entered.wait(timeout=5)
        second = executor.submit(dispatch)
        time.sleep(0.25)
        assert second.done() is False
        gateway.release.set()
        assert first.result(timeout=8).state == "sent"
        assert second.result(timeout=8).state == "sent"

    assert len(gateway.messages) == 1


def test_two_confirmation_requests_send_one_email(postgres_sessions):
    _, _, correlation_id = create_due_lead(postgres_sessions)
    with postgres_sessions() as session:
        appointment = LifecycleService(CoordinatedEmailGateway()).create_booking(
            session, booking_request(correlation_id)
        ).appointment
        appointment_id = appointment.id
    gateway = CoordinatedEmailGateway()

    def confirm():
        with postgres_sessions() as session:
            return LifecycleService(gateway).send_booking_confirmation(session, appointment_id)

    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(confirm)
        assert gateway.entered.wait(timeout=5)
        second = executor.submit(confirm)
        time.sleep(0.25)
        assert second.done() is False
        gateway.release.set()
        assert first.result(timeout=8).state == "sent"
        assert second.result(timeout=8).state == "already_sent"

    with postgres_sessions() as session:
        assert session.get(Appointment, appointment_id).confirmation_sent_at is not None
    assert len(gateway.messages) == 1
