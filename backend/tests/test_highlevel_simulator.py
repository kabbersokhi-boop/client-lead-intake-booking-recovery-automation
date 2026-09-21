import os
import socket
import subprocess
import sys
import time
import uuid
from pathlib import Path
from urllib.request import urlopen

import httpx
import pytest


@pytest.fixture(scope="session")
def simulator_base_url():
    with socket.socket() as reservation:
        reservation.bind(("127.0.0.1", 0))
        port = reservation.getsockname()[1]
    backend_dir = Path(__file__).resolve().parents[1]
    environment = {
        **os.environ,
        "HIGHLEVEL_SIMULATOR_TOKEN": "unit-token",
        "HIGHLEVEL_SIMULATOR_FAULT_TIMEOUT_SECONDS": "0.01",
    }
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "simulator.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--log-level",
            "error",
        ],
        cwd=backend_dir,
        env=environment,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    base_url = f"http://127.0.0.1:{port}"
    for _ in range(100):
        try:
            with urlopen(f"{base_url}/health", timeout=0.2):
                break
        except OSError:
            if process.poll() is not None:
                raise RuntimeError("Simulator test process exited during startup")
            time.sleep(0.05)
    else:
        process.terminate()
        raise RuntimeError("Simulator test process did not become healthy")
    yield base_url
    process.terminate()
    process.wait(timeout=5)


@pytest.fixture()
def simulator(simulator_base_url):
    with httpx.Client(base_url=simulator_base_url) as client:
        client.post("/simulator/api/reset")
        yield client
        client.post("/simulator/api/reset")


def headers(**changes):
    values = {
        "Authorization": "Bearer unit-token",
        "Version": "v3",
    }
    values.update(changes)
    return values


def contact_body(**changes):
    values = {
        "name": "Morgan Heat",
        "email": "morgan.simulator@example.com",
        "phone": "+16045550177",
        "locationId": "sim_location_reference",
        "source": "local-contract-reference",
        "createNewIfDuplicateAllowed": False,
        "customFields": [
            {"id": "sim_cf_submission_id", "fieldValue": str(uuid.uuid4())},
            {"id": "sim_cf_correlation_id", "fieldValue": str(uuid.uuid4())},
        ],
    }
    values.update(changes)
    return values


def create_contact(simulator, body=None):
    return simulator.post(
        "/contacts/upsert", headers=headers(), json=body or contact_body()
    )


def test_simulator_requires_auth_and_version_and_strict_body(simulator):
    body = contact_body()
    assert simulator.post("/contacts/upsert", json=body).status_code == 401
    assert (
        simulator.post(
            "/contacts/upsert",
            headers=headers(Version="2023-02-21"),
            json=body,
        ).status_code
        == 422
    )
    invalid = {**body, "inventedField": "not documented for this subset"}
    rejected = create_contact(simulator, invalid)
    assert rejected.status_code == 422
    assert rejected.json()["statusCode"] == 422
    assert rejected.json()["error"] == "Unprocessable Entity"


def test_simulator_rejects_non_e164_lookup_and_undocumented_opportunity_status(
    simulator,
):
    lookup = simulator.get(
        "/contacts/lookup",
        headers=headers(),
        params={"locationId": "sim_location_reference", "phone": "604-555-0177"},
    )
    assert lookup.status_code == 422
    invalid_cursor = simulator.get(
        "/contacts/lookup",
        headers=headers(),
        params={
            "locationId": "sim_location_reference",
            "email": "morgan.simulator@example.com",
            "nextCursor": "not-a-simulator-cursor",
        },
    )
    assert invalid_cursor.status_code == 422

    contact = create_contact(simulator).json()["contact"]
    opportunity = simulator.post(
        "/opportunities/",
        headers=headers(),
        json={
            "pipelineId": "sim_pipeline_hvac",
            "locationId": "sim_location_reference",
            "name": "Invalid undocumented status",
            "pipelineStageId": "sim_stage_new_lead",
            "status": "pending",
            "contactId": contact["id"],
            "customFields": [
                {"id": "sim_of_submission_id", "fieldValue": str(uuid.uuid4())}
            ],
        },
    )
    assert opportunity.status_code == 422
    assert opportunity.json()["statusCode"] == 422


