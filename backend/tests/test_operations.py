import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from test_leads import payload

from app.api.operations import _execution_url
from app.models import CRMWriteAttempt, CRMWriteJob, Lead, RecoveryIncident
from app.schemas.lead import CRMLeadCreate
from app.services.crm_service import DevelopmentCRMService


def seed_job(db, *, state="pending", created_at=None, completed=False, correlation_id=None):
    created_at = created_at or datetime.now(timezone.utc)
    submission_id = uuid.uuid4()
    correlation_id = correlation_id or uuid.uuid4()
    lead = None
    if completed:
        lead = DevelopmentCRMService().create_lead(
            db,
            CRMLeadCreate.model_validate(
                payload(submission_id=str(submission_id), correlation_id=str(correlation_id))
            ),
        ).lead
    job = CRMWriteJob(
        id=uuid.uuid4(),
        submission_id=submission_id,
        correlation_id=correlation_id,
        operation_kind="create_lead",
        payload_fingerprint="a" * 64,
        payload_json={"secret_canary": "payload-secret-canary"},
        state=state,
        attempt_count=0,
        reconciliation_failure_count=0,
        due_at=created_at + timedelta(minutes=5),
        lease_token=uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
        quota_permit_lease_token=uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"),
        lease_expires_at=created_at - timedelta(minutes=1),
        completed_lead_id=lead.id if lead else None,
        last_error_class="api-key-canary",
        last_error_message="Authorization: Bearer adapter-key-canary",
        source_execution_reference="provider-response-canary",
        created_at=created_at,
        updated_at=created_at,
    )
    db.add(job)
    db.flush()
    return job, lead


def test_operations_summary_filters_pagination_and_allowlisted_detail(client, db):
    now = datetime(2026, 9, 20, 12, 0, tzinfo=timezone.utc)
    pending, _ = seed_job(db, state="pending", created_at=now)
    pending.last_error_message = "control-\x1b-canary"
    retry, _ = seed_job(db, state="retry_wait", created_at=now + timedelta(seconds=1))
    completed, lead = seed_job(
        db, state="completed", created_at=now + timedelta(seconds=2), completed=True
    )
    retry.attempt_count = 2
    db.add_all(
        [
            CRMWriteAttempt(
                id=uuid.uuid4(), job_id=retry.id, attempt_number=1, started_at=now,
                finished_at=now + timedelta(seconds=1), outcome="failed", status_code=503,
                error_class="adapter-key-canary",
                retry_after_raw="Authorization: Bearer attempt-canary",
                retry_after_seconds=None,
                execution_reference="703",
            ),
            CRMWriteAttempt(
                id=uuid.uuid4(), job_id=retry.id, attempt_number=2,
                started_at=now + timedelta(seconds=2), finished_at=now + timedelta(seconds=3),
                outcome="reconciled", status_code=200,
                error_class=None, retry_after_raw="30", retry_after_seconds=30,
                execution_reference="provider-body-canary",
            ),
            RecoveryIncident(
                id=uuid.uuid4(), event_key="linked", job_id=retry.id,
                correlation_id=retry.correlation_id, execution_reference="720", failed_node="write",
                error_class="http_503", state="resolved", resolved_at=now + timedelta(minutes=1),
                created_at=now,
            ),
            RecoveryIncident(
                id=uuid.uuid4(), event_key="open", job_id=pending.id,
                correlation_id=pending.correlation_id, workflow_reference="workflow-secret-canary",
                execution_reference="Authorization: Bearer incident-canary",
                failed_node="provider-body-canary", error_class="adapter-key-canary",
                state="open", created_at=now,
            ),
        ]
    )
    db.commit()

    summary = client.get("/api/operations/summary")
    assert summary.status_code == 200
    assert summary.json()["job_counts"] == {
        "pending": 1, "processing": 0, "retry_wait": 1, "completed": 1,
        "blocked": 0, "needs_review": 0,
    }
    assert summary.json()["open_incident_count"] == 1

    listed = client.get("/api/operations/jobs?page_size=2")
    assert listed.status_code == 200
    assert listed.json()["total"] == 3
    assert [item["id"] for item in listed.json()["items"]] == [str(completed.id), str(retry.id)]
    filtered = client.get(
        f"/api/operations/jobs?state=retry_wait&lookup_kind=job_id&lookup_id={retry.id}"
    )
    assert filtered.json()["total"] == 1
    found_submission = client.get(
        f"/api/operations/jobs?lookup_kind=submission_id&lookup_id={pending.submission_id}"
    )
    assert found_submission.json()["items"][0]["id"] == str(pending.id)
    assert client.get("/api/operations/jobs?state=not_a_state").status_code == 422
    assert client.get("/api/operations/jobs?lookup_kind=job_id").status_code == 422
    invalid_id = client.get("/api/operations/jobs?lookup_kind=job_id&lookup_id=not-a-uuid")
    assert invalid_id.status_code == 422
    assert client.get("/api/operations/jobs?page=10001").status_code == 422
    assert client.get("/api/operations/incidents?page=10001").status_code == 422
    unknown = client.get(f"/api/operations/jobs?lookup_kind=job_id&lookup_id={uuid.uuid4()}")
    assert unknown.json()["items"] == []

    detail = client.get(f"/api/operations/jobs/{retry.id}")
    assert detail.status_code == 200
    body = detail.json()
    operations_responses = [
        summary.text,
        listed.text,
        filtered.text,
        found_submission.text,
        client.get(f"/api/operations/jobs/{pending.id}").text,
        detail.text,
        client.get("/api/operations/incidents").text,
        invalid_id.text,
    ]
    serialized = "\n".join(operations_responses)
    for canary in [
        "payload-secret-canary",
        "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
        "adapter-key-canary",
        "Authorization: Bearer",
        "provider-response-canary",
        "attempt-canary",
        "workflow-secret-canary",
        "incident-canary",
        "provider-body-canary",
        "control-\\u001b-canary",
    ]:
        assert canary not in serialized
    assert "payload_json" not in body and "lease_token" not in body
    assert "quota_permit" not in serialized
    assert body["last_error_class"] == "Redacted unsafe recorded value"
    assert body["source_execution_reference"] == "Redacted unsafe recorded value"
    assert body["completed_lead"] is None
    assert body["attempts"][0]["execution_url"] == "http://localhost:5678/execution/703"
    assert body["attempts"][1]["execution_url"] is None
    assert body["incidents"][0]["state"] == "resolved"
    completed_detail = client.get(f"/api/operations/jobs/{completed.id}").json()
    assert completed_detail["completed_lead"]["id"] == str(lead.id)


