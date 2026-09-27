import hashlib
import hmac
import secrets
import time
import uuid
from datetime import datetime, timezone
from typing import Literal

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.db.session import get_db
from app.models import CRMWriteAttempt, CRMWriteJob, Lead

router = APIRouter(prefix="/api/demo", tags=["isolated-demo"])

Scenario = Literal[
    "normal", "duplicate", "ai_unavailable", "rate_limit", "lost_acknowledgement"
]
DEMO_SESSION_COOKIE = "hvac_guided_demo_session"
N8N_REQUIRED_WEBHOOKS = {
    "n8n lead intake webhook": "lead-intake",
    "n8n recovery webhook": "crm-write-recovery-dispatch",
}


def _allowed_origins() -> set[str]:
    return {
        origin.strip().rstrip("/")
        for origin in settings.demo_allowed_origins.split(",")
        if origin.strip()
    }


def _require_allowed_origin(request: Request) -> None:
    origin = request.headers.get("Origin", "").rstrip("/")
    if origin not in _allowed_origins():
        raise HTTPException(status_code=403, detail="Trusted demo origin required")


def _session_token(session_id: str) -> str:
    key = settings.demo_control_key.get_secret_value().encode()
    return hmac.new(key, f"demo-session:{session_id}".encode(), hashlib.sha256).hexdigest()


def _session_is_fresh(session_id: str) -> bool:
    try:
        issued_at_text, nonce = session_id.split(".", 1)
        issued_at = int(issued_at_text)
    except (TypeError, ValueError):
        return False
    age = int(time.time()) - issued_at
    return len(nonce) >= 32 and 0 <= age <= settings.demo_session_ttl_seconds


def _require_demo_session(request: Request) -> None:
    _require_allowed_origin(request)
    session_id = request.cookies.get(DEMO_SESSION_COOKIE, "")
    presented = request.headers.get("X-Demo-CSRF", "")
    if not _session_is_fresh(session_id) or not hmac.compare_digest(
        presented, _session_token(session_id)
    ):
        raise HTTPException(status_code=403, detail="Valid demo session required")


@router.post("/session")
def create_demo_session(request: Request, response: Response) -> dict:
    _require_allowed_origin(request)
    if request.headers.get("X-Demo-Bootstrap") != "guided-demo":
        raise HTTPException(status_code=403, detail="Demo bootstrap header required")
    session_id = request.cookies.get(DEMO_SESSION_COOKIE, "")
    if not _session_is_fresh(session_id):
        session_id = f"{int(time.time())}.{secrets.token_urlsafe(32)}"
    response.set_cookie(
        DEMO_SESSION_COOKIE,
        session_id,
        max_age=settings.demo_session_ttl_seconds,
        httponly=True,
        samesite="strict",
        secure=False,
        path="/api/demo",
    )
    response.headers["Cache-Control"] = "no-store"
    return {
        "csrf_token": _session_token(session_id),
        "expires_in_seconds": settings.demo_session_ttl_seconds,
    }


def _custom_value(record: dict, field_id: str) -> str | None:
    for field in record.get("customFields", []):
        if isinstance(field, dict) and field.get("id") == field_id:
            return field.get("value") or field.get("fieldValue")
    return None


def _client() -> httpx.Client:
    return httpx.Client(timeout=20, trust_env=False)


def _registered_post_webhook(response: httpx.Response) -> bool:
    if response.status_code != 404:
        return False
    try:
        message = response.json().get("message", "")
    except ValueError:
        return False
    return "not registered for GET requests" in message


def _readiness() -> dict:
    checks: dict[str, dict] = {}
    with _client() as client:
        for name, url in {
            "n8n process": f"{settings.demo_n8n_base_url}/healthz",
            "simulator": f"{settings.demo_simulator_control_url}/health",
            "deterministic AI": f"{settings.demo_ai_base_url}/health",
            "Mailpit": f"{settings.demo_mailpit_base_url}/livez",
        }.items():
            try:
                response = client.get(url)
                checks[name] = {
                    "ready": response.status_code == 200,
                    "status": response.status_code,
                }
            except httpx.HTTPError as error:
                checks[name] = {"ready": False, "error": type(error).__name__}
        for name, path in N8N_REQUIRED_WEBHOOKS.items():
            try:
                response = client.get(f"{settings.demo_n8n_base_url}/webhook/{path}")
                checks[name] = {
                    "ready": _registered_post_webhook(response),
                    "status": response.status_code,
                    "method": "POST",
                    "path": path,
                }
            except httpx.HTTPError as error:
                checks[name] = {"ready": False, "error": type(error).__name__}
    return checks


