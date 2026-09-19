import uuid
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError
from sqlalchemy import select

from app.api.routes import get_lead, get_trace, list_audit_events, list_leads
from app.models import AuditEvent, Lead
from app.providers.crm import DevelopmentCRMProvider
from app.schemas.lead import CRMLeadCreate
from app.services.crm_service import SubmissionConflictError


def payload(**overrides):
    value = {
        "submission_id": str(uuid.uuid4()),
        "correlation_id": str(uuid.uuid4()),
        "received_at": datetime.now(timezone.utc).isoformat(),
        "full_name": "  Maya Verma ",
        "email": " MAYA.VERMA@EXAMPLE.COM ",
        "phone": " +1 604 555 0138 ",
        "original_message": "  Furnace does not heat properly. ",
        "normalized_message": "Furnace does not heat properly.",
        "enrichment": {
            "service_type": "furnace_service",
            "location": "Surrey",
            "preferred_time": "Tuesday afternoon",
            "urgency": "medium",
            "summary": "Older furnace is not heating properly.",
        },
        "ai_status": "enriched",
        "needs_review": False,
        "provider_metadata": {
            "provider": "nvidia_nim",
            "model_id": "example/model",
            "outcome_class": "enriched",
            "status_code": 200,
        },
    }
    value.update(overrides)
    return value


def test_valid_schema_normalizes_contact_data_and_preserves_original_message():
    lead = CRMLeadCreate.model_validate(payload())
    assert lead.full_name == "Maya Verma"
    assert str(lead.email) == "maya.verma@example.com"
    assert lead.phone == "+1 604 555 0138"
    assert lead.original_message == "  Furnace does not heat properly. "
    assert lead.normalized_message == "Furnace does not heat properly."


@pytest.mark.parametrize(
    "changes",
    [
        {"full_name": "   "},
        {"email": None, "phone": None},
        {"email": "not-an-email"},
        {"email": 123},
        {"phone": {"number": "1234567890"}},
        {"email": None, "phone": "+++++++"},
        {"enrichment": {**payload()["enrichment"], "location": 42}},
    ],
)
def test_wrong_types_and_unusable_contact_shapes_are_validation_errors(changes):
    with pytest.raises(ValidationError):
        CRMLeadCreate.model_validate(payload(**changes))


@pytest.mark.parametrize(
    "changes",
    [
        {"ai_status": "enriched", "enrichment": None, "needs_review": False},
        {"ai_status": "fallback_invalid", "enrichment": None, "needs_review": False},
        {"ai_status": "fallback_unavailable", "enrichment": None, "needs_review": False},
        {
            "ai_status": "fallback_invalid",
            "enrichment": payload()["enrichment"],
            "needs_review": True,
        },
    ],
)
def test_ai_state_invariants_are_rejected(changes):
    with pytest.raises(ValidationError):
        CRMLeadCreate.model_validate(payload(**changes))


def test_enriched_records_may_have_an_additional_review_reason():
    lead = CRMLeadCreate.model_validate(payload(needs_review=True))
    assert lead.ai_status == "enriched"
    assert lead.needs_review is True


def test_crm_persists_enriched_lead_audit_event_and_trace_timestamps(db):
    request = payload()
    result = DevelopmentCRMProvider().create_lead(db, CRMLeadCreate.model_validate(request))
    lead = result.lead
    assert result.created is True
    assert str(lead.correlation_id) == request["correlation_id"]

    persisted = list_leads(correlation_id=uuid.UUID(request["correlation_id"]), db=db)[0]
    assert persisted.original_message == request["original_message"]
    assert persisted.normalized_message == request["normalized_message"]
    assert persisted.service_type == "furnace_service"
    assert persisted.needs_review is False
    assert persisted.client_received_at.replace(tzinfo=timezone.utc) == datetime.fromisoformat(
        request["received_at"]
    )
    assert persisted.created_at is not None

    events = list_audit_events(correlation_id=uuid.UUID(request["correlation_id"]), db=db)
    assert events[0].event_type == "crm.lead_created"
    assert events[0].metadata_json["ai_status"] == "enriched"
    assert events[0].metadata_json["client_received_at"] == request["received_at"]
    assert events[0].metadata_json["persisted_at"]
    assert db.scalar(select(AuditEvent).where(AuditEvent.lead_id == lead.id))

    trace = get_trace(correlation_id=uuid.UUID(request["correlation_id"]), db=db)
    assert trace.lead is not None
    assert trace.lead.id == lead.id
    assert len(trace.audit_events) == 1


@pytest.mark.parametrize("ai_status", ["fallback_invalid", "fallback_unavailable"])
def test_safe_ai_fallback_persists_lead_for_review(db, ai_status):
    request = payload(
        enrichment=None,
        ai_status=ai_status,
        needs_review=True,
        provider_metadata={
            "provider": "nvidia_nim",
            "model_id": "example/model",
            "outcome_class": (
                "provider_error" if ai_status == "fallback_unavailable" else "invalid_output"
            ),
            "status_code": 503 if ai_status == "fallback_unavailable" else 200,
            "error_code": (
                "provider_unavailable" if ai_status == "fallback_unavailable" else "invalid_json"
            ),
        },
    )
    request["enrichment_diagnostic"] = "Model response could not be used."
    result = DevelopmentCRMProvider().create_lead(db, CRMLeadCreate.model_validate(request))
    persisted = get_lead(lead_id=result.lead.id, db=db)
    assert persisted.ai_status == ai_status
    assert persisted.needs_review is True
    assert persisted.summary is None


def test_submission_id_is_idempotent_for_same_customer_input(db):
    request = CRMLeadCreate.model_validate(payload())
    provider = DevelopmentCRMProvider()

    first = provider.create_lead(db, request)
    second = provider.create_lead(db, request)

    assert first.created is True
    assert second.created is False
    assert first.lead.id == second.lead.id
    assert len(list(db.scalars(select(Lead)))) == 1
    assert len(list(db.scalars(select(AuditEvent)))) == 1


def test_same_submission_id_with_different_customer_input_is_conflict(db):
    provider = DevelopmentCRMProvider()
    first = CRMLeadCreate.model_validate(payload())
    provider.create_lead(db, first)
    changed = CRMLeadCreate.model_validate(
        payload(
            submission_id=str(first.submission_id),
            correlation_id=str(first.correlation_id),
            original_message="A different customer message.",
            normalized_message="A different customer message.",
        )
    )

    with pytest.raises(SubmissionConflictError):
        provider.create_lead(db, changed)
    assert len(list(db.scalars(select(Lead)))) == 1
    assert len(list(db.scalars(select(AuditEvent)))) == 1
