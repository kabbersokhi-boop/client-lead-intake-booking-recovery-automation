import asyncio
import json
import os
import re
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, model_validator

CONTRACT_VERSION = "v3"
DOCUMENTATION_REVIEW_DATE = "2026-09-22"
LOCATION_ID = "sim_location_reference"
PIPELINE_ID = "sim_pipeline_hvac"
STAGES = {
    "sim_stage_new_lead": "New Lead",
    "sim_stage_contacted": "Contacted",
    "sim_stage_appointment_booked": "Appointment Booked",
}
CONTACT_FIELD_IDS = {"sim_cf_submission_id", "sim_cf_correlation_id"}
OPPORTUNITY_FIELD_IDS = {"sim_of_submission_id"}
FAULT_TIMEOUT_SECONDS = float(
    os.environ.get("HIGHLEVEL_SIMULATOR_FAULT_TIMEOUT_SECONDS", "4")
)
ALLOWED_EVENT_KEYS = {
    "name",
    "email",
    "phone",
    "locationId",
    "source",
    "createNewIfDuplicateAllowed",
    "customFields",
    "id",
    "new",
    "contact",
    "contacts",
    "traceId",
    "pipelineId",
    "pipelineStageId",
    "status",
    "contactId",
    "opportunity",
    "opportunities",
    "meta",
    "aggregations",
    "fieldValue",
    "value",
    "message",
    "statusCode",
    "error",
    "nextCursor",
    "page",
    "limit",
    "title",
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def allowlisted(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: allowlisted(item)
            for key, item in value.items()
            if key in ALLOWED_EVENT_KEYS
        }
    if isinstance(value, list):
        return [allowlisted(item) for item in value[:100]]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return None


class SimulatorState:
    def __init__(self) -> None:
        self.lock = threading.RLock()
        self.contacts: dict[str, dict[str, Any]] = {}
        self.opportunities: dict[str, dict[str, Any]] = {}
        self.appointments: dict[str, dict[str, Any]] = {}
        self.events: list[dict[str, Any]] = []
        self.fault = {"mode": "normal", "retry_after": 5}

    def reset(self) -> None:
        with self.lock:
            self.contacts.clear()
            self.opportunities.clear()
            self.appointments.clear()
            self.events.clear()
            self.fault = {"mode": "normal", "retry_after": 5}

    def arm_fault(self, mode: str, retry_after: int) -> dict[str, Any]:
        with self.lock:
            self.fault = {"mode": mode, "retry_after": retry_after}
            return dict(self.fault)

    def consume_fault(self) -> dict[str, Any]:
        with self.lock:
            armed = dict(self.fault)
            if armed["mode"] != "normal":
                self.fault = {"mode": "normal", "retry_after": 5}
            return armed

    def record(
        self,
        *,
        request_id: str,
        method: str,
        path: str,
        query: dict[str, Any],
        request_body: Any,
        status_code: int,
        response_body: Any,
        retry_after: str | None = None,
    ) -> None:
        correlation = None
        if isinstance(request_body, dict):
            for field in request_body.get("customFields", []):
                if isinstance(field, dict) and field.get("id") == "sim_cf_submission_id":
                    correlation = field.get("fieldValue")
        event = {
            "requestId": request_id,
            "timestamp": now_iso(),
            "method": method,
            "path": path,
            "query": allowlisted(query),
            "requestBody": allowlisted(request_body),
            "status": status_code,
            "responseBody": allowlisted(response_body),
            "retryAfter": retry_after,
            "submissionReference": correlation,
        }
        with self.lock:
            self.events.insert(0, event)
            del self.events[200:]


state = SimulatorState()


class CustomField(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=80)
    fieldValue: str = Field(min_length=1, max_length=200)


class ContactUpsert(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=160)
    email: str | None = Field(default=None, max_length=254)
    phone: str | None = Field(default=None, max_length=50)
    locationId: str
    source: str = Field(min_length=1, max_length=100)
    createNewIfDuplicateAllowed: bool = False
    customFields: list[CustomField] = Field(min_length=2, max_length=2)

    @model_validator(mode="after")
    def validate_contract(self):
        if not self.email and not self.phone:
            raise ValueError("email or phone is required")
        if self.locationId != LOCATION_ID:
            raise ValueError("locationId is not configured in this simulator")
        if self.createNewIfDuplicateAllowed:
            raise ValueError("the reference adapter requires duplicate-safe upsert behavior")
        if {field.id for field in self.customFields} != CONTACT_FIELD_IDS:
            raise ValueError("the configured application identity fields are required")
        return self


class OpportunityCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pipelineId: str
    locationId: str
    name: str = Field(min_length=1, max_length=160)
    pipelineStageId: str
    status: Literal["open", "won", "lost", "abandoned", "all"]
    contactId: str
    customFields: list[CustomField] = Field(min_length=1, max_length=1)

    @model_validator(mode="after")
    def validate_contract(self):
        if self.pipelineId != PIPELINE_ID or self.locationId != LOCATION_ID:
            raise ValueError("pipelineId or locationId is not configured in this simulator")
        if self.pipelineStageId not in STAGES:
            raise ValueError("pipelineStageId is not configured in this simulator")
        if {field.id for field in self.customFields} != OPPORTUNITY_FIELD_IDS:
            raise ValueError("the configured opportunity identity field is required")
        return self


class OpportunityUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pipelineId: str
    pipelineStageId: str
    status: Literal["open", "won", "lost", "abandoned", "all"]

    @model_validator(mode="after")
    def validate_contract(self):
        if self.pipelineId != PIPELINE_ID or self.pipelineStageId not in STAGES:
            raise ValueError("pipeline or stage is not configured in this simulator")
        return self


class FaultRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Literal["normal", "unauthorized", "rate_limited", "server_error", "timeout"]
    retry_after: int = Field(default=5, ge=1, le=30)


app = FastAPI(title="HighLevel Contract Simulator", version="0.1.0")


@app.exception_handler(RequestValidationError)
async def validation_error(_request: Request, error: RequestValidationError):
    messages = [item["msg"] for item in error.errors()]
    return JSONResponse(
        {"statusCode": 422, "message": messages, "error": "Unprocessable Entity"},
        status_code=422,
    )


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "environment": "local-contract-simulator"}


