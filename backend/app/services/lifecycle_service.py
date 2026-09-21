import hashlib
import html
import json
import smtplib
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from email.message import EmailMessage
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Appointment, AuditEvent, FollowUp, Lead
from app.schemas.lifecycle import BookingCreate


class BookingConflictError(Exception):
    """A booking request conflicts with existing durable state."""


class BookingValidationError(Exception):
    """A booking uses an unsupported timezone or invalid local time."""


class EmailDeliveryError(Exception):
    """The local development email sink could not accept a message."""


@dataclass(frozen=True)
class BookingResult:
    appointment: Appointment
    follow_up: FollowUp | None
    created: bool


@dataclass(frozen=True)
class DispatchResult:
    state: str
    pipeline_stage: str
    sent_at: datetime | None


class DevelopmentEmailGateway:
    @staticmethod
    def _safe_header(value: str) -> str:
        if "\r" in value or "\n" in value:
            raise EmailDeliveryError("Email header values must not contain line breaks.")
        return value

    @classmethod
    def build_message(
        cls, recipient: str, subject: str, plain_text: str, html_text: str
    ) -> EmailMessage:
        message = EmailMessage()
        message["From"] = cls._safe_header(settings.development_email_from)
        message["To"] = cls._safe_header(recipient)
        message["Subject"] = cls._safe_header(subject)
        message.set_content(plain_text)
        message.add_alternative(html_text, subtype="html")
        return message

    def send(
        self, recipient: str, subject: str, plain_text: str, html_text: str
    ) -> None:
        message = self.build_message(recipient, subject, plain_text, html_text)
        try:
            with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=5) as smtp:
                smtp.send_message(message)
        except (OSError, smtplib.SMTPException) as error:
            raise EmailDeliveryError("The local development email sink is unavailable.") from error


def _service_label(value: str | None) -> str | None:
    return value.replace("_", " ").title() if value else None


def _detail_rows(lead: Lead, appointment_text: str | None = None) -> list[tuple[str, str]]:
    rows = []
    if service := _service_label(lead.service_type):
        rows.append(("Service", service))
    if lead.location:
        rows.append(("Location", lead.location))
    if lead.preferred_time:
        rows.append(("Preferred time", lead.preferred_time))
    if appointment_text:
        rows.append(("Appointment", appointment_text))
    return rows


def _plain_details(rows: list[tuple[str, str]]) -> str:
    if not rows:
        return ""
    return "\n\nRequest details\n" + "\n".join(f"{label}: {value}" for label, value in rows)


def _html_message(
    heading: str,
    greeting_name: str,
    paragraphs: list[str],
    rows: list[tuple[str, str]],
) -> str:
    escaped_rows = "".join(
        "<tr>"
        "<th style=\"padding:6px 12px 6px 0;text-align:left;vertical-align:top\">"
        f"{html.escape(label)}</th>"
        f"<td style=\"padding:6px 0\">{html.escape(value)}</td>"
        "</tr>"
        for label, value in rows
    )
    details = (
        "<div style=\"margin:20px 0;padding:14px 18px;border:1px solid #d9e2ec;"
        "border-radius:8px;background:#f7fafc\"><table role=\"presentation\">"
        f"{escaped_rows}</table></div>"
        if escaped_rows
        else ""
    )
    body = "".join(f"<p>{html.escape(paragraph)}</p>" for paragraph in paragraphs)
    return (
        "<!doctype html><html><body style=\"font-family:Arial,sans-serif;color:#243b53;"
        "line-height:1.5;margin:0;padding:24px\">"
        f"<h1 style=\"font-size:22px;margin:0 0 18px\">{html.escape(heading)}</h1>"
        f"<p>Hello {html.escape(greeting_name)},</p>{body}{details}"
        "<p style=\"margin-top:24px;padding-top:16px;border-top:1px solid #d9e2ec;"
        "font-size:13px;color:#52667a\"><strong>Development demonstration:</strong> "
        "This message was sent to a local test inbox. It does not reserve a technician, "
        "confirm commercial service, or reserve an external calendar.</p>"
        "<p>Regards,<br>Local automation demonstration</p></body></html>"
    )


