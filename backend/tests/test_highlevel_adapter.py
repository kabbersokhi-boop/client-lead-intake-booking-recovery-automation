import json
import uuid
from datetime import datetime, timezone

import httpx
import pytest
from fastapi import HTTPException, Response
from pydantic import SecretStr

from app.api import routes
from app.config import Settings
from app.models import CRMWriteAttempt, CRMWriteJob, Lead
from app.providers.crm import DevelopmentCRMProvider, build_crm_provider
from app.providers.highlevel import (
    HighLevelClient,
    HighLevelCRMProvider,
    HighLevelProviderError,
)
from app.schemas.lead import CRMLeadCreate
from app.schemas.recovery import (
    AttemptRequest,
    ClaimRequest,
    CompleteRequest,
    RecoveryAdmission,
)
from app.services.crm_service import SubmissionConflictError


def lead_payload(**changes) -> CRMLeadCreate:
    values = {
        "submission_id": uuid.uuid4(),
        "correlation_id": uuid.uuid4(),
        "received_at": "2026-09-21T10:00:00Z",
        "full_name": "Avery Furnace",
        "email": "avery.phase6@example.com",
        "phone": "+16045550144",
        "original_message": "The furnace needs a synthetic inspection.",
        "normalized_message": "The furnace needs a synthetic inspection.",
        "enrichment": {
            "service_type": "furnace_service",
            "location": "Surrey",
            "preferred_time": "Tuesday afternoon",
            "urgency": "medium",
            "summary": "Synthetic furnace service request.",
        },
        "ai_status": "enriched",
        "needs_review": False,
    }
    values.update(changes)
    return CRMLeadCreate.model_validate(values)


def highlevel_settings(**changes) -> Settings:
    values = {
        "crm_provider_mode": "highlevel_simulator",
        "highlevel_base_url": "http://127.0.0.1:18080",
        "highlevel_token": SecretStr("local-test-token"),
        "highlevel_timeout_seconds": 0.1,
    }
    values.update(changes)
    return Settings(_env_file=None, **values)


class ContractBackend:
    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []
        self.contacts: dict[str, dict] = {}
        self.opportunities: dict[str, dict] = {}
        self.failure_status: int | None = None
        self.malformed = False
        self.malformed_opportunity_meta = False
        self.network_error = False

    @staticmethod
    def _request_fields(body: dict) -> list[dict]:
        return [
            {"id": field["id"], "value": field["fieldValue"]}
            for field in body.get("customFields", [])
        ]

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        assert request.headers["Authorization"] == "Bearer local-test-token"
        assert request.headers["Version"] == "v3"
        assert request.headers["Accept"] == "application/json"
        if self.network_error:
            raise httpx.ConnectError("controlled", request=request)
        if self.failure_status:
            headers = {"Retry-After": "7"} if self.failure_status == 429 else {}
            return httpx.Response(
                self.failure_status,
                headers=headers,
                json={"statusCode": self.failure_status, "message": "controlled"},
            )
        if self.malformed:
            return httpx.Response(200, content=b"not-json")

        if request.method == "POST" and request.url.path == "/contacts/upsert":
            body = json.loads(request.content)
            existing = next(
                (
                    contact
                    for contact in self.contacts.values()
                    if contact.get("email", "").casefold()
                    == body.get("email", "").casefold()
                ),
                None,
            )
            contact_id = existing["id"] if existing else "sim_contact_adapter"
            contact = {
                "id": contact_id,
                "name": body["name"],
                "email": body.get("email"),
                "phone": body.get("phone"),
                "locationId": body["locationId"],
                "customFields": self._request_fields(body),
            }
            self.contacts[contact_id] = contact
            return httpx.Response(
                200,
                json={"new": existing is None, "contact": contact, "traceId": "sim_trace"},
            )
        if request.method == "GET" and request.url.path.startswith("/contacts/"):
            if request.url.path == "/contacts/lookup":
                email = request.url.params.get("email")
                phone = request.url.params.get("phone")
                matches = [
                    contact
                    for contact in self.contacts.values()
                    if (
                        email
                        and contact.get("email", "").casefold() == email.casefold()
                    )
                    or (phone and contact.get("phone") == phone)
                ]
                cursor = request.url.params.get("nextCursor")
                start = int(cursor.removeprefix("sim_cursor_")) if cursor else 0
                limit = int(request.url.params.get("limit", "20"))
                page = matches[start : start + limit]
                response = {"contacts": page}
                if len(page) == limit:
                    response["nextCursor"] = f"sim_cursor_{start + limit}"
                return httpx.Response(200, json=response)
            contact_id = request.url.path.rsplit("/", 1)[-1]
            return httpx.Response(200, json={"contact": self.contacts[contact_id]})
        if request.method == "GET" and request.url.path == "/opportunities/search":
            contact_id = request.url.params.get("contactId")
            pipeline_id = request.url.params.get("pipelineId")
            location_id = request.url.params.get("locationId")
            matches = [
                opportunity
                for opportunity in self.opportunities.values()
                if (contact_id is None or opportunity["contactId"] == contact_id)
                and (pipeline_id is None or opportunity["pipelineId"] == pipeline_id)
                and (location_id is None or opportunity["locationId"] == location_id)
            ]
            page = int(request.url.params.get("page", "1"))
            limit = int(request.url.params.get("limit", "20"))
            start = (page - 1) * limit
            return httpx.Response(
                200,
                json={
                    "opportunities": matches[start : start + limit],
                    "meta": (
                        "not-an-object"
                        if self.malformed_opportunity_meta
                        else {"total": len(matches), "currentPage": page}
                    ),
                    "aggregations": {},
                },
            )
        if request.method == "POST" and request.url.path == "/opportunities/":
            body = json.loads(request.content)
            opportunity = {
                "id": "sim_opportunity_adapter",
                **body,
                "customFields": self._request_fields(body),
            }
            self.opportunities[opportunity["id"]] = opportunity
            return httpx.Response(201, json={"opportunity": opportunity})
        if request.method == "PUT" and request.url.path.startswith("/opportunities/"):
            opportunity = self.opportunities[request.url.path.rsplit("/", 1)[-1]]
            opportunity.update(json.loads(request.content))
            return httpx.Response(200, json={"opportunity": opportunity})
        raise AssertionError(f"unexpected request: {request.method} {request.url}")