@router.get("/readiness")
def readiness(db: Session = Depends(get_db)) -> dict:
    database_ready = db.scalar(select(func.count()).select_from(CRMWriteJob)) is not None
    checks = {"database": {"ready": database_ready}, **_readiness()}
    return {
        "ready": all(item["ready"] for item in checks.values()),
        "mode": "isolated-local-demo",
        "external_accounts_required": False,
        "checks": checks,
    }


def _arm_fault(client: httpx.Client, scenario: Scenario, submission_id: uuid.UUID) -> bool:
    if scenario not in {"rate_limit", "lost_acknowledgement"}:
        return False
    mode = "rate_limited" if scenario == "rate_limit" else "lost_acknowledgement"
    target = "/contacts/upsert" if scenario == "rate_limit" else "/opportunities/"
    response = client.post(
        f"{settings.demo_simulator_control_url}/simulator/api/fault",
        headers={"X-Demo-Control-Key": settings.demo_control_key.get_secret_value()},
        json={
            "mode": mode,
            "retry_after": 2,
            "submission_id": str(submission_id),
            "target_path": target,
        },
    )
    response.raise_for_status()
    return True


def _clear_fault(client: httpx.Client, scenario: Scenario, submission_id: uuid.UUID) -> None:
    target = "/contacts/upsert" if scenario == "rate_limit" else "/opportunities/"
    response = client.post(
        f"{settings.demo_simulator_control_url}/simulator/api/fault",
        headers={"X-Demo-Control-Key": settings.demo_control_key.get_secret_value()},
        json={
            "mode": "normal",
            "retry_after": 2,
            "submission_id": str(submission_id),
            "target_path": target,
        },
    )
    response.raise_for_status()


def _post_intake(client: httpx.Client, payload: dict) -> tuple[int, dict]:
    response = client.post(
        f"{settings.demo_n8n_base_url}/webhook/lead-intake", json=payload, timeout=20
    )
    try:
        body = response.json()
    except ValueError as error:
        raise HTTPException(
            status_code=502, detail="n8n returned a non-JSON intake result"
        ) from error
    return response.status_code, body


def _recover_until_terminal(
    client: httpx.Client, db: Session, submission_id: uuid.UUID
) -> CRMWriteJob:
    for _ in range(12):
        db.expire_all()
        job = db.scalar(select(CRMWriteJob).where(CRMWriteJob.submission_id == submission_id))
        if job and job.state in {"completed", "blocked", "needs_review"}:
            return job
        if job and job.due_at:
            due_at = job.due_at
            if due_at.tzinfo is None:
                due_at = due_at.replace(tzinfo=timezone.utc)
            remaining = (due_at - datetime.now(timezone.utc)).total_seconds()
            if remaining > 0:
                time.sleep(min(remaining + 0.15, 2.25))
        response = client.post(
            f"{settings.demo_n8n_base_url}/webhook/crm-write-recovery-dispatch",
            json={},
            timeout=20,
        )
        if response.status_code >= 500:
            time.sleep(0.25)
    db.expire_all()
    job = db.scalar(select(CRMWriteJob).where(CRMWriteJob.submission_id == submission_id))
    if not job:
        raise HTTPException(status_code=502, detail="No durable recovery job was observed")
    return job


def _aware(value: datetime | None) -> datetime | None:
    if value is not None and value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def _iso(value: datetime | None) -> str | None:
    aware = _aware(value)
    return aware.isoformat() if aware is not None else None


def _operation_identity(body: dict | None) -> dict[str, str] | None:
    if not isinstance(body, dict):
        return None
    fields = (
        "crm_lead_id",
        "submission_id",
        "correlation_id",
        "submission_fingerprint",
    )
    identity = {field: body.get(field) for field in fields}
    if not all(isinstance(value, str) and value for value in identity.values()):
        return None
    return identity


def _retry_timing(attempts: list[CRMWriteAttempt], due_at: datetime | None) -> dict:
    evidence = {
        "failed_attempt_finished_at": None,
        "scheduled_retry_at": _iso(due_at),
        "next_attempt_started_at": None,
        "required_delay_seconds": None,
        "scheduled_delay_seconds": None,
        "observed_delay_seconds": None,
        "honored": False,
    }
    if len(attempts) < 2:
        return evidence
    failed_at = _aware(attempts[0].finished_at)
    next_started_at = _aware(attempts[1].started_at)
    scheduled_at = _aware(due_at)
    required = attempts[0].retry_after_seconds
    evidence.update(
        {
            "failed_attempt_finished_at": _iso(failed_at),
            "next_attempt_started_at": _iso(next_started_at),
            "required_delay_seconds": required,
        }
    )
    if failed_at is None or next_started_at is None or scheduled_at is None or required is None:
        return evidence
    scheduled_delay = (scheduled_at - failed_at).total_seconds()
    observed_delay = (next_started_at - failed_at).total_seconds()
    evidence.update(
        {
            "scheduled_delay_seconds": round(scheduled_delay, 6),
            "observed_delay_seconds": round(observed_delay, 6),
            "honored": (
                scheduled_delay >= required
                and next_started_at >= scheduled_at
                and observed_delay >= required
            ),
        }
    )
    return evidence