def test_execution_urls_require_the_configured_loopback_editor_route(monkeypatch):
    assert _execution_url("283") == "http://localhost:5678/execution/283"
    monkeypatch.setattr("app.api.operations.settings.n8n_editor_base_url", "http://localhost:5678/editor")
    assert _execution_url("283") is None
    monkeypatch.setattr("app.api.operations.settings.n8n_editor_base_url", "http://example.test:5678")
    assert _execution_url("283") is None


def test_operations_incidents_keep_unlinked_history_and_gets_are_read_only(client, db):
    now = datetime(2026, 9, 20, 12, 0, tzinfo=timezone.utc)
    job, _ = seed_job(db, state="processing", created_at=now)
    unlinked = RecoveryIncident(
        id=uuid.uuid4(), event_key="unlinked-secret-canary", job_id=None, correlation_id=None,
        workflow_reference="workflow <script>", execution_reference="515", failed_node=None,
        error_class="provider_error", state="resolved", resolved_at=now, created_at=now,
    )
    unknown_correlation = RecoveryIncident(
        id=uuid.uuid4(), event_key="unknown-correlation", job_id=None, correlation_id=uuid.uuid4(),
        workflow_reference=None, execution_reference=None, failed_node=None,
        error_class="provider_error", state="resolved", resolved_at=now, created_at=now,
    )
    db.add_all([unlinked, unknown_correlation])
    db.commit()
    before_job = db.get(CRMWriteJob, job.id)
    before = (before_job.state, before_job.updated_at, before_job.attempt_count)
    before_counts = (
        db.query(CRMWriteJob).count(), db.query(CRMWriteAttempt).count(),
        db.query(RecoveryIncident).count(), db.query(Lead).count(),
    )

    assert client.get("/api/operations/summary").status_code == 200
    assert client.get("/api/operations/jobs").status_code == 200
    assert client.get(f"/api/operations/jobs/{job.id}").status_code == 200
    incidents = client.get("/api/operations/incidents?state=resolved").json()
    assert incidents["total"] == 2
    item = next(item for item in incidents["items"] if item["id"] == str(unlinked.id))
    assert item["id"] == str(unlinked.id)
    assert item["linked"] is False
    assert item["execution_url"] == "http://localhost:5678/execution/515"
    unknown_item = next(
        item for item in incidents["items"] if item["id"] == str(unknown_correlation.id)
    )
    assert unknown_item["linked"] is False
    assert client.get("/api/operations/incidents?state=invalid").status_code == 422

    db.expire_all()
    after_job = db.get(CRMWriteJob, job.id)
    after_counts = (
        db.query(CRMWriteJob).count(), db.query(CRMWriteAttempt).count(),
        db.query(RecoveryIncident).count(), db.query(Lead).count(),
    )
    assert (after_job.state, after_job.updated_at, after_job.attempt_count) == before
    assert after_counts == before_counts
    persisted = db.scalars(select(RecoveryIncident).where(RecoveryIncident.id == unlinked.id)).one()
    assert persisted.state == "resolved"