def test_contact_upsert_lookup_and_opportunity_contract_are_replay_safe(simulator):
    body = contact_body()
    first = create_contact(simulator, body)
    replay = create_contact(simulator, body)

    assert first.status_code == 200
    assert first.json()["new"] is True
    assert replay.json()["new"] is False
    assert first.json()["contact"]["id"].startswith("sim_contact_")
    assert replay.json()["contact"]["id"] == first.json()["contact"]["id"]

    lookup = simulator.get(
        "/contacts/lookup",
        headers=headers(),
        params={
            "locationId": "sim_location_reference",
            "email": body["email"],
        },
    )
    assert len(lookup.json()["contacts"]) == 1

    opportunity = simulator.post(
        "/opportunities/",
        headers=headers(),
        json={
            "pipelineId": "sim_pipeline_hvac",
            "locationId": "sim_location_reference",
            "name": "Morgan Heat - HVAC enquiry",
            "pipelineStageId": "sim_stage_new_lead",
            "status": "open",
            "contactId": first.json()["contact"]["id"],
            "customFields": [
                {
                    "id": "sim_of_submission_id",
                    "fieldValue": body["customFields"][0]["fieldValue"],
                }
            ],
        },
    )
    assert opportunity.status_code == 201
    assert opportunity.json()["opportunity"]["id"].startswith("sim_opportunity_")

    search = simulator.get(
        "/opportunities/search",
        headers=headers(),
        params={
            "locationId": "sim_location_reference",
            "pipelineId": "sim_pipeline_hvac",
            "contactId": first.json()["contact"]["id"],
            "status": "all",
        },
    )
    assert len(search.json()["opportunities"]) == 1
    assert search.json()["meta"] == {"total": 1, "currentPage": 1}


def test_one_shot_429_preserves_retry_after_and_resets(simulator):
    simulator.post(
        "/simulator/api/fault", json={"mode": "rate_limited", "retry_after": 9}
    )
    rejected = create_contact(simulator)
    accepted = create_contact(simulator)

    assert rejected.status_code == 429
    assert rejected.headers["Retry-After"] == "9"
    assert rejected.headers["X-Simulator-Request-Id"].startswith("sim_req_")
    assert accepted.status_code == 200
    snapshot = simulator.get("/simulator/api/state").json()
    assert snapshot["fault"]["mode"] == "normal"
    rate_limit_event = next(event for event in snapshot["events"] if event["status"] == 429)
    assert rate_limit_event["retryAfter"] == "9"


@pytest.mark.parametrize(
    ("mode", "status_code"),
    [("unauthorized", 401), ("server_error", 500)],
)
def test_other_one_shot_faults_reset(simulator, mode, status_code):
    simulator.post(
        "/simulator/api/fault", json={"mode": mode, "retry_after": 5}
    )
    assert create_contact(simulator).status_code == status_code
    assert create_contact(simulator).status_code == 200


def test_timeout_fault_is_one_shot(simulator):
    simulator.post(
        "/simulator/api/fault", json={"mode": "timeout", "retry_after": 5}
    )
    assert create_contact(simulator).status_code == 504
    assert create_contact(simulator).status_code == 200


def test_event_log_is_allowlisted_and_never_contains_authorization(simulator):
    create_contact(simulator)
    snapshot = simulator.get("/simulator/api/state").json()
    serialized = str(snapshot["events"])

    assert snapshot["events"][0]["path"] == "/contacts/upsert"
    assert "Authorization" not in serialized
    assert "unit-token" not in serialized
    assert "headers" not in serialized


def test_reset_is_isolated_to_simulator_state(simulator):
    create_contact(simulator)
    assert simulator.get("/simulator/api/state").json()["contacts"]
    assert simulator.post("/simulator/api/reset").json() == {"reset": True}
    snapshot = simulator.get("/simulator/api/state").json()
    assert snapshot["contacts"] == []
    assert snapshot["opportunities"] == []
    assert snapshot["events"] == []