def _scenario_proof(
    scenario: Scenario,
    *,
    initial_status: int,
    initial_job_state: str,
    initial_body: dict,
    replay_status: int | None,
    replay_body: dict | None,
    lead: Lead | None,
    attempts: list[CRMWriteAttempt],
    due_at: datetime | None,
    opportunity_posts: list[dict],
) -> tuple[dict[str, bool], dict]:
    initial_identity = _operation_identity(initial_body)
    replay_identity = _operation_identity(replay_body)
    retry_timing = _retry_timing(attempts, due_at)
    proof = {
        "normal": {
            "created_response": initial_status == 201,
            "completed_during_intake": initial_job_state == "completed",
        },
        "duplicate": {
            "created_then_replayed": (
                initial_status == 201
                and replay_status == 200
                and replay_body is not None
                and replay_body.get("intake_state") == "replayed"
            ),
            "same_original_operation": (
                initial_identity is not None
                and replay_identity is not None
                and initial_identity == replay_identity
            ),
        },
        "ai_unavailable": {
            "request_preserved": initial_status == 201,
            "fallback_persisted": lead is not None
            and lead.ai_status == "fallback_unavailable",
            "human_review_persisted": lead is not None and lead.needs_review is True,
        },
        "rate_limit": {
            "queued_after_429": initial_status == 202
            and initial_job_state == "retry_wait",
            "retry_after_recorded": (
                len(attempts) >= 2
                and attempts[0].status_code == 429
                and attempts[0].error_class == "highlevel_rate_limited"
                and attempts[0].retry_after_seconds == 2
            ),
            "retry_after_honored": retry_timing["honored"] is True,
            "later_attempt_completed": len(attempts) >= 2
            and attempts[-1].outcome == "completed",
        },
        "lost_acknowledgement": {
            "queued_after_timeout": initial_status == 202
            and initial_job_state == "retry_wait",
            "timeout_recorded": any(
                item.error_class == "highlevel_timeout" for item in attempts
            ),
            "one_remote_commit": len(opportunity_posts) == 1
            and opportunity_posts[0].get("status") == 201,
        },
    }[scenario]
    return proof, {
        "initial_operation_identity": initial_identity,
        "replay_operation_identity": replay_identity,
        "retry_timing": retry_timing,
    }


