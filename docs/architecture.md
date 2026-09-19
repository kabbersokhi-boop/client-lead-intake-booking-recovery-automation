# Phase 1 architecture

## Responsibilities

| Component | Responsibility |
| --- | --- |
| Browser form | Captures a manual synthetic enquiry, creates UUID trace identifiers, and POSTs directly to n8n. |
| n8n | Owns intake orchestration: business validation, normalization, NVIDIA request, strict output validation, safe fallback, CRM call, and webhook response. |
| NVIDIA NIM | Performs bounded extraction from the original message only. |
| Development CRM adapter | Validates the n8n contract and persists the lead through a provider interface. It is not GoHighLevel. |
| PostgreSQL | Stores lead data and auditable event records by correlation ID. |

## Verification trace

After a successful submission, the browser displays the returned correlation ID and pre-fills the read-only trace lookup panel. `GET /api/traces/{correlation_id}` joins the persisted lead with its safe audit events so an interviewer can inspect what happened to one specific synthetic lead. This query does not mutate data and is intentionally separate from the intake workflow.

## Failure behavior

Invalid customer data takes the n8n validation branch and returns HTTP 422 with a safe message. No model call is made.

If NVIDIA is unavailable or returns invalid JSON/schema, n8n sends the original normalized lead to the adapter with `ai_status=fallback_unavailable` or `fallback_invalid`, `needs_review=true`, and safe diagnostic state. The lead is still persisted.

The CRM adapter validates all inbound data again. Its persistence operation is idempotent by `submission_id`, so an orchestration retry will return the original CRM lead instead of creating a duplicate. On CRM failure, n8n returns a safe 502 response without stack details.

## Extension point

The orchestration contract is the `POST /api/crm/leads` payload. `DevelopmentCRMProvider` is the working provider in Phase 1. A future `GoHighLevelCRMProvider` can implement the same interface and map the stable payload to a GoHighLevel sandbox without changing n8n node logic.