def configured_client(backend: ContractBackend) -> HighLevelClient:
    return HighLevelClient(
        highlevel_settings(), transport=httpx.MockTransport(backend)
    )


def contact_record(
    payload: CRMLeadCreate,
    contact_id: str,
    *,
    email: str,
    phone: str,
    submission_id: uuid.UUID | None = None,
    correlation_id: uuid.UUID | None = None,
) -> dict:
    return {
        "id": contact_id,
        "name": payload.full_name,
        "email": email,
        "phone": phone,
        "locationId": "sim_location_reference",
        "customFields": [
            {
                "id": "sim_cf_submission_id",
                "value": str(submission_id or payload.submission_id),
            },
            {
                "id": "sim_cf_correlation_id",
                "value": str(correlation_id or payload.correlation_id),
            },
        ],
    }


def test_documented_contact_and_opportunity_mapping_and_reconciliation():
    backend = ContractBackend()
    client = configured_client(backend)
    payload = lead_payload()

    client.sync_lead(payload)
    assert client.reconcile(payload) is True

    contact_request = next(
        request
        for request in backend.requests
        if request.method == "POST" and request.url.path == "/contacts/upsert"
    )
    contact_body = json.loads(contact_request.content)
    assert contact_request.url.path == "/contacts/upsert"
    assert contact_body == {
        "name": "Avery Furnace",
        "email": "avery.phase6@example.com",
        "phone": "+16045550144",
        "locationId": "sim_location_reference",
        "source": "local-contract-reference",
        "createNewIfDuplicateAllowed": False,
        "customFields": [
            {"id": "sim_cf_submission_id", "fieldValue": str(payload.submission_id)},
            {"id": "sim_cf_correlation_id", "fieldValue": str(payload.correlation_id)},
        ],
    }
    opportunity_request = next(
        request
        for request in backend.requests
        if request.method == "POST" and request.url.path == "/opportunities/"
    )
    opportunity_body = json.loads(opportunity_request.content)
    assert opportunity_body["pipelineStageId"] == "sim_stage_new_lead"
    assert opportunity_body["contactId"] == "sim_contact_adapter"
    assert opportunity_body["customFields"] == [
        {"id": "sim_of_submission_id", "fieldValue": str(payload.submission_id)}
    ]


