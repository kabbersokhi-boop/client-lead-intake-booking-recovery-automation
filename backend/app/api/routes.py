import uuid

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.security import require_crm_adapter_key
from app.db.session import get_db
from app.models import AuditEvent, Lead
from app.providers.crm import DevelopmentCRMProvider
from app.schemas.lead import (
    AuditEventResponse,
    CRMCreateResponse,
    CRMLeadCreate,
    LeadResponse,
    TraceResponse,
)
from app.services.crm_service import SubmissionConflictError

router = APIRouter()
provider = DevelopmentCRMProvider()


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.post(
    "/api/crm/leads", response_model=CRMCreateResponse, status_code=status.HTTP_201_CREATED
)
def create_crm_lead(
    payload: CRMLeadCreate,
    response: Response,
    _: None = Depends(require_crm_adapter_key),
    db: Session = Depends(get_db),
) -> CRMCreateResponse:
    try:
        result = provider.create_lead(db, payload)
    except SubmissionConflictError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Submission identifier is already associated with different lead data.",
        ) from error
    lead = result.lead
    response.status_code = status.HTTP_201_CREATED if result.created else status.HTTP_200_OK
    return CRMCreateResponse(
        crm_lead_id=lead.id, submission_id=lead.submission_id,
        correlation_id=lead.correlation_id, pipeline_stage=lead.pipeline_stage,
        ai_status=lead.ai_status, intake_state="created" if result.created else "replayed",
    )


@router.get("/api/leads", response_model=list[LeadResponse])
def list_leads(
    correlation_id: uuid.UUID | None = None, db: Session = Depends(get_db)
) -> list[Lead]:
    statement = select(Lead).order_by(Lead.created_at.desc())
    if correlation_id:
        statement = statement.where(Lead.correlation_id == correlation_id)
    return list(db.scalars(statement))


@router.get("/api/audit-events", response_model=list[AuditEventResponse])
def list_audit_events(correlation_id: uuid.UUID, db: Session = Depends(get_db)) -> list[AuditEvent]:
    statement = (
        select(AuditEvent)
        .where(AuditEvent.correlation_id == correlation_id)
        .order_by(AuditEvent.created_at.asc())
    )
    return list(db.scalars(statement))


@router.get("/api/traces/{correlation_id}", response_model=TraceResponse)
def get_trace(correlation_id: uuid.UUID, db: Session = Depends(get_db)) -> TraceResponse:
    lead = db.scalar(select(Lead).where(Lead.correlation_id == correlation_id))
    audit_events = list_audit_events(correlation_id=correlation_id, db=db)
    return TraceResponse(correlation_id=correlation_id, lead=lead, audit_events=audit_events)


@router.get("/api/leads/{lead_id}", response_model=LeadResponse)
def get_lead(lead_id: uuid.UUID, db: Session = Depends(get_db)) -> Lead:
    lead = db.get(Lead, lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    return lead
