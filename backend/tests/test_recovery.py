import uuid
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime

import pytest
from fastapi import HTTPException
from sqlalchemy import func, select
from test_leads import payload

from app.api.routes import _apply_fault_quota, get_fault_run
from app.config import settings
from app.models import CRMFaultRun, CRMWriteAttempt, CRMWriteJob, Lead, RecoveryIncident
from app.schemas.lead import CRMLeadCreate
from app.services.crm_service import DevelopmentCRMService
from app.services.recovery_service import (
    MAX_RETRY_AFTER_SECONDS,
    RecoveryConflictError,
    RecoveryService,
    StaleLeaseError,
    parse_retry_after,
    retry_after_seconds,
    retry_decision,
)


def validated_payload(**overrides):
    return CRMLeadCreate.model_validate(payload(**overrides))


def test_retry_after_supports_seconds_http_date_invalid_missing_and_long_delay():
    now = datetime(2026, 9, 20, 10, 0, tzinfo=timezone.utc)
    assert retry_after_seconds("12", now) == 12
    assert retry_after_seconds(format_datetime(now + timedelta(seconds=31)), now) == 31
    assert retry_after_seconds("not-a-delay", now) is None
    assert retry_after_seconds(None, now) is None
    assert retry_decision(429, 1, "7200", now).due_at == now + timedelta(hours=2)
    assert retry_decision(429, 1, None, now).due_at == now + timedelta(
        seconds=settings.crm_retry_fallback_seconds
    )


@pytest.mark.parametrize("value", ["99999999999999999999", "²"])
def test_unrepresentable_or_nonnormal_numeric_retry_after_never_crashes(value):
    now = datetime(2026, 9, 20, 10, 0, tzinfo=timezone.utc)
    parsed = parse_retry_after(value, now)
    if value.isascii():
        assert parsed.unrepresentable is True
        decision = retry_decision(429, 1, value, now)
        assert decision.state == "needs_review"
        assert decision.due_at == now
    else:
        assert parsed.unrepresentable is False
        assert retry_decision(429, 1, value, now).due_at == now + timedelta(
            seconds=settings.crm_retry_fallback_seconds
        )


def test_retry_after_database_integer_boundary_is_safe():
    now = datetime(2026, 9, 20, 10, 0, tzinfo=timezone.utc)
    assert parse_retry_after(str(MAX_RETRY_AFTER_SECONDS), now).seconds == (
        MAX_RETRY_AFTER_SECONDS
    )
    assert parse_retry_after(str(MAX_RETRY_AFTER_SECONDS + 1), now).unrepresentable is True


def test_retry_classification_and_exact_total_attempt_budget():
    now = datetime(2026, 9, 20, 10, 0, tzinfo=timezone.utc)
    assert retry_decision(400, 1, None, now).state == "needs_review"
    assert retry_decision(401, 1, None, now).state == "blocked"
    assert retry_decision(503, 1, None, now).state == "retry_wait"
    assert retry_decision(None, 2, None, now).due_at == now + timedelta(
        seconds=settings.crm_retry_fallback_seconds * 2
    )
    assert retry_decision(429, settings.crm_recovery_max_attempts, "10", now).state == (
        "needs_review"
    )
    assert retry_decision(401, 1, "99999999999999999999", now).state == "blocked"


def test_durable_admission_uniqueness_conflict_and_completed_reuse(db):
    service = RecoveryService()
    request = validated_payload()
    first, created = service.admit(db, request)
    replay, replay_created = service.admit(db, request)
    assert created is True
    assert replay_created is False
    assert replay.id == first.id
    assert db.scalar(select(func.count()).select_from(CRMWriteJob)) == 1

    changed = validated_payload(
        submission_id=str(request.submission_id),
        correlation_id=str(request.correlation_id),
        original_message="Different",
        normalized_message="Different",
    )
    with pytest.raises(RecoveryConflictError):
        service.admit(db, changed)

    other = validated_payload(
        submission_id=str(uuid.uuid4()), correlation_id=str(uuid.uuid4())
    )
    lead = DevelopmentCRMService().create_lead(db, other).lead
    completed, _ = service.admit(db, other)
    assert completed.state == "completed"
    assert completed.completed_lead_id == lead.id