def test_provider_replay_keeps_one_local_and_one_external_business_effect(db):
    backend = ContractBackend()
    provider = HighLevelCRMProvider(
        highlevel_settings(), client=configured_client(backend)
    )
    payload = lead_payload()

    first = provider.create_lead(db, payload)
    replay = provider.create_lead(db, payload)

    assert first.created is True
    assert replay.created is False
    assert first.lead.id == replay.lead.id
    assert db.query(Lead).count() == 1
    assert len(backend.contacts) == 1
    assert len(backend.opportunities) == 1
    assert provider.lookup_lead(db, payload.submission_id).lead.id == first.lead.id


@pytest.mark.parametrize(
    "upstream_state",
    ["unauthorized", "rate_limited", "server_error", "malformed", "network_error"],
)
def test_completed_provider_replay_never_reacquires_upstream_risk(db, upstream_state):
    backend = ContractBackend()
    provider = HighLevelCRMProvider(
        highlevel_settings(), client=configured_client(backend)
    )
    payload = lead_payload()
    created = provider.create_lead(db, payload)
    request_count = len(backend.requests)
    if upstream_state == "malformed":
        backend.malformed = True
    elif upstream_state == "network_error":
        backend.network_error = True
    else:
        backend.failure_status = {
            "unauthorized": 401,
            "rate_limited": 429,
            "server_error": 500,
        }[upstream_state]

    replayed = provider.replay_lead(db, payload)

    assert replayed.created is False
    assert replayed.lead.id == created.lead.id
    assert len(backend.requests) == request_count


def test_same_submission_with_conflicting_payload_stops_before_external_rewrite(db):
    backend = ContractBackend()
    provider = HighLevelCRMProvider(
        highlevel_settings(), client=configured_client(backend)
    )
    payload = lead_payload()
    provider.create_lead(db, payload)
    request_count = len(backend.requests)

    with pytest.raises(SubmissionConflictError):
        provider.create_lead(db, payload.model_copy(update={"full_name": "Changed Name"}))

    assert len(backend.requests) == request_count
    assert len(backend.contacts) == 1


def test_external_identity_conflict_is_not_treated_as_absence():
    backend = ContractBackend()
    client = configured_client(backend)
    payload = lead_payload()
    backend.contacts["sim_contact_foreign"] = {
        "id": "sim_contact_foreign",
        "name": payload.full_name,
        "email": str(payload.email),
        "phone": payload.phone,
        "locationId": "sim_location_reference",
        "customFields": [
            {"id": "sim_cf_submission_id", "value": str(uuid.uuid4())},
            {"id": "sim_cf_correlation_id", "value": str(uuid.uuid4())},
        ],
    }

    with pytest.raises(HighLevelProviderError, match="different application") as captured:
        client.reconcile(payload)

    assert captured.value.status_code == 409
    assert captured.value.error_class == "highlevel_identity_conflict"


def test_sync_refuses_foreign_duplicate_before_upsert():
    backend = ContractBackend()
    client = configured_client(backend)
    payload = lead_payload()
    backend.contacts["sim_contact_foreign"] = {
        "id": "sim_contact_foreign",
        "name": payload.full_name,
        "email": str(payload.email),
        "phone": payload.phone,
        "locationId": "sim_location_reference",
        "customFields": [
            {"id": "sim_cf_submission_id", "value": str(uuid.uuid4())},
            {"id": "sim_cf_correlation_id", "value": str(uuid.uuid4())},
        ],
    }

    with pytest.raises(HighLevelProviderError, match="different application"):
        client.sync_lead(payload)

    assert not any(
        request.method == "POST" and request.url.path == "/contacts/upsert"
        for request in backend.requests
    )
    assert backend.contacts["sim_contact_foreign"]["customFields"][0]["value"] != str(
        payload.submission_id
    )


def test_email_case_difference_cannot_bypass_foreign_identity_conflict():
    backend = ContractBackend()
    client = configured_client(backend)
    payload = lead_payload()
    backend.contacts["sim_contact_foreign"] = contact_record(
        payload,
        "sim_contact_foreign",
        email=str(payload.email).upper(),
        phone="+16045550991",
        submission_id=uuid.uuid4(),
        correlation_id=uuid.uuid4(),
    )

    with pytest.raises(HighLevelProviderError) as captured:
        client.sync_lead(payload)

    assert captured.value.error_class == "highlevel_identity_conflict"
    assert not any(request.method == "POST" for request in backend.requests)


