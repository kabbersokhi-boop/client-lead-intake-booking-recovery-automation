import uuid
from abc import ABC, abstractmethod

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.models import FollowUp, Lead
from app.schemas.lead import CRMLeadCreate
from app.services.crm_service import CreateLeadResult, DevelopmentCRMService


class CRMProvider(ABC):
    @abstractmethod
    def create_lead(self, db: Session, payload: CRMLeadCreate) -> CreateLeadResult: ...

    @abstractmethod
    def replay_lead(self, db: Session, payload: CRMLeadCreate) -> CreateLeadResult: ...

    @abstractmethod
    def lookup_lead(
        self, db: Session, submission_id: uuid.UUID
    ) -> CreateLeadResult | None: ...


class DevelopmentCRMProvider(CRMProvider):
    def __init__(self) -> None:
        self.service = DevelopmentCRMService()

    def create_lead(self, db: Session, payload: CRMLeadCreate) -> CreateLeadResult:
        return self.service.create_lead(db, payload)

    def replay_lead(self, db: Session, payload: CRMLeadCreate) -> CreateLeadResult:
        return self.service.create_lead(db, payload)

    def lookup_lead(
        self, db: Session, submission_id: uuid.UUID
    ) -> CreateLeadResult | None:
        lead = db.scalar(select(Lead).where(Lead.submission_id == submission_id))
        if not lead:
            return None
        follow_up = db.scalar(select(FollowUp).where(FollowUp.lead_id == lead.id))
        return CreateLeadResult(lead=lead, follow_up=follow_up, created=False)


def build_crm_provider(settings: Settings) -> CRMProvider:
    if settings.crm_provider_mode == "development":
        return DevelopmentCRMProvider()
    if settings.crm_provider_mode in {"highlevel_simulator", "highlevel_live"}:
        from app.providers.highlevel import HighLevelCRMProvider

        return HighLevelCRMProvider(settings)
    raise RuntimeError(
        "CRM_PROVIDER_MODE must be development, highlevel_simulator, or highlevel_live."
    )
