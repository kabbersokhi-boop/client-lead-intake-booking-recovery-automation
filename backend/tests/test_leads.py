import uuid
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError
from sqlalchemy import select

from app.api.routes import get_lead, get_trace, list_audit_events, list_leads
from app.models import AuditEvent, Lead
from app.providers.crm import DevelopmentCRMProvider
from app.schemas.lead import CRMLeadCreate


def payload(**overrides):
    value = {
        "submission_id": str(uuid.uuid4()),
        "correlation_id": str(uuid.uuid4()),
        "received_at": datetime.now(timezone.utc).isoformat(),
        "full_name": "  Maya Verma ",
        "email": " MAYA.VERMA@EXAMPLE.COM ",
        "phone": " +1 604 555 0138 ",
        "original_message": "  Furnace does not heat properly. ",
        "enrichment": {
            "service_type": "furnace_service",
            "location": "Surrey",
            "preferred_time": "Tuesday afternoon",
            "urgency": "medium",
            "summary": "Older furnace is not heating properly.",
        },
        "ai_status": "enriched",
        "needs_review": False,
    }
    value.update(overrides)
    return value


def test_valid_schema_normalizes_contact_data():
    lead = CRMLeadCreate.model_validate(payload())
    assert lead.full_name == "Maya Verma"
    assert str(lead.email) == "maya.verma@example.com"
    assert lead.phone == "+1 604 555 0138"
    assert lead.original_message == "Furnace does not heat properly."


@pytest.mark.parametrize(
    "changes",
    [
        {"full_name": "   "},
        {"email": None, "phone": None},
        {"email": "not-an-email"},
    ],
)
def test_invalid_schema_rejected(changes):
    with pytest.raises(ValidationError):
        CRMLeadCreate.model_validate(payload(**changes))


def test_crm_persists_enriched_lead_audit_event_and_correlation(db):
    request = payload()
    response = DevelopmentCRMProvider().create_lead(db, CRMLeadCreate.model_validate(request))
    assert str(response.correlation_id) == request["correlation_id"]

    persisted = list_leads(correlation_id=uuid.UUID(request["correlation_id"]), db=db)[0]
    assert persisted.original_message == "Furnace does not heat properly."
    assert persisted.service_type == "furnace_service"
    assert persisted.needs_review is False

    events = list_audit_events(correlation_id=uuid.UUID(request["correlation_id"]), db=db)
    assert events[0].event_type == "crm.lead_created"
    assert events[0].metadata_json["ai_status"] == "enriched"
    assert db.scalar(select(AuditEvent).where(AuditEvent.lead_id == response.id))

    trace = get_trace(correlation_id=uuid.UUID(request["correlation_id"]), db=db)
    assert trace.lead is not None
    assert trace.lead.id == response.id
    assert len(trace.audit_events) == 1


@pytest.mark.parametrize("ai_status", ["fallback_invalid", "fallback_unavailable"])
def test_safe_ai_fallback_persists_lead_for_review(db, ai_status):
    request = payload(enrichment=None, ai_status=ai_status, needs_review=True)
    request["enrichment_diagnostic"] = "Model response could not be used."
    response = DevelopmentCRMProvider().create_lead(db, CRMLeadCreate.model_validate(request))
    persisted = get_lead(lead_id=response.id, db=db)
    assert persisted.ai_status == ai_status
    assert persisted.needs_review is True
    assert persisted.summary is None


def test_submission_id_is_idempotent(db):
    request = CRMLeadCreate.model_validate(payload())
    provider = DevelopmentCRMProvider()

    first = provider.create_lead(db, request)
    second = provider.create_lead(db, request)

    assert first.id == second.id
    assert len(list(db.scalars(select(Lead)))) == 1
    assert len(list(db.scalars(select(AuditEvent)))) == 1