def test_sync_checks_phone_duplicate_even_when_email_is_present():
    backend = ContractBackend()
    client = configured_client(backend)
    payload = lead_payload()
    backend.contacts["sim_contact_phone_foreign"] = {
        "id": "sim_contact_phone_foreign",
        "name": "Different synthetic person",
        "email": "different.phase6@example.com",
        "phone": payload.phone,
        "locationId": "sim_location_reference",
        "customFields": [
            {"id": "sim_cf_submission_id", "value": str(uuid.uuid4())},
            {"id": "sim_cf_correlation_id", "value": str(uuid.uuid4())},
        ],
    }

    with pytest.raises(HighLevelProviderError, match="different application"):
        client.sync_lead(payload)

    lookup_queries = [
        request.url.params
        for request in backend.requests
        if request.url.path == "/contacts/lookup"
    ]
    assert any(query.get("email") == str(payload.email) for query in lookup_queries)
    assert any(query.get("phone") == payload.phone for query in lookup_queries)
    assert not any(request.method == "POST" for request in backend.requests)


@pytest.mark.parametrize("correct_identifier", ["email", "phone"])
def test_split_identifiers_fail_when_one_match_has_foreign_identity(correct_identifier):
    backend = ContractBackend()
    client = configured_client(backend)
    payload = lead_payload()
    correct_email = (
        str(payload.email) if correct_identifier == "email" else "other@example.com"
    )
    correct_phone = payload.phone if correct_identifier == "phone" else "+16045550991"
    backend.contacts["sim_contact_correct"] = contact_record(
        payload,
        "sim_contact_correct",
        email=correct_email,
        phone=correct_phone,
    )
    backend.contacts["sim_contact_foreign"] = contact_record(
        payload,
        "sim_contact_foreign",
        email=("foreign@example.com" if correct_identifier == "email" else str(payload.email)),
        phone=(payload.phone if correct_identifier == "email" else "+16045550992"),
        submission_id=uuid.uuid4(),
        correlation_id=uuid.uuid4(),
    )

    with pytest.raises(HighLevelProviderError) as captured:
        client.sync_lead(payload)

    assert captured.value.error_class == "highlevel_identity_conflict"
    assert not any(request.method == "POST" for request in backend.requests)


def test_both_identifiers_resolving_to_same_application_contact_succeed():
    backend = ContractBackend()
    client = configured_client(backend)
    payload = lead_payload()
    backend.contacts["sim_contact_expected"] = contact_record(
        payload,
        "sim_contact_expected",
        email=str(payload.email),
        phone=payload.phone,
    )

    client.sync_lead(payload)

    assert len(backend.contacts) == 1
    assert len(backend.opportunities) == 1
    assert not any(
        request.method == "POST" and request.url.path == "/contacts/upsert"
        for request in backend.requests
    )


def test_multiple_contacts_for_one_identifier_are_an_identity_conflict():
    backend = ContractBackend()
    client = configured_client(backend)
    payload = lead_payload()
    backend.contacts["sim_contact_expected"] = contact_record(
        payload,
        "sim_contact_expected",
        email=str(payload.email),
        phone="+16045550991",
    )
    backend.contacts["sim_contact_duplicate"] = contact_record(
        payload,
        "sim_contact_duplicate",
        email=str(payload.email),
        phone="+16045550992",
    )

    with pytest.raises(HighLevelProviderError) as captured:
        client.sync_lead(payload)

    assert captured.value.error_class == "highlevel_identity_conflict"
    assert "ambiguous" in captured.value.safe_message


def test_one_identifier_absent_and_other_correct_reuses_known_contact():
    backend = ContractBackend()
    client = configured_client(backend)
    payload = lead_payload()
    backend.contacts["sim_contact_expected"] = contact_record(
        payload,
        "sim_contact_expected",
        email=str(payload.email),
        phone="+16045550991",
    )

    client.sync_lead(payload)

    assert len(backend.contacts) == 1
    assert len(backend.opportunities) == 1
    assert not any(
        request.method == "POST" and request.url.path == "/contacts/upsert"
        for request in backend.requests
    )


