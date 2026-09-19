from abc import ABC, abstractmethod

from sqlalchemy.orm import Session

from app.models import Lead
from app.schemas.lead import CRMLeadCreate
from app.services.crm_service import DevelopmentCRMService


class CRMProvider(ABC):
    @abstractmethod
    def create_lead(self, db: Session, payload: CRMLeadCreate) -> Lead: ...


class DevelopmentCRMProvider(CRMProvider):
    def __init__(self) -> None:
        self.service = DevelopmentCRMService()

    def create_lead(self, db: Session, payload: CRMLeadCreate) -> Lead:
        return self.service.create_lead(db, payload)


class GoHighLevelCRMProvider(CRMProvider):
    def create_lead(self, db: Session, payload: CRMLeadCreate) -> Lead:
        raise NotImplementedError("Future GoHighLevel sandbox integration is not configured.")
