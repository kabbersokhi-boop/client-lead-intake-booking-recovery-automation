import uuid
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session
from test_highlevel_adapter import ContractBackend, configured_client, lead_payload

from app.config import settings
from app.models import CRMWriteJob, FollowUp, Lead, StageSyncAttempt, StageSyncJob
from app.providers.crm import DevelopmentCRMProvider
from app.providers.highlevel import HighLevelProviderError
from app.schemas.lifecycle import BookingCreate
from app.services.lifecycle_service import LifecycleService
from app.services.stage_sync_service import StageSyncLeaseError, StageSyncService


class EmailSink:
    def send(self, *_args):
        pass


def new_lead(db):
    return DevelopmentCRMProvider().create_lead(db, lead_payload()).lead


def booking(lead):
    local = datetime.now(ZoneInfo(settings.business_timezone)).replace(
        second=0, microsecond=0
    ) + timedelta(days=2)
    return BookingCreate(
        booking_request_id=uuid.uuid4(), correlation_id=lead.correlation_id,
        appointment_local=local.replace(tzinfo=None),
        business_timezone=settings.business_timezone,
    )


def remote_for(backend, lead, stage="sim_stage_new_lead"):
    backend.contacts["contact-1"] = {
        "id": "contact-1", "email": lead.email, "phone": lead.phone,
        "locationId": "sim_location_reference",
        "customFields": [
            {"id": "sim_cf_submission_id", "value": str(lead.submission_id)},
            {"id": "sim_cf_correlation_id", "value": str(lead.correlation_id)},
        ],
    }
    backend.opportunities["opportunity-1"] = {
        "id": "opportunity-1", "contactId": "contact-1",
        "locationId": "sim_location_reference", "pipelineId": "sim_pipeline_hvac",
        "pipelineStageId": stage, "status": "open",
        "customFields": [{"id": "sim_of_submission_id", "value": str(lead.submission_id)}],
    }


def test_lifecycle_outbox_coalesces_and_never_decreases(db, monkeypatch):
    monkeypatch.setattr(settings, "crm_provider_mode", "highlevel_simulator")
    lead = new_lead(db)
    follow_up = db.scalar(select(FollowUp).where(FollowUp.lead_id == lead.id))
    follow_up.due_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    db.commit()
    service = LifecycleService(EmailSink())
    service.dispatch_follow_up(db, follow_up.id)
    job = db.scalar(select(StageSyncJob).where(StageSyncJob.lead_id == lead.id))
    assert (job.desired_stage, job.desired_rank, job.desired_version) == ("contacted", 1, 1)
    service.dispatch_follow_up(db, follow_up.id)
    assert job.desired_version == 1
    request = booking(lead)
    service.create_booking(db, request)
    service.create_booking(db, request)
    db.refresh(job)
    assert (job.desired_stage, job.desired_rank, job.desired_version) == (
        "appointment_booked", 2, 2
    )
    StageSyncService.advance(db, lead, "contacted")
    db.commit()
    persisted = db.scalar(select(StageSyncJob).where(StageSyncJob.lead_id == lead.id))
    assert persisted.desired_version == 2
    assert len(list(db.scalars(select(StageSyncJob)))) == 1


@pytest.mark.parametrize("remote,desired,expected,writes", [
    ("sim_stage_new_lead", "contacted", "contacted", 1),
    ("sim_stage_contacted", "contacted", "contacted", 0),
    ("sim_stage_contacted", "appointment_booked", "appointment_booked", 1),
    ("sim_stage_appointment_booked", "contacted", "appointment_booked", 0),
])
def test_provider_moves_only_forward(db, remote, desired, expected, writes):
    lead = new_lead(db)
    backend = ContractBackend()
    remote_for(backend, lead, remote)
    client = configured_client(backend)
    assert client.sync_opportunity_stage(lead, desired) == expected
    assert sum(req.method == "PUT" for req in backend.requests) == writes
    assert sum(
        req.method == "POST" and req.url.path == "/opportunities/" for req in backend.requests
    ) == 0


