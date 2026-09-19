import uuid

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.security import require_crm_adapter_key
from app.db.session import get_db
from app.models import Appointment, AuditEvent, FollowUp, Lead
from app.providers.crm import DevelopmentCRMProvider
from app.schemas.lead import (
    AuditEventResponse,
    CRMCreateResponse,
    CRMLeadCreate,
    LeadResponse,
    TraceResponse,
)
from app.schemas.lifecycle import (
    BookingCreate,
    BookingCreateResponse,
    EmailDispatchResponse,
    FollowUpResponse,
)
from app.services.crm_service import SubmissionConflictError
from app.services.lifecycle_service import (
    BookingConflictError,
    BookingValidationError,
    EmailDeliveryError,
    LifecycleService,
)

router = APIRouter()
provider = DevelopmentCRMProvider()
lifecycle_service = LifecycleService()


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
    follow_up = result.follow_up
    response.status_code = status.HTTP_201_CREATED if result.created else status.HTTP_200_OK
    return CRMCreateResponse(
        crm_lead_id=lead.id, submission_id=lead.submission_id,
        correlation_id=lead.correlation_id, pipeline_stage=lead.pipeline_stage,
        ai_status=lead.ai_status, intake_state="created" if result.created else "replayed",
        follow_up_status=follow_up.status if follow_up else None,
        follow_up_due_at=follow_up.due_at if follow_up else None,
    )


@router.get("/api/crm/follow-ups/due", response_model=list[FollowUpResponse])
def list_due_follow_ups(
    limit: int = 25,
    _: None = Depends(require_crm_adapter_key),
    db: Session = Depends(get_db),
) -> list[FollowUp]:
    if limit < 1 or limit > 100:
        raise HTTPException(status_code=422, detail="limit must be between 1 and 100")
    return lifecycle_service.due_follow_ups(db, limit)


@router.post(
    "/api/crm/follow-ups/{follow_up_id}/dispatch", response_model=EmailDispatchResponse
)
def dispatch_follow_up(
    follow_up_id: uuid.UUID,
    _: None = Depends(require_crm_adapter_key),
    db: Session = Depends(get_db),
) -> EmailDispatchResponse:
    try:
        result = lifecycle_service.dispatch_follow_up(db, follow_up_id)
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except BookingValidationError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except EmailDeliveryError as error:
        db.rollback()
        raise HTTPException(status_code=503, detail=str(error)) from error
    return EmailDispatchResponse(
        state=result.state, pipeline_stage=result.pipeline_stage, sent_at=result.sent_at
    )


@router.post(
    "/api/crm/bookings", response_model=BookingCreateResponse, status_code=status.HTTP_201_CREATED
)
def create_booking(
    payload: BookingCreate,
    response: Response,
    _: None = Depends(require_crm_adapter_key),
    db: Session = Depends(get_db),
) -> BookingCreateResponse:
    try:
        result = lifecycle_service.create_booking(db, payload)
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except BookingValidationError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except BookingConflictError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    appointment = result.appointment
    lead = db.get(Lead, appointment.lead_id)
    response.status_code = status.HTTP_201_CREATED if result.created else status.HTTP_200_OK
    confirmation_state = "sent" if appointment.confirmation_sent_at else "pending"
    if not lead.email:
        confirmation_state = "skipped_no_email"
    return BookingCreateResponse(
        appointment_id=appointment.id,
        booking_request_id=appointment.booking_request_id,
        correlation_id=appointment.correlation_id,
        booking_state="created" if result.created else "replayed",
        appointment_status=appointment.status,
        appointment_at=appointment.appointment_at,
        business_timezone=appointment.business_timezone,
        pipeline_stage=lead.pipeline_stage,
        follow_up_status=result.follow_up.status if result.follow_up else None,
        confirmation_state=confirmation_state,
    )


@router.post(
    "/api/crm/appointments/{appointment_id}/confirmation",
    response_model=EmailDispatchResponse,
)
def send_booking_confirmation(
    appointment_id: uuid.UUID,
    _: None = Depends(require_crm_adapter_key),
    db: Session = Depends(get_db),
) -> EmailDispatchResponse:
    try:
        result = lifecycle_service.send_booking_confirmation(db, appointment_id)
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except EmailDeliveryError as error:
        db.rollback()
        raise HTTPException(status_code=503, detail=str(error)) from error
    return EmailDispatchResponse(
        state=result.state, pipeline_stage=result.pipeline_stage, sent_at=result.sent_at
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
    follow_ups = list(
        db.scalars(
            select(FollowUp)
            .where(FollowUp.correlation_id == correlation_id)
            .order_by(FollowUp.created_at.asc())
        )
    )
    appointments = list(
        db.scalars(
            select(Appointment)
            .where(Appointment.correlation_id == correlation_id)
            .order_by(Appointment.created_at.asc())
        )
    )
    audit_events = list_audit_events(correlation_id=correlation_id, db=db)
    return TraceResponse(
        correlation_id=correlation_id,
        lead=lead,
        follow_ups=follow_ups,
        appointments=appointments,
        audit_events=audit_events,
    )


@router.get("/api/leads/{lead_id}", response_model=LeadResponse)
def get_lead(lead_id: uuid.UUID, db: Session = Depends(get_db)) -> Lead:
    lead = db.get(Lead, lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    return lead
