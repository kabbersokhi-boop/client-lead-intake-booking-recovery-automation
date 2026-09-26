import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.security import require_crm_adapter_key
from app.config import settings
from app.db.session import get_db
from app.providers.highlevel import HighLevelClient
from app.schemas.recovery import AttemptRequest, ClaimRequest
from app.schemas.stage_sync import StageSyncJobResponse, StageSyncProcessResponse
from app.services.stage_sync_service import StageSyncLeaseError, StageSyncService

router = APIRouter(prefix="/api/stage-sync", tags=["stage-sync"])
service = StageSyncService()


@router.post("/claim", response_model=StageSyncJobResponse | None)
def claim_stage_sync(
    request: ClaimRequest,
    _: None = Depends(require_crm_adapter_key),
    db: Session = Depends(get_db),
):
    return service.claim(db, request.worker_id)


@router.post("/{job_id}/process", response_model=StageSyncProcessResponse)
def process_stage_sync(
    job_id: uuid.UUID,
    request: AttemptRequest,
    _: None = Depends(require_crm_adapter_key),
    db: Session = Depends(get_db),
):
    if settings.crm_provider_mode not in {"highlevel_simulator", "highlevel_live"}:
        raise HTTPException(status_code=503, detail="HighLevel stage sync is not configured.")
    client = HighLevelClient(settings)
    try:
        return service.process(db, job_id, request.lease_token, client)
    except StageSyncLeaseError as error:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(error)) from error
    finally:
        client.client.close()


@router.post("/{job_id}/requeue", response_model=StageSyncJobResponse)
def requeue_stage_sync(
    job_id: uuid.UUID,
    _: None = Depends(require_crm_adapter_key),
    db: Session = Depends(get_db),
):
    try:
        return service.requeue(db, job_id)
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