def test_durable_intake_reuses_first_prepared_payload_when_later_ai_changes(client, db):
    prepared = validated_payload()
    admitted = client.post(
        "/api/recovery/jobs", json={"payload": prepared.model_dump(mode="json")}
    )
    assert admitted.status_code == 201

    later_fallback = prepared.model_copy(
        update={
            "enrichment": None,
            "ai_status": "fallback_invalid",
            "needs_review": True,
            "provider_metadata": None,
        }
    )
    delivered = client.post(
        "/api/recovery/intake",
        json={"payload": later_fallback.model_dump(mode="json")},
    )

    assert delivered.status_code == 201
    assert delivered.json()["ai_status"] == "enriched"
    job = db.scalar(select(CRMWriteJob).where(CRMWriteJob.submission_id == prepared.submission_id))
    lead = db.scalar(select(Lead).where(Lead.submission_id == prepared.submission_id))
    assert job.payload_json["ai_status"] == "enriched"
    assert lead.ai_status == "enriched"
    assert lead.service_type == prepared.enrichment.service_type
    assert job.attempt_count == 1


def test_durable_intake_reuses_prepared_enrichment_details(client, db):
    prepared = validated_payload()
    client.post("/api/recovery/jobs", json={"payload": prepared.model_dump(mode="json")})
    changed_enrichment = prepared.enrichment.model_copy(
        update={"summary": "A later model returned different extraction details."}
    )
    later = prepared.model_copy(update={"enrichment": changed_enrichment})

    delivered = client.post(
        "/api/recovery/intake", json={"payload": later.model_dump(mode="json")}
    )

    assert delivered.status_code == 201
    lead = db.scalar(select(Lead).where(Lead.submission_id == prepared.submission_id))
    assert lead.summary == prepared.enrichment.summary


def test_completed_admission_replays_persisted_ai_not_later_ai(client, db):
    prepared = validated_payload()
    lead = DevelopmentCRMService().create_lead(db, prepared).lead
    later_fallback = prepared.model_copy(
        update={
            "enrichment": None,
            "ai_status": "fallback_invalid",
            "needs_review": True,
            "provider_metadata": None,
        }
    )

    replay = client.post(
        "/api/recovery/intake",
        json={"payload": later_fallback.model_dump(mode="json")},
    )

    assert replay.status_code == 200
    assert replay.json()["crm_lead_id"] == str(lead.id)
    assert replay.json()["ai_status"] == "enriched"
    job = db.scalar(select(CRMWriteJob).where(CRMWriteJob.submission_id == prepared.submission_id))
    assert job.payload_json["ai_status"] == "enriched"


def test_expired_lease_is_reclaimed_and_stale_worker_cannot_complete(db):
    service = RecoveryService()
    request = validated_payload()
    job, _ = service.admit(db, request)
    first = service.claim(db, "worker-one")
    stale_token = first.lease_token
    first.lease_expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    db.commit()
    current = service.claim(db, "worker-two")
    assert current.id == job.id
    assert current.lease_token != stale_token
    lead = DevelopmentCRMService().create_lead(db, request).lead
    with pytest.raises(StaleLeaseError):
        service.complete(db, job.id, stale_token, lead.id)
    completed = service.complete(db, job.id, current.lease_token, lead.id)
    assert completed.state == "completed"


def test_attempt_history_retry_and_exhaustion_are_not_reset(db):
    service = RecoveryService()
    job, _ = service.admit(db, validated_payload())
    now = datetime.now(timezone.utc)
    for attempt_number in range(1, settings.crm_recovery_max_attempts + 1):
        claimed = service.claim(db, f"worker-{attempt_number}", now=now)
        attempt = service.start_attempt(db, job.id, claimed.lease_token, now=now)
        assert attempt.attempt_number == attempt_number
        job = service.fail(
            db,
            job.id,
            claimed.lease_token,
            attempt.id,
            503,
            "transient",
            "CRM temporarily unavailable",
            None,
            now=now,
        )
        if attempt_number < settings.crm_recovery_max_attempts:
            assert job.state == "retry_wait"
            job.due_at = now
            db.commit()
    assert job.state == "needs_review"
    assert db.scalar(select(func.count()).select_from(CRMWriteAttempt)) == 4
    service.requeue(db, job.id, now)
    claimed = service.claim(db, "manual-worker", now=now)
    manual_attempt = service.start_attempt(db, job.id, claimed.lease_token, now=now)
    assert manual_attempt.attempt_number == 5
    held = service.fail(
        db,
        job.id,
        claimed.lease_token,
        manual_attempt.id,
        503,
        "transient",
        "Still unavailable",
        None,
        now=now,
    )
    assert held.state == "needs_review"
    assert db.scalar(select(func.count()).select_from(CRMWriteAttempt)) == 5


