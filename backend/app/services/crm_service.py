"""Idempotent persistence for the development CRM adapter."""

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import settings
from app.models import AuditEvent, FollowUp, Lead
from app.schemas.lead import CRMLeadCreate


class SubmissionConflictError(Exception):
    """A submission identifier was reused for different customer data."""


@dataclass(frozen=True)
class CreateLeadResult:
    lead: Lead
    follow_up: FollowUp | None
    created: bool


def submission_fingerprint(payload: CRMLeadCreate) -> str:
    """Hash stable, normalized customer data only; AI output is deliberately excluded."""
    normalized = {
        "full_name": payload.full_name.casefold(),
        "email": str(payload.email).casefold() if payload.email else None,
        "phone": "".join(character for character in (payload.phone or "") if character.isdigit())
        or None,
        "normalized_message": payload.normalized_message,
    }
    encoded = json.dumps(normalized, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


class DevelopmentCRMService:
    """Persistence implementation for the development CRM adapter boundary."""

    def create_lead(self, db: Session, payload: CRMLeadCreate) -> CreateLeadResult:
        fingerprint = submission_fingerprint(payload)
        existing = db.scalar(select(Lead).where(Lead.submission_id == payload.submission_id))
        if existing:
            return self._existing_result(existing, fingerprint, db)

        enrichment = payload.enrichment
        lead = Lead(
            submission_id=payload.submission_id,
            correlation_id=payload.correlation_id,
            full_name=payload.full_name,
            email=str(payload.email) if payload.email else None,
            phone=payload.phone,
            original_message=payload.original_message,
            normalized_message=payload.normalized_message,
            submission_fingerprint=fingerprint,
            client_received_at=payload.received_at,
            service_type=enrichment.service_type if enrichment else None,
            location=enrichment.location if enrichment else None,
            preferred_time=enrichment.preferred_time if enrichment else None,
            urgency=enrichment.urgency if enrichment else None,
            summary=enrichment.summary if enrichment else None,
            ai_status=payload.ai_status,
            needs_review=payload.needs_review,
            provider_metadata=(
                payload.provider_metadata.model_dump(exclude_none=True)
                if payload.provider_metadata
                else None
            ),
        )
        db.add(lead)
        try:
            db.flush()
            db.refresh(lead)
            follow_up = None
            if lead.email:
                follow_up = FollowUp(
                    lead_id=lead.id,
                    correlation_id=lead.correlation_id,
                    due_at=datetime.now(timezone.utc)
                    + timedelta(seconds=settings.follow_up_delay_seconds),
                )
                db.add(follow_up)
                db.flush()
                db.refresh(follow_up)
            db.add(
                AuditEvent(
                    correlation_id=payload.correlation_id,
                    lead_id=lead.id,
                    event_type="crm.lead_created",
                    status="success",
                    metadata_json={
                        "submission_id": str(payload.submission_id),
                        "ai_status": payload.ai_status,
                        "needs_review": payload.needs_review,
                        "client_received_at": payload.received_at.isoformat(),
                        "persisted_at": lead.created_at.isoformat() if lead.created_at else None,
                        "diagnostic": payload.enrichment_diagnostic,
                        "provider": (
                            payload.provider_metadata.model_dump(exclude_none=True)
                            if payload.provider_metadata
                            else None
                        ),
                    },
                )
            )
            if follow_up:
                db.add(
                    AuditEvent(
                        correlation_id=lead.correlation_id,
                        lead_id=lead.id,
                        event_type="follow_up.scheduled",
                        status="success",
                        metadata_json={
                            "follow_up_id": str(follow_up.id),
                            "due_at": follow_up.due_at.isoformat(),
                            "delay_seconds": settings.follow_up_delay_seconds,
                        },
                    )
                )
            db.commit()
        except IntegrityError:
            db.rollback()
            existing = db.scalar(select(Lead).where(Lead.submission_id == payload.submission_id))
            if existing:
                return self._existing_result(existing, fingerprint, db)
            raise

        db.refresh(lead)
        if follow_up:
            db.refresh(follow_up)
        return CreateLeadResult(lead=lead, follow_up=follow_up, created=True)

    @staticmethod
    def _existing_result(
        existing: Lead, fingerprint: str, db: Session | None = None
    ) -> CreateLeadResult:
        if existing.submission_fingerprint != fingerprint:
            raise SubmissionConflictError
        follow_up = (
            db.scalar(select(FollowUp).where(FollowUp.lead_id == existing.id)) if db else None
        )
        return CreateLeadResult(lead=existing, follow_up=follow_up, created=False)
