from abc import ABC, abstractmethod

from sqlalchemy.orm import Session

from app.schemas.lead import CRMLeadCreate
from app.services.crm_service import CreateLeadResult, DevelopmentCRMService


class CRMProvider(ABC):
    @abstractmethod
    def create_lead(self, db: Session, payload: CRMLeadCreate) -> CreateLeadResult: ...


class DevelopmentCRMProvider(CRMProvider):
    def __init__(self) -> None:
        self.service = DevelopmentCRMService()

    def create_lead(self, db: Session, payload: CRMLeadCreate) -> CreateLeadResult:
        return self.service.create_lead(db, payload)


class GoHighLevelCRMProvider(CRMProvider):
    def create_lead(self, db: Session, payload: CRMLeadCreate) -> CreateLeadResult:
        raise NotImplementedError("Future GoHighLevel sandbox integration is not configured.")