def test_unrepresentable_retry_after_settles_attempt_for_review(db):
    service = RecoveryService()
    job, _ = service.admit(db, validated_payload())
    claimed = service.claim(db, "overflow-test")
    attempt = service.start_attempt(db, job.id, claimed.lease_token)

    settled = service.fail(
        db,
        job.id,
        claimed.lease_token,
        attempt.id,
        429,
        "http_429",
        "CRM write was not verified.",
        "99999999999999999999",
    )

    db.refresh(attempt)
    assert settled.state == "needs_review"
    assert settled.lease_token is None
    assert "cannot be represented safely" in settled.last_error_message
    assert attempt.finished_at is not None
    assert attempt.retry_after_raw == "99999999999999999999"
    assert attempt.retry_after_seconds is None


def test_unrepresentable_reconciliation_retry_after_releases_lease_for_review(db):
    service = RecoveryService()
    job, _ = service.admit(db, validated_payload())
    claimed = service.claim(db, "lookup-overflow-test")

    settled = service.fail_reconciliation(
        db,
        job.id,
        claimed.lease_token,
        429,
        "reconciliation_http_429",
        "CRM lookup was not verified.",
        "Fri, 31 Dec 9999 23:59:59 GMT",
    )

    assert settled.state == "needs_review"
    assert settled.lease_token is None
    assert "cannot be represented safely" in settled.last_error_message
    assert "Fri, 31 Dec 9999 23:59:59 GMT" in settled.last_error_message


def test_committed_write_with_lost_ack_is_reconciled_without_duplicate(db):
    service = RecoveryService()
    request = validated_payload()
    job, _ = service.admit(db, request)
    lead = DevelopmentCRMService().create_lead(db, request).lead
    claimed = service.claim(db, "reconciler")
    completed = service.complete(db, job.id, claimed.lease_token, lead.id)
    assert completed.completed_lead_id == lead.id
    assert db.scalar(select(func.count()).select_from(Lead)) == 1
    assert db.scalar(select(func.count()).select_from(CRMWriteAttempt)) == 0


def test_lost_ack_lookup_returns_persisted_canonical_payload_for_workflow(client, db):
    service = RecoveryService()
    prepared = validated_payload()
    job, _ = service.admit(db, prepared)
    claimed = service.claim(db, "lost-ack-writer")
    attempt = service.start_attempt(db, job.id, claimed.lease_token)
    lead = DevelopmentCRMService().create_lead(
        db, service.payload_for_job(claimed)
    ).lead
    claimed.lease_expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    db.commit()

    reclaimed = service.claim(db, "reconciliation-worker")
    lookup = client.get(f"/api/crm/leads/by-submission/{prepared.submission_id}")

    assert lookup.status_code == 200
    assert lookup.json()["intake_state"] == "replayed"
    assert lookup.json()["ai_status"] == job.payload_json["ai_status"]
    assert lookup.json()["submission_fingerprint"] == job.payload_fingerprint
    completed = service.complete(db, job.id, reclaimed.lease_token, lead.id)
    db.refresh(attempt)
    assert completed.state == "completed"
    assert attempt.outcome == "reconciled"
    assert db.scalar(select(func.count()).select_from(Lead)) == 1