def test_formatted_phone_is_normalized_for_lookup_upsert_and_replay():
    backend = ContractBackend()
    client = configured_client(backend)
    payload = lead_payload(phone="+1 (604) 555-0144")

    client.sync_lead(payload)
    client.sync_lead(payload)

    phone_queries = [
        request.url.params.get("phone")
        for request in backend.requests
        if request.url.path == "/contacts/lookup" and request.url.params.get("phone")
    ]
    contact_writes = [
        json.loads(request.content)
        for request in backend.requests
        if request.method == "POST" and request.url.path == "/contacts/upsert"
    ]
    assert phone_queries == ["+16045550144", "+16045550144"]
    assert [write["phone"] for write in contact_writes] == ["+16045550144"]
    assert len(backend.contacts) == 1
    assert len(backend.opportunities) == 1


def test_non_e164_phone_is_rejected_before_any_external_request():
    backend = ContractBackend()
    client = configured_client(backend)

    with pytest.raises(HighLevelProviderError) as captured:
        client.sync_lead(lead_payload(phone="604-555-0144"))

    assert captured.value.status_code == 422
    assert captured.value.error_class == "highlevel_phone_validation"
    assert backend.requests == []


@pytest.mark.parametrize(
    ("status_code", "error_class", "retry_after"),
    [
        (401, "highlevel_authentication", None),
        (429, "highlevel_rate_limited", "7"),
        (500, "highlevel_upstream_failure", None),
    ],
)
def test_error_translation(status_code, error_class, retry_after):
    backend = ContractBackend()
    backend.failure_status = status_code
    client = configured_client(backend)

    with pytest.raises(HighLevelProviderError) as captured:
        client.sync_lead(lead_payload())

    assert captured.value.status_code == status_code
    assert captured.value.error_class == error_class
    assert captured.value.retry_after == retry_after


def test_timeout_and_malformed_success_are_distinct():
    def timeout_handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("controlled", request=request)

    timeout_client = HighLevelClient(
        highlevel_settings(), transport=httpx.MockTransport(timeout_handler)
    )
    with pytest.raises(HighLevelProviderError) as timeout:
        timeout_client.sync_lead(lead_payload())
    assert timeout.value.status_code is None
    assert timeout.value.error_class == "highlevel_timeout"

    malformed_backend = ContractBackend()
    malformed_backend.malformed = True
    with pytest.raises(HighLevelProviderError) as malformed:
        configured_client(malformed_backend).sync_lead(lead_payload())
    assert malformed.value.status_code == 502
    assert malformed.value.error_class == "highlevel_malformed_response"


def test_pipeline_stage_mapping_and_update_contract():
    backend = ContractBackend()
    client = configured_client(backend)
    payload = lead_payload()
    client.sync_lead(payload)

    client.update_opportunity_stage("sim_opportunity_adapter", "appointment_booked")

    request = backend.requests[-1]
    assert request.method == "PUT"
    assert json.loads(request.content) == {
        "pipelineId": "sim_pipeline_hvac",
        "pipelineStageId": "sim_stage_appointment_booked",
        "status": "open",
    }


def test_opportunity_reconciliation_finds_stable_identity_on_second_page():
    backend = ContractBackend()
    client = configured_client(backend)
    payload = lead_payload()
    contact_id = "sim_contact_paginated"
    backend.contacts[contact_id] = {
        "id": contact_id,
        "name": payload.full_name,
        "email": str(payload.email),
        "phone": payload.phone,
        "locationId": "sim_location_reference",
        "customFields": [
            {"id": "sim_cf_submission_id", "value": str(payload.submission_id)},
            {"id": "sim_cf_correlation_id", "value": str(payload.correlation_id)},
        ],
    }
    for index in range(100):
        opportunity_id = f"sim_opportunity_foreign_{index}"
        backend.opportunities[opportunity_id] = {
            "id": opportunity_id,
            "contactId": contact_id,
            "locationId": "sim_location_reference",
            "pipelineId": "sim_pipeline_hvac",
            "customFields": [
                {"id": "sim_of_submission_id", "value": str(uuid.uuid4())}
            ],
        }
    backend.opportunities["sim_opportunity_expected"] = {
        "id": "sim_opportunity_expected",
        "contactId": contact_id,
        "locationId": "sim_location_reference",
        "pipelineId": "sim_pipeline_hvac",
        "customFields": [
            {
                "id": "sim_of_submission_id",
                "value": str(payload.submission_id),
            }
        ],
    }

    assert client.reconcile(payload) is True
    opportunity_pages = [
        request.url.params.get("page")
        for request in backend.requests
        if request.url.path == "/opportunities/search"
    ]
    assert opportunity_pages == ["1", "2"]