def booking_fingerprint(payload: BookingCreate) -> str:
    encoded = json.dumps(
        {
            "correlation_id": str(payload.correlation_id),
            "appointment_local": payload.appointment_local.isoformat(timespec="minutes"),
            "business_timezone": payload.business_timezone,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


class LifecycleService:
    def __init__(self, email_gateway: DevelopmentEmailGateway | None = None) -> None:
        self.email_gateway = email_gateway or DevelopmentEmailGateway()

    @staticmethod
    def due_follow_ups(db: Session, limit: int) -> list[FollowUp]:
        now = datetime.now(timezone.utc)
        statement = (
            select(FollowUp)
            .where(FollowUp.status == "pending", FollowUp.due_at <= now)
            .order_by(FollowUp.due_at.asc())
            .limit(limit)
        )
        return list(db.scalars(statement))

    def dispatch_follow_up(self, db: Session, follow_up_id: uuid.UUID) -> DispatchResult:
        lead_id = db.scalar(select(FollowUp.lead_id).where(FollowUp.id == follow_up_id))
        if not lead_id:
            raise LookupError("Follow-up not found")
        lead = db.scalar(select(Lead).where(Lead.id == lead_id).with_for_update())
        follow_up = db.scalar(
            select(FollowUp)
            .where(FollowUp.id == follow_up_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if not follow_up:
            raise LookupError("Follow-up not found")
        if follow_up.status != "pending":
            return DispatchResult(follow_up.status, lead.pipeline_stage, follow_up.sent_at)
        due_at = follow_up.due_at
        if due_at.tzinfo is None:
            due_at = due_at.replace(tzinfo=timezone.utc)
        if due_at > datetime.now(timezone.utc):
            return DispatchResult("not_due", lead.pipeline_stage, None)
        if not lead.email:
            raise BookingValidationError("An email follow-up requires a lead email address.")

        service_label = _service_label(lead.service_type)
        subject = (
            f"Checking in about your {service_label.lower()} request"
            if service_label
            else "Checking in about your service request"
        )
        details = _detail_rows(lead)
        paragraphs = [
            "Thank you for getting in touch about your home comfort service request.",
            "We have kept the details you shared with this request. To continue in this "
            "demonstration, use the booking option shown with the saved request.",
        ]
        plain_text = (
            f"Hello {lead.full_name},\n\n" + "\n\n".join(paragraphs)
            + f"{_plain_details(details)}\n\n"
            "Development demonstration: This message was sent to a local test inbox. "
            "It does not reserve a technician, confirm commercial service, or reserve an "
            "external calendar.\n\nRegards,\nLocal automation demonstration"
        )
        self.email_gateway.send(
            lead.email,
            subject,
            plain_text,
            _html_message("Service request follow-up", lead.full_name, paragraphs, details),
        )
        sent_at = datetime.now(timezone.utc)
        follow_up.status = "sent"
        follow_up.sent_at = sent_at
        previous_stage = lead.pipeline_stage
        if previous_stage == "new_lead":
            lead.pipeline_stage = "contacted"
        db.add_all(
            [
                AuditEvent(
                    correlation_id=lead.correlation_id,
                    lead_id=lead.id,
                    event_type="follow_up.sent",
                    status="success",
                    metadata_json={
                        "follow_up_id": str(follow_up.id),
                        "sent_at": sent_at.isoformat(),
                    },
                ),
                AuditEvent(
                    correlation_id=lead.correlation_id,
                    lead_id=lead.id,
                    event_type="pipeline.stage_changed",
                    status="success",
                    metadata_json={"from": previous_stage, "to": lead.pipeline_stage},
                ),
            ]
        )
        db.commit()
        return DispatchResult("sent", lead.pipeline_stage, sent_at)

    def create_booking(self, db: Session, payload: BookingCreate) -> BookingResult:
        fingerprint = booking_fingerprint(payload)
        existing = db.scalar(
            select(Appointment).where(Appointment.booking_request_id == payload.booking_request_id)
        )
        if existing:
            return self._existing_booking(db, existing, fingerprint)
        if payload.business_timezone != settings.business_timezone:
            raise BookingValidationError(
                f"business_timezone must be {settings.business_timezone}."
            )
        try:
            business_zone = ZoneInfo(settings.business_timezone)
        except ZoneInfoNotFoundError as error:
            raise BookingValidationError(
                "The configured business timezone is unavailable."
            ) from error

        local_time = payload.appointment_local
        appointment_at = local_time.replace(tzinfo=business_zone).astimezone(timezone.utc)
        round_trip = appointment_at.astimezone(business_zone).replace(tzinfo=None)
        if round_trip != local_time:
            raise BookingValidationError("The selected business-local time does not exist.")
        if appointment_at <= datetime.now(timezone.utc):
            raise BookingValidationError("The appointment must be in the future.")

        lead = db.scalar(
            select(Lead).where(Lead.correlation_id == payload.correlation_id).with_for_update()
        )
        if not lead:
            raise LookupError("Lead not found")
        replay_after_lock = db.scalar(
            select(Appointment).where(Appointment.booking_request_id == payload.booking_request_id)
        )
        if replay_after_lock:
            return self._existing_booking(db, replay_after_lock, fingerprint)
        existing_for_lead = db.scalar(select(Appointment).where(Appointment.lead_id == lead.id))
        if existing_for_lead:
            raise BookingConflictError("The lead already has an active appointment.")

        appointment = Appointment(
            booking_request_id=payload.booking_request_id,
            lead_id=lead.id,
            correlation_id=lead.correlation_id,
            appointment_at=appointment_at,
            business_timezone=settings.business_timezone,
            booking_fingerprint=fingerprint,
        )
        db.add(appointment)
        try:
            db.flush()
        except IntegrityError as error:
            db.rollback()
            replay = db.scalar(
                select(Appointment).where(
                    Appointment.booking_request_id == payload.booking_request_id
                )
            )
            if replay:
                return self._existing_booking(db, replay, fingerprint)
            raise BookingConflictError("The lead already has an active appointment.") from error

        follow_up = db.scalar(
            select(FollowUp).where(FollowUp.lead_id == lead.id).with_for_update()
        )
        previous_stage = lead.pipeline_stage
        lead.pipeline_stage = "appointment_booked"
        now = datetime.now(timezone.utc)
        events = [
            AuditEvent(
                correlation_id=lead.correlation_id,
                lead_id=lead.id,
                event_type="appointment.booked",
                status="success",
                metadata_json={
                    "appointment_id": str(appointment.id),
                    "booking_request_id": str(payload.booking_request_id),
                    "appointment_at": appointment_at.isoformat(),
                    "business_timezone": settings.business_timezone,
                },
            ),
            AuditEvent(
                correlation_id=lead.correlation_id,
                lead_id=lead.id,
                event_type="pipeline.stage_changed",
                status="success",
                metadata_json={"from": previous_stage, "to": "appointment_booked"},
            ),
        ]
        if follow_up and follow_up.status == "pending":
            follow_up.status = "cancelled"
            follow_up.cancelled_at = now
            events.append(
                AuditEvent(
                    correlation_id=lead.correlation_id,
                    lead_id=lead.id,
                    event_type="follow_up.cancelled",
                    status="success",
                    metadata_json={
                        "follow_up_id": str(follow_up.id),
                        "cancelled_at": now.isoformat(),
                        "reason": "appointment_booked",
                    },
                )
            )
        db.add_all(events)
        db.commit()
        db.refresh(appointment)
        if follow_up:
            db.refresh(follow_up)
        return BookingResult(appointment=appointment, follow_up=follow_up, created=True)

    def send_booking_confirmation(
        self, db: Session, appointment_id: uuid.UUID
    ) -> DispatchResult:
        appointment = db.scalar(
            select(Appointment).where(Appointment.id == appointment_id).with_for_update()
        )
        if not appointment:
            raise LookupError("Appointment not found")
        lead = db.get(Lead, appointment.lead_id)
        if appointment.confirmation_sent_at:
            return DispatchResult(
                "already_sent", lead.pipeline_stage, appointment.confirmation_sent_at
            )
        if not lead.email:
            return DispatchResult("skipped_no_email", lead.pipeline_stage, None)

        business_zone = ZoneInfo(appointment.business_timezone)
        appointment_at = appointment.appointment_at
        if appointment_at.tzinfo is None:
            appointment_at = appointment_at.replace(tzinfo=timezone.utc)
        local_time = appointment_at.astimezone(business_zone)
        appointment_text = (
            f"{local_time.strftime('%A, %B %d, %Y at %I:%M %p')} "
            f"({appointment.business_timezone})"
        )
        follow_up = db.scalar(select(FollowUp).where(FollowUp.lead_id == lead.id))
        service_label = _service_label(lead.service_type)
        subject = (
            f"Appointment details saved: {service_label}"
            if service_label
            else "Appointment details saved"
        )
        paragraphs = [
            "Your appointment details have been saved for the time shown below."
        ]
        if follow_up and follow_up.status == "cancelled":
            paragraphs.append(
                "The pending follow-up for this request was cancelled because the "
                "appointment was saved."
            )
        details = _detail_rows(lead, appointment_text)
        plain_text = (
            f"Hello {lead.full_name},\n\n"
            + "\n\n".join(paragraphs)
            + _plain_details(details)
            + "\n\nDevelopment demonstration: This message was sent to a local test inbox. "
            "It does not reserve a technician, confirm commercial service, or reserve an "
            "external calendar.\n\nRegards,\nLocal automation demonstration"
        )
        self.email_gateway.send(
            lead.email,
            subject,
            plain_text,
            _html_message("Saved appointment details", lead.full_name, paragraphs, details),
        )
        sent_at = datetime.now(timezone.utc)
        appointment.confirmation_sent_at = sent_at
        db.add(
            AuditEvent(
                correlation_id=lead.correlation_id,
                lead_id=lead.id,
                event_type="booking_confirmation.sent",
                status="success",
                metadata_json={
                    "appointment_id": str(appointment.id),
                    "sent_at": sent_at.isoformat(),
                },
            )
        )
        db.commit()
        return DispatchResult("sent", lead.pipeline_stage, sent_at)

    @staticmethod
    def _existing_booking(
        db: Session, existing: Appointment, fingerprint: str
    ) -> BookingResult:
        if existing.booking_fingerprint != fingerprint:
            raise BookingConflictError(
                "Booking request identifier is associated with different booking data."
            )
        follow_up = db.scalar(select(FollowUp).where(FollowUp.lead_id == existing.lead_id))
        return BookingResult(appointment=existing, follow_up=follow_up, created=False)