def test_intake_commit_with_expired_settlement_lease_returns_queued_and_reconciles(
    client, db, monkeypatch
):
    service = RecoveryService()
    prepared = validated_payload()
    original_complete = service.complete

    def expire_before_complete(
        session,
        job_id,
        lease_token,
        lead_id,
        attempt_id=None,
        status_code=200,
        now=None,
    ):
        job = session.get(CRMWriteJob, job_id)
        job.lease_expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        session.commit()
        raise StaleLeaseError

    monkeypatch.setattr(
        "app.api.routes.recovery_service.complete", expire_before_complete
    )
    response = client.post(
        "/api/recovery/intake", json={"payload": prepared.model_dump(mode="json")}
    )

    assert response.status_code == 202
    assert response.json()["intake_state"] == "queued"
    assert "crm_lead_id" not in response.json()
    assert db.scalar(select(func.count()).select_from(Lead)) == 1
    job = db.scalar(select(CRMWriteJob).where(CRMWriteJob.submission_id == prepared.submission_id))
    reclaimed = service.claim(db, "post-commit-reconciler")
    lookup = client.get(f"/api/crm/leads/by-submission/{prepared.submission_id}")
    assert lookup.status_code == 200
    monkeypatch.setattr("app.api.routes.recovery_service.complete", original_complete)
    completed = original_complete(
        db, job.id, reclaimed.lease_token, uuid.UUID(lookup.json()["crm_lead_id"])
    )
    assert completed.state == "completed"
    assert db.scalar(select(func.count()).select_from(Lead)) == 1


def test_admission_and_completion_verify_business_identity(db):
    service = RecoveryService()
    request = validated_payload()
    DevelopmentCRMService().create_lead(db, request)
    changed = validated_payload(
        submission_id=str(request.submission_id),
        correlation_id=str(request.correlation_id),
        original_message="Different business request",
        normalized_message="Different business request",
    )
    with pytest.raises(RecoveryConflictError):
        service.admit(db, changed)

    second_request = validated_payload(
        submission_id=str(uuid.uuid4()), correlation_id=str(uuid.uuid4())
    )
    job, _ = service.admit(db, second_request)
    wrong_lead = DevelopmentCRMService().create_lead(db, second_request).lead
    wrong_lead.correlation_id = uuid.uuid4()
    db.commit()
    claimed = service.claim(db, "identity-check")
    with pytest.raises(RecoveryConflictError):
        service.complete(db, job.id, claimed.lease_token, wrong_lead.id)


def test_incident_is_deduplicated_and_only_resolution_by_verified_completion(db):
    service = RecoveryService()
    request = validated_payload()
    job, _ = service.admit(db, request)
    values = {
        "event_key": "workflow:execution:node",
        "job_id": job.id,
        "correlation_id": job.correlation_id,
        "workflow_reference": "diagnostic",
        "execution_reference": "123",
        "failed_node": "Create CRM Lead",
        "error_class": "http_429",
    }
    incident, created = service.record_incident(db, **values)
    duplicate, duplicate_created = service.record_incident(db, **values)
    assert created is True
    assert duplicate_created is False
    assert duplicate.id == incident.id
    assert incident.state == "open"
    lead = DevelopmentCRMService().create_lead(db, request).lead
    claimed = service.claim(db, "reconciler")
    service.complete(db, job.id, claimed.lease_token, lead.id)
    db.refresh(incident)
    assert incident.state == "resolved"
    assert incident.resolved_at is not None


def test_late_duplicate_incident_is_recorded_as_already_resolved(db):
    service = RecoveryService()
    request = validated_payload()
    job, _ = service.admit(db, request)
    lead = DevelopmentCRMService().create_lead(db, request).lead
    claimed = service.claim(db, "reconciler")
    service.complete(db, job.id, claimed.lease_token, lead.id)
    values = {
        "event_key": "late:execution:node",
        "job_id": job.id,
        "correlation_id": uuid.uuid4(),
        "workflow_reference": "diagnostic",
        "execution_reference": "late-123",
        "failed_node": "Create CRM Lead",
        "error_class": "http_429",
    }
    incident, created = service.record_incident(db, **values)
    duplicate, duplicate_created = service.record_incident(db, **values)
    assert created is True
    assert duplicate_created is False
    assert duplicate.id == incident.id
    assert incident.state == "resolved"
    assert incident.resolved_at is not None
    assert incident.correlation_id == job.correlation_id


