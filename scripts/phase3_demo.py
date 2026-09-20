#!/usr/bin/env python3
import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = Path(
    os.environ.get("PHASE3_MANIFEST", ROOT / "docs/fixtures/phase-3-manifest.json")
)
BACKEND_URL = os.environ.get("PHASE3_BACKEND_URL", "http://localhost:18000")
INTAKE_URL = os.environ.get("PHASE3_INTAKE_URL", "http://localhost:5678/webhook/lead-intake")
DIAGNOSTIC_URL = os.environ.get(
    "PHASE3_DIAGNOSTIC_URL",
    "http://localhost:5678/webhook/controlled-crm-rate-limit-diagnostic",
)
RECOVERY_URL = os.environ.get(
    "PHASE3_RECOVERY_URL", "http://localhost:5678/webhook/crm-write-recovery-dispatch"
)


def request(url, method="GET", body=None, authenticated=False, allow_error=False):
    headers = {"Accept": "application/json"}
    if body is not None:
        headers["Content-Type"] = "application/json"
    if authenticated:
        headers["X-CRM-Adapter-Key"] = os.environ["CRM_ADAPTER_API_KEY"]
    encoded = json.dumps(body).encode() if body is not None else None
    try:
        with urlopen(Request(url, data=encoded, headers=headers, method=method), timeout=40) as result:
            raw = result.read()
            return result.status, json.loads(raw) if raw else None
    except HTTPError as error:
        raw = error.read()
        parsed = json.loads(raw) if raw else None
        if allow_error:
            return error.code, parsed
        raise RuntimeError(f"HTTP {error.code}: {parsed}") from error


def load_manifest():
    return json.loads(MANIFEST_PATH.read_text())


def control(manifest, **changes):
    return request(
        f"{BACKEND_URL}/api/recovery/fault-runs/{manifest['run_id']}",
        method="PATCH",
        body=changes,
        authenticated=True,
    )[1]


def fault_state(manifest, allow_missing=False):
    status_code, result = request(
        f"{BACKEND_URL}/api/recovery/fault-runs/{manifest['run_id']}",
        authenticated=True,
        allow_error=True,
    )
    if status_code == 404 and allow_missing:
        return None
    if status_code != 200:
        raise RuntimeError(f"Fault-run inspection failed with HTTP {status_code}")
    return result


def register(manifest):
    status_code, _ = request(
        f"{BACKEND_URL}/api/recovery/fault-runs",
        method="POST",
        body={
            "run_id": manifest["run_id"],
            "submission_ids": [item["submission_id"] for item in manifest["enquiries"]],
            "request_limit": 5,
            "window_seconds": 10,
            "hold_delivery": True,
        },
        authenticated=True,
        allow_error=True,
    )
    if status_code not in {200, 409}:
        raise RuntimeError(f"Fault-run registration failed with HTTP {status_code}")
    if status_code == 409:
        current = fault_state(manifest)
        expected_ids = {item["submission_id"] for item in manifest["enquiries"]}
        if (
            set(current["submission_ids"]) != expected_ids
            or current["request_limit"] != 5
            or current["window_seconds"] != 10
        ):
            raise RuntimeError(
                "Existing fault run does not match this manifest and quota configuration"
            )
    return status_code == 200


def scoped_state(manifest):
    expected_by_submission = {
        item["submission_id"]: item for item in manifest["enquiries"]
    }
    identifiers = set(expected_by_submission)
    jobs = request(f"{BACKEND_URL}/api/recovery/jobs", authenticated=True)[1]
    leads = request(f"{BACKEND_URL}/api/leads")[1]
    scoped_jobs = [job for job in jobs if job["submission_id"] in identifiers]
    scoped_leads = [lead for lead in leads if lead["submission_id"] in identifiers]
    counts = {}
    for job in scoped_jobs:
        counts[job["state"]] = counts.get(job["state"], 0) + 1
    lead_counts = {}
    for lead in scoped_leads:
        lead_counts[lead["submission_id"]] = lead_counts.get(lead["submission_id"], 0) + 1
    lead_by_submission = {lead["submission_id"]: lead for lead in scoped_leads}
    job_by_submission = {job["submission_id"]: job for job in scoped_jobs}
    identity_mismatches = []
    for submission_id, expected in expected_by_submission.items():
        job = job_by_submission.get(submission_id)
        lead = lead_by_submission.get(submission_id)
        if job and job["correlation_id"] != expected["correlation_id"]:
            identity_mismatches.append(f"{submission_id}:job_correlation")
        if lead and (
            lead["correlation_id"] != expected["correlation_id"]
            or lead["full_name"] != expected["full_name"]
            or lead["email"] != expected.get("email")
            or lead["phone"] != expected.get("phone")
            or lead["original_message"] != expected["message"]
        ):
            identity_mismatches.append(f"{submission_id}:lead_business_data")
    completed_mismatches = sorted(
        job["submission_id"]
        for job in scoped_jobs
        if job["state"] == "completed"
        and (
            not job.get("completed_lead_id")
            or job["submission_id"] not in lead_by_submission
            or lead_by_submission[job["submission_id"]]["id"] != job["completed_lead_id"]
        )
    )
    attempts = []
    for job in scoped_jobs:
        attempts.extend(
            request(
                f"{BACKEND_URL}/api/recovery/jobs/{job['id']}/attempts",
                authenticated=True,
            )[1]
        )
    return {
        "expected": len(identifiers),
        "jobs": counts,
        "matching_leads": len(scoped_leads),
        "missing": sorted(identifiers - set(lead_counts)),
        "duplicate_submission_ids": sorted(
            identifier for identifier, count in lead_counts.items() if count > 1
        ),
        "completed_job_lead_mismatches": completed_mismatches,
        "identity_mismatches": sorted(identity_mismatches),
        "actual_write_attempts": sorted(
            attempts, key=lambda attempt: (attempt["started_at"], attempt["attempt_number"])
        ),
        "quota_window": fault_state(manifest, allow_missing=True),
    }