def test_provider_missing_ambiguous_and_unmanaged_fail_closed(db):
    lead = new_lead(db)
    backend = ContractBackend()
    remote_for(backend, lead)
    client = configured_client(backend)
    backend.opportunities.clear()
    with pytest.raises(HighLevelProviderError) as missing:
        client.sync_opportunity_stage(lead, "contacted")
    assert missing.value.error_class == "highlevel_opportunity_missing"
    remote_for(backend, lead)
    backend.opportunities["opportunity-2"] = dict(
        backend.opportunities["opportunity-1"], id="opportunity-2"
    )
    with pytest.raises(HighLevelProviderError) as ambiguous:
        client.sync_opportunity_stage(lead, "contacted")
    assert ambiguous.value.error_class == "highlevel_identity_conflict"
    backend.opportunities.pop("opportunity-2")
    backend.opportunities["opportunity-1"]["pipelineStageId"] = "manual-stage"
    with pytest.raises(HighLevelProviderError) as unmanaged:
        client.sync_opportunity_stage(lead, "contacted")
    assert unmanaged.value.error_class == "highlevel_unmanaged_stage"
    assert not any(req.method == "PUT" for req in backend.requests)


def test_closed_opportunity_is_not_reopened(db):
    lead = new_lead(db)
    backend = ContractBackend()
    remote_for(backend, lead)
    backend.opportunities["opportunity-1"]["status"] = "won"
    with pytest.raises(HighLevelProviderError) as closed:
        configured_client(backend).sync_opportunity_stage(lead, "contacted")
    assert closed.value.error_class == "highlevel_unmanaged_status"
    assert backend.opportunities["opportunity-1"]["status"] == "won"
    assert not any(req.method == "PUT" for req in backend.requests)


def test_claim_reclaim_and_stale_ownership(db, monkeypatch):
    monkeypatch.setattr(settings, "crm_provider_mode", "highlevel_simulator")
    lead = new_lead(db)
    StageSyncService.advance(db, lead, "contacted")
    db.commit()
    service = StageSyncService()
    first = service.claim(db, "worker-1")
    token = first.lease_token
    assert service.claim(db, "worker-2") is None
    first.lease_expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    db.commit()
    second = service.claim(db, "worker-2")
    assert second.lease_token != token
    with pytest.raises(StageSyncLeaseError):
        service._owned(db, first.id, token)
    db.rollback()


def test_desired_advance_during_owned_remote_write_survives(db, monkeypatch):
    monkeypatch.setattr(settings, "crm_provider_mode", "highlevel_simulator")
    lead = new_lead(db)
    StageSyncService.advance(db, lead, "contacted")
    db.commit()
    service = StageSyncService()
    claimed = service.claim(db, "worker-1")

    class ConcurrentClient:
        def sync_opportunity_stage(self, _lead, stage):
            assert stage == "contacted"
            with Session(db.get_bind()) as other:
                other_lead = other.get(Lead, lead.id)
                StageSyncService.advance(other, other_lead, "appointment_booked")
                other.commit()
            return "contacted"

    result = service.process(db, claimed.id, claimed.lease_token, ConcurrentClient())
    assert (result.state, result.desired_version, result.desired_stage) == (
        "pending", 2, "appointment_booked"
    )
    assert db.scalar(select(StageSyncAttempt)).outcome == "superseded"

    class FinalClient:
        def sync_opportunity_stage(self, _lead, stage):
            assert stage == "appointment_booked"
            return stage

    claimed = service.claim(db, "worker-2")
    result = service.process(db, claimed.id, claimed.lease_token, FinalClient())
    assert (result.state, result.verified_remote_stage) == ("completed", "appointment_booked")


@pytest.mark.parametrize("code,expected", [
    (429, "retry_wait"), (401, "blocked"), (403, "blocked"),
    (500, "retry_wait"), (None, "retry_wait"), (409, "needs_review"),
    (502, "retry_wait"),
])
def test_failure_classification(db, monkeypatch, code, expected):
    monkeypatch.setattr(settings, "crm_provider_mode", "highlevel_simulator")
    lead = new_lead(db)
    StageSyncService.advance(db, lead, "contacted")
    db.commit()
    service = StageSyncService()
    claimed = service.claim(db, "test")

    class FailingClient:
        def sync_opportunity_stage(self, *_args):
            raise HighLevelProviderError(
                code, "synthetic_failure", "Safe test failure.",
                "120" if code == 429 else None,
            )

    before = datetime.now(timezone.utc)
    result = service.process(db, claimed.id, claimed.lease_token, FailingClient())
    assert result.state == expected
    if code == 429:
        job = db.get(StageSyncJob, claimed.id)
        due_at = job.due_at
        if due_at.tzinfo is None:
            due_at = due_at.replace(tzinfo=timezone.utc)
        assert due_at >= before + timedelta(seconds=120)