def test_incident_prefers_failed_attempt_in_multi_item_execution(db):
    service = RecoveryService()
    first, _ = service.admit(db, validated_payload())
    second, _ = service.admit(
        db,
        validated_payload(
            submission_id=str(uuid.uuid4()), correlation_id=str(uuid.uuid4())
        ),
    )
    first_claim = service.claim_specific(db, first.id, "first")
    first_attempt = service.start_attempt(db, first.id, first_claim.lease_token, "shared-exec")
    first_lead = DevelopmentCRMService().create_lead(
        db, CRMLeadCreate.model_validate(first.payload_json)
    ).lead
    service.complete(
        db, first.id, first_claim.lease_token, first_lead.id, first_attempt.id, 201
    )
    second_claim = service.claim_specific(db, second.id, "second")
    second_attempt = service.start_attempt(
        db, second.id, second_claim.lease_token, "shared-exec"
    )
    service.fail(
        db,
        second.id,
        second_claim.lease_token,
        second_attempt.id,
        429,
        "http_429",
        "rate limited",
        "10",
        "shared-exec",
    )

    incident, _ = service.record_incident(
        db,
        event_key="workflow:shared-exec:write",
        job_id=None,
        correlation_id=None,
        workflow_reference="diagnostic",
        execution_reference="shared-exec",
        failed_node="CRM Write",
        error_class="http_429",
    )
    assert incident.job_id == second.id
    assert incident.correlation_id == second.correlation_id
    assert incident.state == "open"


def test_fault_controls_are_authenticated_disabled_and_batch_scoped(client, db):
    run_id = str(uuid.uuid4())
    scoped = str(uuid.uuid4())
    unscoped = str(uuid.uuid4())
    unauthorized = client.post(
        "/api/recovery/fault-runs",
        headers={"X-CRM-Adapter-Key": "wrong"},
        json={"run_id": run_id, "submission_ids": [scoped]},
    )
    assert unauthorized.status_code == 401
    created = client.post(
        "/api/recovery/fault-runs",
        json={"run_id": run_id, "submission_ids": [scoped]},
    )
    assert created.status_code == 200
    assert created.json()["active"] is False
    inspected = get_fault_run(uuid.UUID(run_id), None, db)
    assert inspected["submission_ids"] == [scoped]
    _apply_fault_quota(db, uuid.UUID(unscoped))

    overlapping_run = str(uuid.uuid4())
    assert client.post(
        "/api/recovery/fault-runs",
        json={"run_id": overlapping_run, "submission_ids": [scoped]},
    ).status_code == 200
    assert client.patch(
        f"/api/recovery/fault-runs/{run_id}", json={"active": True}
    ).status_code == 200
    conflict = client.patch(
        f"/api/recovery/fault-runs/{overlapping_run}", json={"active": True}
    )
    assert conflict.status_code == 409


def test_fixed_window_fault_returns_real_retry_after_before_write(db):
    submission_id = uuid.uuid4()
    run = CRMFaultRun(
        run_id=uuid.uuid4(),
        submission_ids=[str(submission_id)],
        active=True,
        hold_delivery=False,
        request_limit=2,
        window_seconds=10,
    )
    db.add(run)
    db.commit()
    _apply_fault_quota(db, submission_id)
    _apply_fault_quota(db, submission_id)
    with pytest.raises(HTTPException) as caught:
        _apply_fault_quota(db, submission_id)
    assert caught.value.status_code == 429
    assert int(caught.value.headers["Retry-After"]) >= 1


def test_fault_quota_never_mutates_attempt_bookkeeping(db):
    request = validated_payload()
    job, _ = RecoveryService().admit(db, request)
    run = CRMFaultRun(
        run_id=uuid.uuid4(),
        submission_ids=[str(request.submission_id)],
        active=True,
        hold_delivery=False,
        request_limit=1,
        window_seconds=10,
    )
    db.add(run)
    db.commit()
    _apply_fault_quota(db, request.submission_id)
    with pytest.raises(HTTPException):
        _apply_fault_quota(db, request.submission_id)
    db.refresh(job)
    assert job.state == "pending"
    assert job.attempt_count == 0
    assert db.scalar(select(func.count()).select_from(CRMWriteAttempt)) == 0