@app.middleware("http")
async def contract_boundary(request: Request, call_next):
    is_contract = request.url.path.startswith(("/contacts", "/opportunities"))
    if not is_contract:
        return await call_next(request)

    request_id = f"sim_req_{uuid.uuid4().hex[:16]}"
    raw_body = await request.body()
    try:
        request_body = json.loads(raw_body) if raw_body else None
    except ValueError:
        request_body = None
    query = dict(request.query_params)

    async def finish(status_code: int, body: dict[str, Any], headers: dict | None = None):
        response_headers = dict(headers or {})
        response_headers["X-Simulator-Request-Id"] = request_id
        state.record(
            request_id=request_id,
            method=request.method,
            path=request.url.path,
            query=query,
            request_body=request_body,
            status_code=status_code,
            response_body=body,
            retry_after=response_headers.get("Retry-After"),
        )
        return JSONResponse(body, status_code=status_code, headers=response_headers)

    expected_token = os.environ.get("HIGHLEVEL_SIMULATOR_TOKEN", "")
    if not expected_token or request.headers.get("Authorization") != f"Bearer {expected_token}":
        return await finish(
            401,
            {
                "statusCode": 401,
                "message": "Invalid token: access token is invalid",
                "error": "Unauthorized",
            },
        )
    if request.headers.get("Version") != CONTRACT_VERSION:
        return await finish(
            422,
            {
                "statusCode": 422,
                "message": ["Version header must be v3"],
                "error": "Unprocessable Entity",
            },
        )

    fault = state.consume_fault()
    if fault["mode"] == "unauthorized":
        return await finish(
            401,
            {
                "statusCode": 401,
                "message": "Synthetic one-shot unauthorized",
                "error": "Unauthorized",
            },
        )
    if fault["mode"] == "rate_limited":
        return await finish(
            429,
            {"statusCode": 429, "message": "Synthetic one-shot rate limit"},
            {"Retry-After": str(fault["retry_after"])},
        )
    if fault["mode"] == "server_error":
        return await finish(500, {"statusCode": 500, "message": "Synthetic one-shot server error"})
    if fault["mode"] == "timeout":
        await asyncio.sleep(FAULT_TIMEOUT_SECONDS)
        return await finish(504, {"statusCode": 504, "message": "Synthetic one-shot timeout"})

    response = await call_next(request)
    response_bytes = b"".join([chunk async for chunk in response.body_iterator])
    try:
        response_body = json.loads(response_bytes) if response_bytes else None
    except ValueError:
        response_body = None
    state.record(
        request_id=request_id,
        method=request.method,
        path=request.url.path,
        query=query,
        request_body=request_body,
        status_code=response.status_code,
        response_body=response_body,
        retry_after=response.headers.get("Retry-After"),
    )
    headers = dict(response.headers)
    headers["X-Simulator-Request-Id"] = request_id
    return Response(
        content=response_bytes,
        status_code=response.status_code,
        headers=headers,
        media_type=response.media_type,
    )