def test_blocked_credential_pause_survives_desired_advance(db, monkeypatch):
    monkeypatch.setattr(settings, "crm_provider_mode", "highlevel_simulator")
    first_lead = new_lead(db)
    job = StageSyncService.advance(db, first_lead, "contacted")
    db.commit()
    job.state = "blocked"
    job.last_error_class = "highlevel_authentication"
    db.commit()
    StageSyncService.advance(db, first_lead, "appointment_booked")
    second_lead = new_lead(db)
    StageSyncService.advance(db, second_lead, "contacted")
    db.commit()
    assert StageSyncService.claim(db, "worker") is None
    StageSyncService.requeue(db, job.id)
    assert StageSyncService.claim(db, "worker") is not None


def test_upstream_retry_after_never_shortens_backoff(db, monkeypatch):
    monkeypatch.setattr(settings, "crm_provider_mode", "highlevel_simulator")
    lead = new_lead(db)
    StageSyncService.advance(db, lead, "contacted")
    db.commit()
    service = StageSyncService()
    claimed = service.claim(db, "worker")

    class UnavailableClient:
        def sync_opportunity_stage(self, *_args):
            raise HighLevelProviderError(503, "highlevel_upstream_failure", "Unavailable.", "120")

    before = datetime.now(timezone.utc)
    service.process(db, claimed.id, claimed.lease_token, UnavailableClient())
    due_at = db.get(StageSyncJob, claimed.id).due_at
    if due_at.tzinfo is None:
        due_at = due_at.replace(tzinfo=timezone.utc)
    assert due_at >= before + timedelta(seconds=120)


def test_operations_projection_and_protected_worker_contract(db, client, monkeypatch):
    monkeypatch.setattr(settings, "crm_provider_mode", "highlevel_simulator")
    lead = new_lead(db)
    StageSyncService.advance(db, lead, "contacted")
    db.commit()
    response = client.get(f"/api/operations/stage-sync?submission_id={lead.submission_id}")
    assert response.status_code == 200
    item = response.json()["items"][0]
    assert item["desired_stage"] == "contacted"
    assert item["state"] == "pending"
    assert "lease_token" not in item
    assert "email" not in item
    assert "payload_json" not in item
    assert db.scalar(select(StageSyncJob)).state == "pending"
    unauthorized = client.post(
        "/api/stage-sync/claim", json={"worker_id": "test"},
        headers={"X-CRM-Adapter-Key": "incorrect"},
    )
    assert unauthorized.status_code == 401
    claimed = client.post("/api/stage-sync/claim", json={"worker_id": "test"})
    assert claimed.status_code == 200
    assert claimed.json()["state"] == "processing"
    assert claimed.json()["lease_token"]


def test_pending_work_survives_session_restart(db, monkeypatch):
    monkeypatch.setattr(settings, "crm_provider_mode", "highlevel_simulator")
    lead = new_lead(db)
    StageSyncService.advance(db, lead, "contacted")
    db.commit()
    with Session(db.get_bind()) as restarted:
        claimed = StageSyncService.claim(restarted, "after-restart")
        assert claimed.submission_id == lead.submission_id
        assert claimed.state == "processing"


def test_stage_waits_for_initial_crm_create_without_spending_attempt(db, monkeypatch):
    monkeypatch.setattr(settings, "crm_provider_mode", "highlevel_simulator")
    lead = new_lead(db)
    StageSyncService.advance(db, lead, "contacted")
    create = CRMWriteJob(
        submission_id=lead.submission_id,
        correlation_id=lead.correlation_id,
        operation_kind="create_lead",
        payload_fingerprint="0" * 64,
        payload_json={},
        state="retry_wait",
        due_at=datetime.now(timezone.utc) + timedelta(minutes=3),
    )
    db.add(create)
    db.commit()
    service = StageSyncService()
    claimed = service.claim(db, "stage-worker")

    class UnexpectedClient:
        def sync_opportunity_stage(self, *_args):
            raise AssertionError("Stage provider should not run before initial CRM creation.")

    result = service.process(db, claimed.id, claimed.lease_token, UnexpectedClient())
    assert result.state == "retry_wait"
    job = db.get(StageSyncJob, claimed.id)
    assert job.attempt_count == 0
    assert len(list(db.scalars(select(StageSyncAttempt)))) == 0
    due = job.due_at.replace(tzinfo=timezone.utc) if job.due_at.tzinfo is None else job.due_at
    initial_due = (
        create.due_at.replace(tzinfo=timezone.utc)
        if create.due_at.tzinfo is None else create.due_at
    )
    assert due >= initial_due
    create.state = "completed"
    job.due_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    db.commit()
    claimed = service.claim(db, "stage-worker")

    class VerifiedClient:
        def sync_opportunity_stage(self, _lead, stage):
            return stage

    result = service.process(db, claimed.id, claimed.lease_token, VerifiedClient())
    assert result.state == "completed"