def test_durable_intake_429_counts_one_attempt_and_returns_truthful_queue(client, db):
    request = validated_payload()
    run = CRMFaultRun(
        run_id=uuid.uuid4(),
        submission_ids=[str(request.submission_id)],
        active=True,
        hold_delivery=False,
        request_limit=1,
        window_seconds=120,
    )
    db.add(run)
    db.commit()
    _apply_fault_quota(db, request.submission_id)

    response = client.post(
        "/api/recovery/intake", json={"payload": request.model_dump(mode="json")}
    )

    assert response.status_code == 202
    assert response.json()["intake_state"] == "queued"
    assert "crm_lead_id" not in response.json()
    assert int(response.headers["Retry-After"]) >= 1
    job = db.scalar(select(CRMWriteJob).where(CRMWriteJob.submission_id == request.submission_id))
    attempts = list(db.scalars(select(CRMWriteAttempt).where(CRMWriteAttempt.job_id == job.id)))
    assert job.attempt_count == 1
    assert job.state == "retry_wait"
    assert len(attempts) == 1
    assert attempts[0].status_code == 429
    assert attempts[0].finished_at is not None


def test_recovery_write_boundary_429_is_settled_once_with_exact_attempt(client, db):
    service = RecoveryService()
    request = validated_payload()
    job, _ = service.admit(db, request)
    run = CRMFaultRun(
        run_id=uuid.uuid4(),
        submission_ids=[str(request.submission_id)],
        active=True,
        hold_delivery=False,
        request_limit=1,
        window_seconds=120,
    )
    db.add(run)
    db.commit()
    _apply_fault_quota(db, request.submission_id)
    claimed = service.claim_specific(db, job.id, "workflow-write")
    attempt = service.start_attempt(db, job.id, claimed.lease_token, "write-429")

    rejected = client.post(
        "/api/crm/leads",
        headers={"X-Recovery-Lease-Token": str(claimed.lease_token)},
        json=request.model_dump(mode="json"),
    )
    assert rejected.status_code == 429
    retry_after = rejected.headers["Retry-After"]
    settled = client.post(
        f"/api/recovery/jobs/{job.id}/fail",
        json={
            "lease_token": str(claimed.lease_token),
            "attempt_id": str(attempt.id),
            "status_code": 429,
            "error_class": "http_429",
            "safe_message": "CRM write was not verified.",
            "retry_after": retry_after,
            "execution_reference": "write-429",
        },
    )
    assert settled.status_code == 200
    db.refresh(job)
    db.refresh(attempt)
    assert job.attempt_count == 1
    assert job.state == "retry_wait"
    assert attempt.status_code == 429
    assert attempt.retry_after_raw == retry_after
    assert attempt.finished_at is not None


def test_diagnostic_failure_owns_one_attempt_and_correlates_incident(client, db):
    service = RecoveryService()
    request = validated_payload()
    job, _ = service.admit(db, request)
    run = CRMFaultRun(
        run_id=uuid.uuid4(),
        submission_ids=[str(request.submission_id)],
        active=True,
        hold_delivery=False,
        request_limit=1,
        window_seconds=120,
    )
    db.add(run)
    db.commit()
    _apply_fault_quota(db, request.submission_id)

    rejected = client.post(
        "/api/crm/leads",
        headers={
            "X-CRM-Diagnostic": "controlled-local-fault",
            "X-N8N-Execution-Reference": "diagnostic-exec",
        },
        json=request.model_dump(mode="json"),
    )
    assert rejected.status_code == 429
    incident = client.post(
        "/api/recovery/incidents",
        json={
            "event_key": "diagnostic:diagnostic-exec:write",
            "workflow_reference": "diagnostic",
            "execution_reference": "diagnostic-exec",
            "failed_node": "Diagnostic CRM Write Without Recovery",
            "error_class": "http_429",
        },
    )
    assert incident.status_code == 201
    db.refresh(job)
    attempts = list(db.scalars(select(CRMWriteAttempt).where(CRMWriteAttempt.job_id == job.id)))
    persisted_incident = db.scalar(
        select(RecoveryIncident).where(
            RecoveryIncident.event_key == "diagnostic:diagnostic-exec:write"
        )
    )
    assert job.attempt_count == 1
    assert len(attempts) == 1
    assert attempts[0].status_code == 429
    assert persisted_incident.job_id == job.id