def field_list(fields: list[CustomField]) -> list[dict[str, str]]:
    return [{"id": field.id, "value": field.fieldValue} for field in fields]


@app.post("/contacts/upsert")
def upsert_contact(payload: ContactUpsert) -> dict[str, Any]:
    with state.lock:
        existing = next(
            (
                contact
                for contact in state.contacts.values()
                if (
                    payload.email
                    and contact.get("email", "").casefold() == payload.email.casefold()
                )
                or (payload.phone and contact.get("phone") == payload.phone)
            ),
            None,
        )
        created = existing is None
        contact_id = existing["id"] if existing else f"sim_contact_{uuid.uuid4().hex[:16]}"
        timestamp = now_iso()
        contact = {
            "id": contact_id,
            "name": payload.name,
            "email": payload.email,
            "phone": payload.phone,
            "locationId": payload.locationId,
            "source": payload.source,
            "customFields": field_list(payload.customFields),
            "dateAdded": existing.get("dateAdded", timestamp) if existing else timestamp,
            "dateUpdated": timestamp,
        }
        state.contacts[contact_id] = contact
        return {
            "new": created,
            "contact": contact,
            "traceId": f"sim_trace_{uuid.uuid4().hex[:16]}",
        }


@app.get("/contacts/lookup")
def lookup_contact(
    locationId: str,
    email: str | None = None,
    phone: str | None = None,
    limit: int = Query(default=20, ge=1, le=20),
    nextCursor: str | None = None,
) -> dict[str, Any]:
    if locationId != LOCATION_ID:
        raise HTTPException(status_code=422, detail="locationId is not configured")
    if (email is None) == (phone is None):
        raise HTTPException(status_code=422, detail="exactly one of email or phone is required")
    if phone is not None and not re.fullmatch(r"\+[1-9]\d{6,14}", phone):
        raise HTTPException(status_code=422, detail="phone must use E.164 format")
    start = 0
    if nextCursor is not None:
        match = re.fullmatch(r"sim_cursor_(\d+)", nextCursor)
        if not match:
            raise HTTPException(status_code=422, detail="nextCursor is invalid")
        start = int(match.group(1))
    with state.lock:
        matching = [
            contact
            for contact in state.contacts.values()
            if contact["locationId"] == locationId
            and (
                (email is not None and contact.get("email", "").casefold() == email.casefold())
                or (phone is not None and contact.get("phone") == phone)
            )
        ]
        contacts = matching[start : start + limit]
    response: dict[str, Any] = {"contacts": contacts}
    if len(contacts) == limit:
        response["nextCursor"] = f"sim_cursor_{start + limit}"
    return response