def test_opportunity_reconciliation_rejects_duplicate_identity_across_pages():
    backend = ContractBackend()
    client = configured_client(backend)
    payload = lead_payload()
    client.sync_lead(payload)
    contact_id = next(iter(backend.contacts))
    opportunity = next(iter(backend.opportunities.values()))
    expected_id = next(iter(backend.opportunities))
    for index in range(99):
        foreign_id = f"sim_opportunity_foreign_{index}"
        backend.opportunities[foreign_id] = {
            **opportunity,
            "id": foreign_id,
            "customFields": [
                {"id": "sim_of_submission_id", "value": str(uuid.uuid4())}
            ],
        }
    duplicate_id = "sim_opportunity_duplicate"
    backend.opportunities[duplicate_id] = {
        **opportunity,
        "id": duplicate_id,
    }

    with pytest.raises(HighLevelProviderError) as captured:
        client.reconcile(payload)

    assert captured.value.status_code == 409
    assert captured.value.error_class == "highlevel_identity_conflict"
    assert backend.opportunities[expected_id]["contactId"] == contact_id


def test_opportunity_reconciliation_rejects_conflicting_pipeline_linkage():
    backend = ContractBackend()
    client = configured_client(backend)
    payload = lead_payload()
    client.sync_lead(payload)
    opportunity = next(iter(backend.opportunities.values()))
    opportunity["pipelineId"] = "sim_pipeline_wrong"

    with pytest.raises(HighLevelProviderError) as captured:
        client.reconcile(payload)

    assert captured.value.status_code == 409
    assert captured.value.error_class == "highlevel_identity_conflict"


def test_opportunity_reconciliation_rejects_same_identity_on_wrong_contact():
    backend = ContractBackend()
    client = configured_client(backend)
    payload = lead_payload()
    client.sync_lead(payload)
    opportunity = next(iter(backend.opportunities.values()))
    opportunity["contactId"] = "sim_contact_foreign"

    with pytest.raises(HighLevelProviderError) as captured:
        client.reconcile(payload)

    assert captured.value.error_class == "highlevel_identity_conflict"
    searches = [
        request
        for request in backend.requests
        if request.url.path == "/opportunities/search"
    ]
    assert searches[-1].url.params.get("contactId") is None
    assert searches[-1].url.params.get("pipelineId") is None


def test_opportunity_reconciliation_rejects_malformed_pagination_metadata():
    backend = ContractBackend()
    client = configured_client(backend)
    payload = lead_payload()
    client.sync_lead(payload)
    backend.malformed_opportunity_meta = True

    with pytest.raises(HighLevelProviderError) as captured:
        client.reconcile(payload)

    assert captured.value.error_class == "highlevel_malformed_response"


def test_opportunity_reconciliation_does_not_treat_missing_identity_data_as_absence():
    backend = ContractBackend()
    client = configured_client(backend)
    payload = lead_payload()
    client.sync_lead(payload)
    opportunity = next(iter(backend.opportunities.values()))
    opportunity.pop("customFields")

    with pytest.raises(HighLevelProviderError) as captured:
        client.reconcile(payload)

    assert captured.value.error_class == "highlevel_malformed_response"


def test_provider_modes_preserve_development_and_fail_closed_for_live():
    assert isinstance(
        build_crm_provider(Settings(_env_file=None, crm_provider_mode="development")),
        DevelopmentCRMProvider,
    )
    with pytest.raises(RuntimeError, match="intentionally unavailable"):
        build_crm_provider(Settings(_env_file=None, crm_provider_mode="highlevel_live"))


@pytest.mark.parametrize(
    "base_url",
    [
        "http://highlevel-simulator:8080",
        "http://localhost:18080",
        "http://127.0.0.1:18080",
        "http://[::1]:18080",
    ],
)
def test_simulator_mode_allows_only_explicit_local_targets(base_url):
    settings = highlevel_settings(highlevel_base_url=base_url)

    assert settings.highlevel_base_url == base_url


