from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.security import require_crm_adapter_key
from app.db.session import get_db
from app.schemas.reporting import ManagementSummary
from app.services.reporting_service import ReportingService

router = APIRouter(prefix="/api/reporting", tags=["reporting"])


@router.get("/management-summary", response_model=ManagementSummary)
def management_summary(
    business_date: date | None = Query(default=None),
    _: None = Depends(require_crm_adapter_key),
    db: Session = Depends(get_db),
) -> ManagementSummary:
    return ReportingService().management_summary(db, business_date=business_date)