@app.get("/contacts/{contact_id}")
def get_contact(contact_id: str) -> dict[str, Any]:
    with state.lock:
        contact = state.contacts.get(contact_id)
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")
    return {"contact": contact}


@app.get("/opportunities/search")
def search_opportunities(
    locationId: str,
    pipelineId: str | None = None,
    contactId: str | None = None,
    status: Literal["open", "won", "lost", "abandoned", "all"] = "all",
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
) -> dict[str, Any]:
    if locationId != LOCATION_ID:
        raise HTTPException(status_code=422, detail="locationId is not configured")
    with state.lock:
        matching = [
            opportunity
            for opportunity in state.opportunities.values()
            if opportunity["locationId"] == locationId
            and (pipelineId is None or opportunity["pipelineId"] == pipelineId)
            and (contactId is None or opportunity["contactId"] == contactId)
            and (status == "all" or opportunity["status"] == status)
        ]
        start = (page - 1) * limit
        opportunities = matching[start : start + limit]
    return {
        "opportunities": opportunities,
        "meta": {"total": len(matching), "currentPage": page},
        "aggregations": {},
    }


@app.post("/opportunities/", status_code=201)
def create_opportunity(payload: OpportunityCreate) -> dict[str, Any]:
    with state.lock:
        if payload.contactId not in state.contacts:
            raise HTTPException(status_code=422, detail="contactId does not exist")
        opportunity_id = f"sim_opportunity_{uuid.uuid4().hex[:16]}"
        timestamp = now_iso()
        opportunity = {
            "id": opportunity_id,
            "name": payload.name,
            "pipelineId": payload.pipelineId,
            "pipelineStageId": payload.pipelineStageId,
            "locationId": payload.locationId,
            "status": payload.status,
            "contactId": payload.contactId,
            "customFields": field_list(payload.customFields),
            "createdAt": timestamp,
            "updatedAt": timestamp,
        }
        state.opportunities[opportunity_id] = opportunity
    return {"opportunity": opportunity}


@app.put("/opportunities/{opportunity_id}")
def update_opportunity(opportunity_id: str, payload: OpportunityUpdate) -> dict[str, Any]:
    with state.lock:
        opportunity = state.opportunities.get(opportunity_id)
        if not opportunity:
            raise HTTPException(status_code=404, detail="Opportunity not found")
        opportunity.update(
            {
                "pipelineId": payload.pipelineId,
                "pipelineStageId": payload.pipelineStageId,
                "status": payload.status,
                "updatedAt": now_iso(),
            }
        )
        return {"opportunity": dict(opportunity)}


@app.get("/simulator/api/state")
def simulator_state() -> dict[str, Any]:
    with state.lock:
        return {
            "contractVersion": CONTRACT_VERSION,
            "documentationReviewDate": DOCUMENTATION_REVIEW_DATE,
            "locationId": LOCATION_ID,
            "pipelineId": PIPELINE_ID,
            "stages": STAGES,
            "contacts": list(state.contacts.values()),
            "opportunities": list(state.opportunities.values()),
            "appointments": list(state.appointments.values()),
            "events": list(state.events),
            "fault": dict(state.fault),
        }


@app.post("/simulator/api/fault")
def configure_fault(payload: FaultRequest) -> dict[str, Any]:
    return state.arm_fault(payload.mode, payload.retry_after)


@app.post("/simulator/api/reset")
def reset_simulator() -> dict[str, bool]:
    state.reset()
    return {"reset": True}


static_dir = Path(__file__).resolve().parent / "static"
app.mount("/", StaticFiles(directory=static_dir, html=True), name="simulator-ui")