@router.post("/scenarios/{scenario}", dependencies=[Depends(_require_demo_session)])
def run_scenario(scenario: Scenario, db: Session = Depends(get_db)) -> dict:
    submission_id = uuid.uuid4()
    correlation_id = uuid.uuid4()
    marker = " [DEMO-AI-TIMEOUT]" if scenario == "ai_unavailable" else ""
    payload = {
        "submission_id": str(submission_id),
        "correlation_id": str(correlation_id),
        "received_at": datetime.now(timezone.utc).isoformat(),
        "full_name": f"Demo {scenario.replace('_', ' ').title()}",
        "email": f"demo-{submission_id.hex[:12]}@example.com",
        "phone": f"+1604{submission_id.int % 10_000_000:07d}",
        "message": (
            "Our furnace stopped heating in Surrey. Tuesday afternoon would help." + marker
        ),
    }
    with _client() as client:
        fault_armed = _arm_fault(client, scenario, submission_id)
        try:
            initial_status, initial_body = _post_intake(client, payload)
        finally:
            if fault_armed:
                _clear_fault(client, scenario, submission_id)
        replay_status = None
        replay_body = None
        if scenario == "duplicate":
            replay_status, replay_body = _post_intake(client, payload)

        db.expire_all()
        job = db.scalar(select(CRMWriteJob).where(CRMWriteJob.submission_id == submission_id))
        if not job:
            raise HTTPException(status_code=502, detail="n8n did not create a durable recovery job")
        initial_job_state = job.state
        if job.state != "completed":
            job = _recover_until_terminal(client, db, submission_id)

        simulator = client.get(
            f"{settings.demo_simulator_control_url}/simulator/api/state"
        ).json()

    db.expire_all()
    lead_count = db.scalar(
        select(func.count()).select_from(Lead).where(Lead.submission_id == submission_id)
    ) or 0
    attempts = list(
        db.scalars(
            select(CRMWriteAttempt)
            .where(CRMWriteAttempt.job_id == job.id)
            .order_by(CRMWriteAttempt.attempt_number)
        )
    )
    contacts = [
        item
        for item in simulator.get("contacts", [])
        if _custom_value(item, "sim_cf_submission_id") == str(submission_id)
    ]
    opportunities = [
        item
        for item in simulator.get("opportunities", [])
        if _custom_value(item, "sim_of_submission_id") == str(submission_id)
    ]
    matching_events = [
        item
        for item in simulator.get("events", [])
        if item.get("submissionReference") == str(submission_id)
    ]
    lead = db.scalar(select(Lead).where(Lead.submission_id == submission_id))
    ai_status = lead.ai_status if lead else None
    needs_review = lead.needs_review if lead else None
    expected_ai = "fallback_unavailable" if scenario == "ai_unavailable" else "enriched"
    opportunity_posts = [
        item
        for item in matching_events
        if item.get("method") == "POST" and item.get("path") == "/opportunities/"
    ]
    scenario_proof, scenario_details = _scenario_proof(
        scenario,
        initial_status=initial_status,
        initial_job_state=initial_job_state,
        initial_body=initial_body,
        replay_status=replay_status,
        replay_body=replay_body,
        lead=lead,
        attempts=attempts,
        due_at=job.due_at,
        opportunity_posts=opportunity_posts,
    )
    scenario_verified = all(scenario_proof.values())
    verified = (
        job.state == "completed"
        and lead_count == 1
        and len(contacts) == 1
        and len(opportunities) == 1
        and ai_status == expected_ai
        and scenario_verified
    )
    timeline = [
        {"step": "n8n accepted the synthetic request", "observed": initial_status},
        {"step": "PostgreSQL durable job after intake", "observed": initial_job_state},
    ]
    if replay_status is not None:
        timeline.append({"step": "Equivalent request replay", "observed": replay_status})
    if initial_job_state != job.state:
        timeline.append({"step": "Recovery worker settled the same job", "observed": job.state})
    timeline.extend(
        [
            {"step": "Local logical leads", "observed": lead_count},
            {"step": "Simulated HighLevel Contacts", "observed": len(contacts)},
            {"step": "Simulated HighLevel Opportunities", "observed": len(opportunities)},
        ]
    )
    return {
        "scenario": scenario,
        "verified": verified,
        "submission_id": submission_id,
        "correlation_id": correlation_id,
        "business_explanation": {
            "normal": (
                "A valid enquiry crosses every local boundary and creates one CRM projection."
            ),
            "duplicate": (
                "An equivalent delivery reuses the original business operation without duplication."
            ),
            "ai_unavailable": (
                "Optional model failure preserves the enquiry and flags it for human review."
            ),
            "rate_limit": (
                "A scoped 429 queues durable work, honors Retry-After, and later recovers."
            ),
            "lost_acknowledgement": (
                "The remote effect commits before the reply is lost; recovery reconciles it "
                "instead of creating another effect."
            ),
        }[scenario],
        "timeline": timeline,
        "authoritative_evidence": {
            "job_id": str(job.id),
            "operation_kind": job.operation_kind,
            "payload_fingerprint": job.payload_fingerprint,
            "source_execution_reference": job.source_execution_reference,
            "scenario_proof": scenario_proof,
            "initial_http_status": initial_status,
            "initial_intake_state": initial_body.get("intake_state"),
            "initial_job_state": initial_job_state,
            "final_job_state": job.state,
            "attempts": [
                {
                    "attempt_id": str(item.id),
                    "number": item.attempt_number,
                    "started_at": _iso(item.started_at),
                    "finished_at": _iso(item.finished_at),
                    "outcome": item.outcome,
                    "status_code": item.status_code,
                    "error_class": item.error_class,
                    "retry_after_seconds": item.retry_after_seconds,
                    "execution_reference": item.execution_reference,
                }
                for item in attempts
            ],
            "ai_status": ai_status,
            "needs_review": needs_review,
            "lead_count": lead_count,
            "contact_count": len(contacts),
            "opportunity_count": len(opportunities),
            "simulator_events": [
                {
                    "request_id": item.get("requestId"),
                    "method": item.get("method"),
                    "path": item.get("path"),
                    "status": item.get("status"),
                }
                for item in reversed(matching_events)
            ],
            "replay_http_status": replay_status,
            "replay_intake_state": replay_body.get("intake_state") if replay_body else None,
            **scenario_details,
        },
    }
