import re
import uuid
from dataclasses import dataclass
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.models import FollowUp, Lead
from app.providers.crm import CRMProvider
from app.schemas.lead import CRMLeadCreate
from app.services.crm_service import CreateLeadResult, DevelopmentCRMService

E164_RE = re.compile(r"^\+[1-9]\d{6,14}$")


@dataclass(frozen=True)
class HighLevelProviderError(Exception):
    status_code: int | None
    error_class: str
    safe_message: str
    retry_after: str | None = None

    def __str__(self) -> str:
        return self.safe_message


class HighLevelClient:
    def __init__(
        self,
        settings: Settings,
        *,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        if not settings.highlevel_token:
            raise RuntimeError("HIGHLEVEL_TOKEN is required in highlevel_simulator mode.")
        self.settings = settings
        self.client = httpx.Client(
            base_url=settings.highlevel_base_url.rstrip("/"),
            headers={
                "Accept": "application/json",
                "Authorization": f"Bearer {settings.highlevel_token.get_secret_value()}",
                "Version": "v3",
            },
            timeout=settings.highlevel_timeout_seconds,
            transport=transport,
        )

    def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        try:
            response = self.client.request(method, path, **kwargs)
        except httpx.TimeoutException as error:
            raise HighLevelProviderError(
                None,
                "highlevel_timeout",
                "HighLevel request timed out before its outcome could be confirmed.",
            ) from error
        except httpx.RequestError as error:
            raise HighLevelProviderError(
                None,
                "highlevel_network_error",
                "HighLevel request could not be completed or confirmed.",
            ) from error

        retry_after = response.headers.get("Retry-After")
        if response.status_code == 429:
            raise HighLevelProviderError(
                429,
                "highlevel_rate_limited",
                "HighLevel rate limited the request.",
                retry_after,
            )
        if response.status_code in {401, 403}:
            raise HighLevelProviderError(
                response.status_code,
                "highlevel_authentication",
                "HighLevel rejected the configured authentication or permissions.",
            )
        if response.status_code in {400, 404, 409, 422}:
            raise HighLevelProviderError(
                response.status_code,
                "highlevel_validation",
                "HighLevel rejected the request contract or referenced account mapping.",
            )
        if response.status_code >= 500:
            raise HighLevelProviderError(
                response.status_code,
                "highlevel_upstream_failure",
                "HighLevel returned a retryable upstream failure.",
                retry_after,
            )
        if response.status_code < 200 or response.status_code >= 300:
            raise HighLevelProviderError(
                response.status_code,
                "highlevel_unexpected_status",
                "HighLevel returned an unexpected response status.",
            )
        try:
            body = response.json()
        except ValueError as error:
            raise HighLevelProviderError(
                502,
                "highlevel_malformed_response",
                "HighLevel returned a malformed success response.",
            ) from error
        if not isinstance(body, dict):
            raise HighLevelProviderError(
                502,
                "highlevel_malformed_response",
                "HighLevel returned a malformed success response.",
            )
        return body

    @staticmethod
    def _field_value(record: dict[str, Any], field_id: str) -> str | None:
        fields = record.get("customFields")
        if not isinstance(fields, list):
            return None
        for field in fields:
            if isinstance(field, dict) and field.get("id") == field_id:
                value = field.get("value", field.get("fieldValue"))
                return value if isinstance(value, str) else None
        return None

    @staticmethod
    def _phone_for_contract(phone: str | None) -> str | None:
        if not phone:
            return None
        normalized = "+" + re.sub(r"\D", "", phone) if phone.strip().startswith("+") else phone
        if not E164_RE.fullmatch(normalized):
            raise HighLevelProviderError(
                422,
                "highlevel_phone_validation",
                "HighLevel reconciliation requires supplied phone numbers to use E.164 format.",
            )
        return normalized

    def _contact_fields(self, submission_id: uuid.UUID, correlation_id: uuid.UUID) -> list[dict]:
        return [
            {
                "id": self.settings.highlevel_contact_submission_field_id,
                "fieldValue": str(submission_id),
            },
            {
                "id": self.settings.highlevel_contact_correlation_field_id,
                "fieldValue": str(correlation_id),
            },
        ]

    def _contact_payload(self, payload: CRMLeadCreate) -> dict[str, Any]:
        body: dict[str, Any] = {
            "name": payload.full_name,
            "locationId": self.settings.highlevel_location_id,
            "source": "local-contract-reference",
            "createNewIfDuplicateAllowed": False,
            "customFields": self._contact_fields(payload.submission_id, payload.correlation_id),
        }
        if payload.email:
            body["email"] = str(payload.email)
        if payload.phone:
            body["phone"] = self._phone_for_contract(payload.phone)
        return body

    def _opportunity_payload(self, payload: CRMLeadCreate, contact_id: str) -> dict[str, Any]:
        return {
            "pipelineId": self.settings.highlevel_pipeline_id,
            "locationId": self.settings.highlevel_location_id,
            "name": f"{payload.full_name} - HVAC enquiry",
            "pipelineStageId": self.settings.highlevel_stage_new_lead_id,
            "status": "open",
            "contactId": contact_id,
            "customFields": [
                {
                    "id": self.settings.highlevel_opportunity_submission_field_id,
                    "fieldValue": str(payload.submission_id),
                }
            ],
        }

    @staticmethod
    def _record(value: Any, key: str) -> dict[str, Any]:
        record = value.get(key) if isinstance(value, dict) else None
        if not isinstance(record, dict) or not isinstance(record.get("id"), str):
            raise HighLevelProviderError(
                502,
                "highlevel_malformed_response",
                "HighLevel returned a malformed success response.",
            )
        return record

    def _lookup_contact(self, payload: CRMLeadCreate) -> dict[str, Any] | None:
        identifiers: list[tuple[str, str]] = []
        if payload.email:
            identifiers.append(("email", str(payload.email)))
        if payload.phone:
            identifiers.append(("phone", self._phone_for_contract(payload.phone)))
        contacts_by_id: dict[str, dict[str, Any]] = {}
        for identifier, value in identifiers:
            next_cursor = None
            seen_cursors: set[str] = set()
            for _ in range(50):
                params = {
                    "locationId": self.settings.highlevel_location_id,
                    identifier: value,
                    "limit": 20,
                }
                if next_cursor is not None:
                    params["nextCursor"] = next_cursor
                body = self._request("GET", "/contacts/lookup", params=params)
                contacts = body.get("contacts")
                if not isinstance(contacts, list):
                    raise HighLevelProviderError(
                        502,
                        "highlevel_malformed_response",
                        "HighLevel returned a malformed contact lookup response.",
                    )
                for contact in contacts:
                    if (
                        not isinstance(contact, dict)
                        or not isinstance(contact.get("id"), str)
                        or contact.get("locationId")
                        != self.settings.highlevel_location_id
                    ):
                        raise HighLevelProviderError(
                            502,
                            "highlevel_malformed_response",
                            "HighLevel returned a malformed contact lookup response.",
                        )
                    contacts_by_id[contact["id"]] = contact
                next_cursor = body.get("nextCursor")
                if next_cursor is None:
                    break
                if (
                    not isinstance(next_cursor, str)
                    or not next_cursor
                    or next_cursor in seen_cursors
                ):
                    raise HighLevelProviderError(
                        502,
                        "highlevel_malformed_response",
                        "HighLevel returned a malformed contact lookup cursor.",
                    )
                seen_cursors.add(next_cursor)
            else:
                raise HighLevelProviderError(
                    409,
                    "highlevel_identity_conflict",
                    "HighLevel contact reconciliation exceeded its bounded search window.",
                )
        contacts = list(contacts_by_id.values())
        expected_submission = str(payload.submission_id)
        matching = [
            contact
            for contact in contacts
            if self._field_value(
                contact, self.settings.highlevel_contact_submission_field_id
            )
            == expected_submission
        ]
        if len(matching) > 1:
            raise HighLevelProviderError(
                409,
                "highlevel_identity_conflict",
                "Multiple HighLevel contacts claim the same application submission identity.",
            )
        if not matching:
            if contacts:
                raise HighLevelProviderError(
                    409,
                    "highlevel_identity_conflict",
                    "The HighLevel duplicate match belongs to a different submission identity.",
                )
            return None
        contact = matching[0]
        if self._field_value(
            contact, self.settings.highlevel_contact_correlation_field_id
        ) != str(payload.correlation_id):
            raise HighLevelProviderError(
                409,
                "highlevel_identity_conflict",
                "The HighLevel contact correlation identity conflicts with local durable state.",
            )
        return contact

    def _lookup_opportunity(
        self, payload: CRMLeadCreate, contact_id: str
    ) -> dict[str, Any] | None:
        expected_submission = str(payload.submission_id)
        match = None
        for page in range(1, 11):
            body = self._request(
                "GET",
                "/opportunities/search",
                params={
                    "locationId": self.settings.highlevel_location_id,
                    "pipelineId": self.settings.highlevel_pipeline_id,
                    "contactId": contact_id,
                    "status": "all",
                    "page": page,
                    "limit": 100,
                },
            )
            opportunities = body.get("opportunities")
            if not isinstance(opportunities, list):
                raise HighLevelProviderError(
                    502,
                    "highlevel_malformed_response",
                    "HighLevel returned a malformed opportunity search response.",
                )
            for opportunity in opportunities:
                if not isinstance(opportunity, dict) or not isinstance(
                    opportunity.get("id"), str
                ):
                    raise HighLevelProviderError(
                        502,
                        "highlevel_malformed_response",
                        "HighLevel returned a malformed opportunity search response.",
                    )
                if (
                    self._field_value(
                        opportunity,
                        self.settings.highlevel_opportunity_submission_field_id,
                    )
                    != expected_submission
                ):
                    continue
                if (
                    opportunity.get("contactId") != contact_id
                    or opportunity.get("locationId")
                    != self.settings.highlevel_location_id
                    or opportunity.get("pipelineId")
                    != self.settings.highlevel_pipeline_id
                ):
                    raise HighLevelProviderError(
                        409,
                        "highlevel_identity_conflict",
                        "The HighLevel opportunity identity conflicts with its requested linkage.",
                    )
                if match is not None:
                    raise HighLevelProviderError(
                        409,
                        "highlevel_identity_conflict",
                        "Multiple HighLevel opportunities claim the same submission identity.",
                    )
                match = opportunity
            if len(opportunities) < 100:
                return match
        raise HighLevelProviderError(
            409,
            "highlevel_identity_conflict",
            "HighLevel opportunity reconciliation exceeded its bounded search window.",
        )

    def reconcile(self, payload: CRMLeadCreate) -> bool:
        contact = self._lookup_contact(payload)
        if not contact:
            return False
        contact_id = contact.get("id")
        if not isinstance(contact_id, str):
            raise HighLevelProviderError(
                502,
                "highlevel_malformed_response",
                "HighLevel returned a contact without a usable identifier.",
            )
        return self._lookup_opportunity(payload, contact_id) is not None

    def sync_lead(self, payload: CRMLeadCreate) -> None:
        contact = self._lookup_contact(payload)
        if contact:
            contact_id = contact["id"]
        else:
            contact_body = self._request(
                "POST", "/contacts/upsert", json=self._contact_payload(payload)
            )
            contact = self._record(contact_body, "contact")
            contact_id = contact["id"]
            verified = self._request("GET", f"/contacts/{contact_id}")
            verified_contact = self._record(verified, "contact")
            if (
                verified_contact.get("locationId")
                != self.settings.highlevel_location_id
                or self._field_value(
                    verified_contact,
                    self.settings.highlevel_contact_submission_field_id,
                )
                != str(payload.submission_id)
                or self._field_value(
                    verified_contact,
                    self.settings.highlevel_contact_correlation_field_id,
                )
                != str(payload.correlation_id)
            ):
                raise HighLevelProviderError(
                    409,
                    "highlevel_identity_conflict",
                    "HighLevel contact acknowledgement did not preserve application identity.",
                )
        if self._lookup_opportunity(payload, contact_id):
            return
        opportunity_body = self._request(
            "POST", "/opportunities/", json=self._opportunity_payload(payload, contact_id)
        )
        opportunity = self._record(opportunity_body, "opportunity")
        if (
            opportunity.get("contactId") != contact_id
            or opportunity.get("locationId") != self.settings.highlevel_location_id
            or opportunity.get("pipelineId") != self.settings.highlevel_pipeline_id
            or self._field_value(
                opportunity, self.settings.highlevel_opportunity_submission_field_id
            )
            != str(payload.submission_id)
        ):
            raise HighLevelProviderError(
                502,
                "highlevel_malformed_response",
                "HighLevel opportunity acknowledgement did not preserve application identity.",
            )

    def stage_id_for(self, pipeline_stage: str) -> str:
        mapping = {
            "new_lead": self.settings.highlevel_stage_new_lead_id,
            "contacted": self.settings.highlevel_stage_contacted_id,
            "appointment_booked": self.settings.highlevel_stage_appointment_booked_id,
        }
        try:
            return mapping[pipeline_stage]
        except KeyError as error:
            raise ValueError(f"Unsupported local pipeline stage: {pipeline_stage}") from error

    def update_opportunity_stage(self, opportunity_id: str, pipeline_stage: str) -> None:
        body = self._request(
            "PUT",
            f"/opportunities/{opportunity_id}",
            json={
                "pipelineId": self.settings.highlevel_pipeline_id,
                "pipelineStageId": self.stage_id_for(pipeline_stage),
                "status": "open",
            },
        )
        opportunity = self._record(body, "opportunity")
        if (
            opportunity.get("id") != opportunity_id
            or opportunity.get("pipelineId") != self.settings.highlevel_pipeline_id
            or opportunity.get("pipelineStageId") != self.stage_id_for(pipeline_stage)
        ):
            raise HighLevelProviderError(
                502,
                "highlevel_malformed_response",
                "HighLevel opportunity stage acknowledgement was malformed.",
            )


class HighLevelCRMProvider(CRMProvider):
    def __init__(self, settings: Settings, *, client: HighLevelClient | None = None) -> None:
        self.local_service = DevelopmentCRMService()
        self.client = client or HighLevelClient(settings)

    def create_lead(self, db: Session, payload: CRMLeadCreate) -> CreateLeadResult:
        local_result = self.local_service.create_lead(db, payload)
        self.client.sync_lead(payload)
        return local_result

    def replay_lead(self, db: Session, payload: CRMLeadCreate) -> CreateLeadResult:
        return self.local_service.create_lead(db, payload)

    def lookup_lead(
        self, db: Session, submission_id: uuid.UUID
    ) -> CreateLeadResult | None:
        lead = db.scalar(select(Lead).where(Lead.submission_id == submission_id))
        if not lead:
            return None
        enrichment = None
        if lead.ai_status == "enriched":
            enrichment = {
                "service_type": lead.service_type,
                "location": lead.location,
                "preferred_time": lead.preferred_time,
                "urgency": lead.urgency,
                "summary": lead.summary,
            }
        payload = CRMLeadCreate.model_validate(
            {
                "submission_id": lead.submission_id,
                "correlation_id": lead.correlation_id,
                "received_at": lead.client_received_at,
                "full_name": lead.full_name,
                "email": lead.email,
                "phone": lead.phone,
                "original_message": lead.original_message,
                "normalized_message": lead.normalized_message,
                "enrichment": enrichment,
                "ai_status": lead.ai_status,
                "needs_review": lead.needs_review,
                "provider_metadata": lead.provider_metadata,
            }
        )
        if not self.client.reconcile(payload):
            return None
        follow_up = db.scalar(select(FollowUp).where(FollowUp.lead_id == lead.id))
        return CreateLeadResult(lead=lead, follow_up=follow_up, created=False)
