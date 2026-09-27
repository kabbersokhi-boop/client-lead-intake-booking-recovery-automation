from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import func, select

import app.api.demo as demo_api
from app.config import settings
from app.db.session import get_db
from app.models import CRMWriteJob, Lead

DEMO_ORIGIN = "http://localhost:28000"


@pytest.fixture()
def demo_client(db):
    application = FastAPI()
    application.include_router(demo_api.router)

    def override_get_db():
        yield db

    application.dependency_overrides[get_db] = override_get_db
    previous_key = settings.demo_control_key
    previous_origins = settings.demo_allowed_origins
    settings.demo_control_key = SecretStr("unit-demo-control-key")
    settings.demo_allowed_origins = (
        "http://localhost:28000,http://127.0.0.1:28000"
    )
    with TestClient(application, base_url=DEMO_ORIGIN) as client:
        yield client
    settings.demo_control_key = previous_key
    settings.demo_allowed_origins = previous_origins


def _bootstrap(client: TestClient) -> str:
    response = client.post(
        "/api/demo/session",
        headers={"Origin": DEMO_ORIGIN, "X-Demo-Bootstrap": "guided-demo"},
    )
    assert response.status_code == 200
    return response.json()["csrf_token"]


def test_demo_session_is_same_origin_http_only_and_does_not_expose_control_key(
    demo_client,
):
    rejected = demo_client.post(
        "/api/demo/session",
        headers={"Origin": "https://untrusted.example", "X-Demo-Bootstrap": "guided-demo"},
    )
    assert rejected.status_code == 403

    response = demo_client.post(
        "/api/demo/session",
        headers={"Origin": DEMO_ORIGIN, "X-Demo-Bootstrap": "guided-demo"},
    )
    assert response.status_code == 200
    assert response.json()["csrf_token"] != "unit-demo-control-key"
    assert "unit-demo-control-key" not in response.text
    cookie = response.headers["set-cookie"].lower()
    assert "httponly" in cookie
    assert "samesite=strict" in cookie
    assert response.headers["cache-control"] == "no-store"
    second_tab = demo_client.post(
        "/api/demo/session",
        headers={"Origin": DEMO_ORIGIN, "X-Demo-Bootstrap": "guided-demo"},
    )
    assert second_tab.json()["csrf_token"] == response.json()["csrf_token"]


def test_unauthorized_scenarios_stop_before_fault_or_application_mutation(
    demo_client, db, monkeypatch
):
    calls = {"arm": 0, "intake": 0}

    def unexpected_arm(*args, **kwargs):
        calls["arm"] += 1
        raise AssertionError("fault control must not run")

    def unexpected_intake(*args, **kwargs):
        calls["intake"] += 1
        raise AssertionError("intake must not run")

    monkeypatch.setattr(demo_api, "_arm_fault", unexpected_arm)
    monkeypatch.setattr(demo_api, "_post_intake", unexpected_intake)
    before = {
        "leads": db.scalar(select(func.count()).select_from(Lead)),
        "jobs": db.scalar(select(func.count()).select_from(CRMWriteJob)),
    }

    missing_session = demo_client.post(
        "/api/demo/scenarios/rate_limit", headers={"Origin": DEMO_ORIGIN}
    )
    csrf_token = _bootstrap(demo_client)
    untrusted_origin = demo_client.post(
        "/api/demo/scenarios/rate_limit",
        headers={"Origin": "https://untrusted.example", "X-Demo-CSRF": csrf_token},
    )
    missing_origin = demo_client.post(
        "/api/demo/scenarios/rate_limit", headers={"X-Demo-CSRF": csrf_token}
    )

    assert [
        missing_session.status_code,
        untrusted_origin.status_code,
        missing_origin.status_code,
    ] == [403, 403, 403]
    assert calls == {"arm": 0, "intake": 0}
    assert db.scalar(select(func.count()).select_from(Lead)) == before["leads"]
    assert db.scalar(select(func.count()).select_from(CRMWriteJob)) == before["jobs"]


def _attempts(second_started_at: datetime):
    failed_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return [
        SimpleNamespace(
            status_code=429,
            error_class="highlevel_rate_limited",
            retry_after_seconds=2,
            finished_at=failed_at,
            started_at=failed_at - timedelta(milliseconds=10),
            outcome="failed",
        ),
        SimpleNamespace(
            status_code=200,
            error_class=None,
            retry_after_seconds=None,
            finished_at=second_started_at + timedelta(milliseconds=10),
            started_at=second_started_at,
            outcome="completed",
        ),
    ]


def _proof(scenario, **changes):
    created_identity = {
        "crm_lead_id": "00000000-0000-4000-8000-000000000001",
        "submission_id": "00000000-0000-4000-8000-000000000002",
        "correlation_id": "00000000-0000-4000-8000-000000000003",
        "submission_fingerprint": "a" * 64,
        "intake_state": "created",
    }
    values = {
        "initial_status": 201,
        "initial_job_state": "completed",
        "initial_body": created_identity,
        "replay_status": 200,
        "replay_body": {**created_identity, "intake_state": "replayed"},
        "lead": SimpleNamespace(ai_status="fallback_unavailable", needs_review=True),
        "attempts": [],
        "due_at": None,
        "opportunity_posts": [],
    }
    values.update(changes)
    return demo_api._scenario_proof(scenario, **values)[0]


def test_scenario_proof_rejects_short_retry_ai_without_review_and_changed_replay():
    failed_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
    on_time = _attempts(failed_at + timedelta(seconds=2))
    rate_proof = _proof(
        "rate_limit",
        initial_status=202,
        initial_job_state="retry_wait",
        attempts=on_time,
        due_at=failed_at + timedelta(seconds=2),
    )
    assert all(rate_proof.values())

    early_proof = _proof(
        "rate_limit",
        initial_status=202,
        initial_job_state="retry_wait",
        attempts=_attempts(failed_at + timedelta(seconds=1)),
        due_at=failed_at + timedelta(seconds=2),
    )
    assert early_proof["retry_after_honored"] is False

    ai_proof = _proof(
        "ai_unavailable",
        lead=SimpleNamespace(ai_status="fallback_unavailable", needs_review=False),
    )
    assert ai_proof["human_review_persisted"] is False

    changed_replay = {
        "crm_lead_id": "00000000-0000-4000-8000-000000000099",
        "submission_id": "00000000-0000-4000-8000-000000000002",
        "correlation_id": "00000000-0000-4000-8000-000000000003",
        "submission_fingerprint": "a" * 64,
        "intake_state": "replayed",
    }
    duplicate_proof = _proof("duplicate", replay_body=changed_replay)
    assert duplicate_proof["same_original_operation"] is False

    changed_fingerprint = {
        **changed_replay,
        "crm_lead_id": "00000000-0000-4000-8000-000000000001",
        "submission_fingerprint": "b" * 64,
    }
    fingerprint_proof = _proof("duplicate", replay_body=changed_fingerprint)
    assert fingerprint_proof["same_original_operation"] is False


def test_n8n_webhook_readiness_distinguishes_registered_post_route():
    registered = httpx.Response(
        404,
        json={
            "message": (
                "This webhook is not registered for GET requests. "
                "Did you mean to make a POST request?"
            )
        },
    )
    missing = httpx.Response(
        404,
        json={"message": 'The requested webhook "GET missing" is not registered.'},
    )
    assert demo_api._registered_post_webhook(registered) is True
    assert demo_api._registered_post_webhook(missing) is False