def prepare(manifest):
    prior = fault_state(manifest, allow_missing=True)
    created = register(manifest)
    try:
        control(manifest, active=True, hold_delivery=True, reset_window=True)
        for enquiry in manifest["enquiries"]:
            intake = {**enquiry, "received_at": datetime.now(timezone.utc).isoformat()}
            status_code, result = request(INTAKE_URL, method="POST", body=intake)
            if status_code != 202 or result.get("intake_state") != "queued":
                raise RuntimeError(
                    f"Expected queued intake, received HTTP {status_code}: {result}"
                )
    except Exception:
        if created:
            control(manifest, active=False, hold_delivery=False, reset_window=True)
        elif prior is not None:
            control(
                manifest,
                active=prior["active"],
                hold_delivery=prior["hold_delivery"],
            )
        raise
    state = scoped_state(manifest)
    state["operator_notice"] = (
        "This scoped fault remains ACTIVE with delivery HELD for the next demo command."
    )
    print(json.dumps(state, indent=2))


def before(manifest):
    control(manifest, active=True, hold_delivery=False, reset_window=True)
    try:
        identifiers = {item["submission_id"] for item in manifest["enquiries"]}
        jobs = request(f"{BACKEND_URL}/api/recovery/jobs", authenticated=True)[1]
        leads = request(f"{BACKEND_URL}/api/leads")[1]
        existing = {lead["submission_id"] for lead in leads}
        scoped = [job for job in jobs if job["submission_id"] in identifiers]
        scoped.sort(key=lambda job: job["submission_id"] in existing)
        payloads = [job["payload_json"] for job in scoped]
        status_code, result = request(
            DIAGNOSTIC_URL, method="POST", body={"jobs": payloads}, allow_error=True
        )
    except Exception:
        control(manifest, active=False, hold_delivery=False, reset_window=True)
        raise
    state = scoped_state(manifest)
    saw_429 = any(
        attempt["status_code"] == 429 and attempt["outcome"] == "failed"
        for attempt in state["actual_write_attempts"]
    )
    partial_completion = 0 < state["matching_leads"] < state["expected"]
    if not saw_429 or not partial_completion:
        control(manifest, active=False, hold_delivery=False, reset_window=True)
        raise RuntimeError(
            "Diagnostic did not produce both partial CRM completion and a real 429 attempt"
        )
    print(json.dumps({"diagnostic_http_status": status_code, "body": result}, indent=2))
    print(json.dumps(state, indent=2))
    print("Scoped quota remains active for the measured recovery command.")


def recover(manifest):
    for _ in range(30):
        request(RECOVERY_URL, method="POST", body={}, allow_error=True)
        state = scoped_state(manifest)
        complete = (
            state["jobs"].get("completed") == state["expected"]
            and state["matching_leads"] == state["expected"]
            and not state["missing"]
            and not state["duplicate_submission_ids"]
            and not state["completed_job_lead_mismatches"]
            and not state["identity_mismatches"]
        )
        if complete:
            print(json.dumps(state, indent=2))
            return
        time.sleep(1)
    raise RuntimeError("Recovery did not complete the scoped batch within 30 dispatches")


def main():
    parser = argparse.ArgumentParser(description="Controlled Phase 3 local fault-injection demo")
    parser.add_argument(
        "command", choices=["prepare", "release", "before", "recover", "status", "disable"]
    )
    args = parser.parse_args()
    if not os.environ.get("CRM_ADAPTER_API_KEY"):
        parser.error("CRM_ADAPTER_API_KEY must be set in the operator shell")
    manifest = load_manifest()
    if args.command == "prepare":
        prepare(manifest)
    elif args.command == "release":
        result = control(manifest, active=True, hold_delivery=False, reset_window=True)
        result["operator_notice"] = "Scoped quota is ACTIVE and delivery is RELEASED."
        print(json.dumps(result, indent=2))
    elif args.command == "before":
        before(manifest)
    elif args.command == "recover":
        recover(manifest)
    elif args.command == "status":
        print(json.dumps(scoped_state(manifest), indent=2))
    else:
        result = control(manifest, active=False, hold_delivery=False, reset_window=True)
        result["operator_notice"] = "Scoped fault is DISABLED and delivery is not held."
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    try:
        main()
    except (OSError, RuntimeError, ValueError, KeyError) as error:
        print(f"phase3_demo: {error}", file=sys.stderr)
        sys.exit(1)