@pytest.mark.parametrize(
    "base_url",
    [
        "https://services.leadconnectorhq.com:443",
        "https://localhost:18080",
        "http://localhost.example.com:18080",
        "http://127.0.0.1.example.com:18080",
        "http://user@localhost:18080",
        "http://localhost:18080/contracts",
        "http://localhost:18080?target=external",
        "http://localhost",
        "http://2130706433:18080",
    ],
)
def test_simulator_mode_rejects_external_or_ambiguous_targets(base_url):
    with pytest.raises(ValueError, match="highlevel_simulator"):
        highlevel_settings(highlevel_base_url=base_url)


def test_durable_recovery_owns_429_retry_and_reconciles_before_rewrite(
    db, monkeypatch
):
    backend = ContractBackend()
    backend.failure_status = 429
    provider = HighLevelCRMProvider(
        highlevel_settings(), client=configured_client(backend)
    )
    monkeypatch.setattr(routes, "provider", provider)
    payload = lead_payload()
    admission = RecoveryAdmission(payload=payload, execution_reference="phase6-test")
    intake_response = Response()

    queued = routes.durable_intake(admission, intake_response, None, db)

    assert intake_response.status_code == 202
    assert intake_response.headers["Retry-After"] == "7"
    assert queued["recovery_state"] == "retry_wait"
    assert db.query(Lead).count() == 1
    job = db.get(CRMWriteJob, uuid.UUID(queued["recovery_job_id"]))
    assert job.attempt_count == 1
    assert db.query(CRMWriteAttempt).one().error_class == "highlevel_rate_limited"

    backend.failure_status = None
    job.due_at = datetime.now(timezone.utc)
    db.commit()
    claim = routes.claim_specific_recovery_job(
        job.id,
        ClaimRequest(worker_id="phase6-test", execution_reference="phase6-recovery"),
        None,
        db,
    )
    lease_token = claim.lease_token

    with pytest.raises(HTTPException) as absent:
        routes.lookup_crm_lead(payload.submission_id, None, db)
    assert absent.value.status_code == 404
    attempt_request = AttemptRequest(
        lease_token=lease_token, execution_reference="phase6-recovery"
    )
    routes.confirm_recovery_reconciliation_absent(job.id, attempt_request, None, db)
    attempt = routes.start_recovery_attempt(job.id, attempt_request, None, db)
    write_response = Response()
    written = routes.create_crm_lead(
        payload,
        write_response,
        x_n8n_execution_reference="phase6-recovery",
        x_recovery_lease_token=lease_token,
        x_crm_diagnostic=None,
        _=None,
        db=db,
    )
    assert write_response.status_code == 200
    completed = routes.complete_recovery_job(
        job.id,
        CompleteRequest(
            lease_token=lease_token,
            attempt_id=attempt["attempt_id"],
            crm_lead_id=written.crm_lead_id,
            status_code=200,
            execution_reference="phase6-recovery",
        ),
        None,
        db,
    )
    assert completed.state == "completed"
    assert len(backend.contacts) == 1
    assert len(backend.opportunities) == 1

    request_count = len(backend.requests)
    backend.failure_status = 429
    replay_response = Response()
    routes.durable_intake(admission, replay_response, None, db)
    assert replay_response.status_code == 200
    assert len(backend.requests) == request_count
    assert len(backend.contacts) == 1
    assert len(backend.opportunities) == 1


def test_highlevel_authentication_failure_activates_existing_credential_pause(
    db, monkeypatch
):
    backend = ContractBackend()
    backend.failure_status = 401
    provider = HighLevelCRMProvider(
        highlevel_settings(), client=configured_client(backend)
    )
    monkeypatch.setattr(routes, "provider", provider)

    response = Response()
    queued = routes.durable_intake(
        RecoveryAdmission(payload=lead_payload(), execution_reference="phase6-auth"),
        response,
        None,
        db,
    )

    assert response.status_code == 202
    assert queued["recovery_state"] == "blocked"
    blocked_job = db.get(CRMWriteJob, uuid.UUID(queued["recovery_job_id"]))
    assert blocked_job.last_error_class == "highlevel_authentication"

    waiting_job, _ = routes.recovery_service.admit(db, lead_payload())
    assert routes.recovery_service.claim(db, "phase6-worker") is None
    db.refresh(waiting_job)
    assert waiting_job.state == "pending"
