#!/usr/bin/env python3
"""Idempotently inspect/provision the narrowly scoped HighLevel live resources.

This command reads HIGHLEVEL_LIVE_TOKEN and HIGHLEVEL_LOCATION_ID only from the
environment.  It never writes credentials or .env files, and its JSON output contains
only non-secret resource identifiers needed to configure highlevel_live.
"""

import json
import os
import sys
from typing import Any

import httpx

BASE_URL = "https://services.leadconnectorhq.com"
PIPELINE_NAME = "HVAC Service Pipeline"
STAGE_NAMES = ("New Lead", "Contacted", "Appointment Booked")
FIELDS = (
    ("contact", "HVAC Integration Submission ID"),
    ("contact", "HVAC Integration Correlation ID"),
    ("opportunity", "HVAC Integration Opportunity Submission ID"),
)


class SetupError(RuntimeError):
    pass


def require_environment() -> tuple[str, str]:
    token = os.environ.get("HIGHLEVEL_LIVE_TOKEN")
    location_id = os.environ.get("HIGHLEVEL_LOCATION_ID")
    if not token or not location_id:
        raise SetupError("HIGHLEVEL_LIVE_TOKEN and HIGHLEVEL_LOCATION_ID must both be set.")
    return token, location_id


def request(client: httpx.Client, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
    try:
        response = client.request(method, path, **kwargs)
    except httpx.RequestError as error:
        raise SetupError("HighLevel request could not be completed.") from error
    if not 200 <= response.status_code < 300:
        raise SetupError(f"HighLevel provisioning request failed with HTTP {response.status_code}.")
    try:
        body = response.json()
    except ValueError as error:
        raise SetupError("HighLevel returned malformed JSON.") from error
    if not isinstance(body, dict):
        raise SetupError("HighLevel returned an unexpected JSON response.")
    return body


def records(body: dict[str, Any], *keys: str) -> list[dict[str, Any]]:
    for key in keys:
        value = body.get(key)
        if isinstance(value, list) and all(isinstance(item, dict) for item in value):
            return value
    raise SetupError("HighLevel returned a malformed collection response.")


def exactly_one(items: list[dict[str, Any]], label: str) -> dict[str, Any] | None:
    if len(items) > 1:
        raise SetupError(f"More than one {label} exists; refusing to choose a target.")
    return items[0] if items else None


def pipeline(client: httpx.Client, location_id: str) -> tuple[str, dict[str, str]]:
    existing = exactly_one(
        [
            item
            for item in records(
                request(
                    client,
                    "GET",
                    "/opportunities/pipelines",
                    params={"locationId": location_id},
                ),
                "pipelines",
            )
            if item.get("name") == PIPELINE_NAME and item.get("locationId") == location_id
        ],
        f"pipeline named {PIPELINE_NAME!r}",
    )
    if existing is None:
        created = request(
            client,
            "POST",
            "/opportunities/pipelines",
            json={
                "name": PIPELINE_NAME,
                "locationId": location_id,
                "stages": [
                    {"name": name, "position": index + 1, "showInFunnel": True}
                    for index, name in enumerate(STAGE_NAMES)
                ],
                "showInFunnel": True,
                "showInPieChart": True,
                "useOpportunityProbability": False,
                "colorRenderMode": "dot",
            },
        )
        candidate = created.get("pipeline", created)
        if not isinstance(candidate, dict):
            raise SetupError("HighLevel returned a malformed pipeline acknowledgement.")
        existing = candidate
    pipeline_id = existing.get("id")
    if not isinstance(pipeline_id, str) or not pipeline_id:
        raise SetupError("HighLevel returned a pipeline without an ID.")
    # Always retrieve the canonical record; creation/list responses can omit stage details.
    fetched = request(client, "GET", f"/opportunities/pipelines/{pipeline_id}")
    canonical = fetched.get("pipeline", fetched)
    if not isinstance(canonical, dict):
        raise SetupError("HighLevel returned a malformed pipeline retrieval response.")
    if canonical.get("name") != PIPELINE_NAME or canonical.get("locationId") != location_id:
        raise SetupError("HighLevel pipeline acknowledgement did not match the requested location.")
    stages = records(canonical, "stages")
    if [stage.get("name") for stage in stages] != list(STAGE_NAMES):
        raise SetupError(
            "Existing HVAC Service Pipeline stages do not exactly match the integration contract; "
            "refusing a destructive full-pipeline update."
        )
    stage_ids: dict[str, str] = {}
    for stage in stages:
        name, stage_id = stage.get("name"), stage.get("id")
        if not isinstance(name, str) or not isinstance(stage_id, str) or not stage_id:
            raise SetupError("HighLevel returned a pipeline stage without a usable ID.")
        stage_ids[name] = stage_id
    return pipeline_id, stage_ids


def custom_fields(client: httpx.Client, location_id: str) -> dict[str, str]:
    ids: dict[str, str] = {}
    for model, name in FIELDS:
        existing_fields = records(
            request(
                client,
                "GET",
                f"/locations/{location_id}/customFields",
                params={"model": model},
            ),
            "customFields",
            "fields",
        )
        matches = [
            field
            for field in existing_fields
            if field.get("name") == name and field.get("model") == model
        ]
        field = exactly_one(matches, f"{model} field named {name!r}")
        if field is None:
            created = request(
                client,
                "POST",
                f"/locations/{location_id}/customFields",
                json={"name": name, "dataType": "TEXT", "model": model},
            )
            candidate = created.get("customField", created.get("field", created))
            if not isinstance(candidate, dict):
                raise SetupError("HighLevel returned a malformed custom-field acknowledgement.")
            field = candidate
        field_id = field.get("id")
        if (
            not isinstance(field_id, str)
            or not field_id
            or field.get("name") != name
            or field.get("model") != model
        ):
            raise SetupError(
                "HighLevel custom-field acknowledgement did not preserve the contract."
            )
        ids[f"{model}:{name}"] = field_id
    # A second read validates newly created fields and detects an unsafe duplicate race.
    for model, name in FIELDS:
        verified = records(
            request(
                client,
                "GET",
                f"/locations/{location_id}/customFields",
                params={"model": model},
            ),
            "customFields",
            "fields",
        )
        matches = [
            field for field in verified if field.get("name") == name and field.get("model") == model
        ]
        field = exactly_one(matches, f"{model} field named {name!r}")
        if not field or field.get("id") != ids[f"{model}:{name}"]:
            raise SetupError("HighLevel custom-field verification failed.")
    return ids


def main() -> int:
    try:
        token, location_id = require_environment()
        with httpx.Client(
            base_url=BASE_URL,
            headers={
                "Accept": "application/json",
                "Authorization": f"Bearer {token}",
                "Version": "v3",
            },
            timeout=15,
            trust_env=False,
        ) as client:
            pipeline_id, stage_ids = pipeline(client, location_id)
            field_ids = custom_fields(client, location_id)
        print(json.dumps({
            "location_id": location_id,
            "pipeline": {"name": PIPELINE_NAME, "id": pipeline_id, "stages": stage_ids},
            "custom_fields": field_ids,
        }, sort_keys=True))
        return 0
    except SetupError as error:
        print(f"setup_highlevel_live: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