def test_exact_attempt_ownership_rejects_duplicate_and_stale_settlement(db):
    service = RecoveryService()
    request = validated_payload()
    job, _ = service.admit(db, request)
    first_claim = service.claim(db, "first")
    first_token = first_claim.lease_token
    first_attempt = service.start_attempt(db, job.id, first_token)
    assert service.start_attempt(db, job.id, first_token).id == first_attempt.id
    service.fail(
        db,
        job.id,
        first_token,
        first_attempt.id,
        503,
        "http_503",
        "temporary",
        None,
    )
    with pytest.raises(StaleLeaseError):
        service.fail(
            db,
            job.id,
            first_token,
            first_attempt.id,
            503,
            "http_503",
            "duplicate",
            None,
        )
    job.due_at = datetime.now(timezone.utc)
    db.commit()
    second_claim = service.claim(db, "second")
    second_attempt = service.start_attempt(db, job.id, second_claim.lease_token)
    with pytest.raises(StaleLeaseError):
        service.complete(db, job.id, first_token, uuid.uuid4(), first_attempt.id)
    assert second_attempt.attempt_number == 2


@pytest.mark.parametrize(
    ("status_code", "retry_after", "expected_state"),
    [(401, None, "blocked"), (403, None, "blocked"), (409, None, "needs_review"),
     (422, None, "needs_review"), (429, "120", "retry_wait"), (503, None, "retry_wait")],
)
def test_reconciliation_failure_classification_without_write_attempt(
    db, status_code, retry_after, expected_state
):
    service = RecoveryService()
    job, _ = service.admit(db, validated_payload())
    claimed = service.claim(db, "lookup")
    before = datetime.now(timezone.utc)
    settled = service.fail_reconciliation(
        db,
        job.id,
        claimed.lease_token,
        status_code,
        f"reconciliation_http_{status_code}",
        "lookup did not establish presence or absence",
        retry_after,
        now=before,
    )
    assert settled.state == expected_state
    assert settled.attempt_count == 0
    assert db.scalar(select(func.count()).select_from(CRMWriteAttempt)) == 0
    if status_code == 429:
        assert settled.due_at.replace(tzinfo=timezone.utc) >= before + timedelta(seconds=120)


def test_credential_failure_pauses_other_jobs_until_operator_requeues(db):
    service = RecoveryService()
    first, _ = service.admit(db, validated_payload())
    second, _ = service.admit(
        db,
        validated_payload(
            submission_id=str(uuid.uuid4()), correlation_id=str(uuid.uuid4())
        ),
    )
    claimed = service.claim_specific(db, first.id, "credential-check")
    attempt = service.start_attempt(db, first.id, claimed.lease_token)
    service.fail(
        db,
        first.id,
        claimed.lease_token,
        attempt.id,
        401,
        "http_401",
        "CRM credentials were rejected",
        None,
    )
    assert service.claim(db, "must-pause") is None
    db.refresh(second)
    assert second.state == "pending"

    service.requeue(db, first.id)
    assert service.claim(db, "resumed") is not None


def test_recovery_endpoints_require_auth(client):
    identifier = "00000000-0000-4000-8000-000000000000"
    for method, path in [
        ("post", "/api/recovery/jobs/claim"),
        ("post", f"/api/recovery/jobs/{identifier}/requeue"),
        ("get", "/api/recovery/jobs"),
        ("get", f"/api/crm/leads/by-submission/{identifier}"),
    ]:
        response = client.request(
            method,
            path,
            headers={"X-CRM-Adapter-Key": "wrong"},
            json={"worker_id": "test"} if path.endswith("claim") else None,
        )
        assert response.status_code == 401


def test_pending_trace_exists_before_lead_and_never_exposes_payload(client):
    request = payload()
    admitted = client.post("/api/recovery/jobs", json={"payload": request})
    assert admitted.status_code == 201
    trace = client.get(f"/api/traces/{request['correlation_id']}").json()
    assert trace["lead"] is None
    assert trace["recovery_jobs"][0]["state"] == "pending"
    assert "payload_json" not in trace["recovery_jobs"][0]
