from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AuditEvent, Lead
from app.schemas.lead import CRMLeadCreate


class DevelopmentCRMService:
    """Persistence implementation for the development CRM adapter boundary."""

    def create_lead(self, db: Session, payload: CRMLeadCreate) -> Lead:
        existing = db.scalar(select(Lead).where(Lead.submission_id == payload.submission_id))
        if existing:
            return existing
        enrichment = payload.enrichment
        lead = Lead(
            submission_id=payload.submission_id, correlation_id=payload.correlation_id,
            full_name=payload.full_name, email=str(payload.email) if payload.email else None,
            phone=payload.phone, original_message=payload.original_message,
            service_type=enrichment.service_type if enrichment else None,
            location=enrichment.location if enrichment else None,
            preferred_time=enrichment.preferred_time if enrichment else None,
            urgency=enrichment.urgency if enrichment else None,
            summary=enrichment.summary if enrichment else None, ai_status=payload.ai_status,
            needs_review=payload.needs_review,
        )
        db.add(lead)
        db.flush()
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
                    "diagnostic": payload.enrichment_diagnostic,
                },
            )
        )
        db.commit()
        db.refresh(lead)
        return lead
