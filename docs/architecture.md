# Phase 1–2 architecture

## Responsibilities

| Component | Responsibility |
| --- | --- |
| Browser form | Captures a manual synthetic enquiry and optional business-local appointment, creates UUID request identities, and retains an unchanged pending identity after an ambiguous outcome. |
| n8n | Owns intake, scheduled follow-up, and booking orchestration while calling narrow development CRM/domain boundaries. |
| NVIDIA NIM | Performs bounded extraction from the original message only. |
| Development CRM adapter | Validates n8n contracts, persists leads, applies transactional booking state, and sends development email to Mailpit. It is not GoHighLevel. |
| PostgreSQL | Stores lead, follow-up, appointment, source/server timestamp, idempotency, and audit state by correlation ID. |
| Mailpit | Accepts local development SMTP messages and exposes them on a loopback web UI. It is not an external email provider. |

## Demonstration lead source

The browser form is one controlled website lead source used to make the live
demonstration repeatable during an interview. It is not presented as a complete
home-services website or a production client deployment.

In a real automation environment, source-specific adapters could map website
forms, CRM-native forms, advertising lead forms, messaging channels, or other
webhook/API sources into the same normalized internal lead contract before
downstream orchestration. Those sources are not implemented or tested in the
current phase.

## Verification trace

After a successful submission, the browser displays the returned correlation ID, enables booking without copying internal IDs, and pre-fills the read-only trace lookup panel. `GET /api/traces/{correlation_id}` joins the persisted lead, follow-up, appointment, and safe audit events. This local-development query does not mutate data.

## Lifecycle consistency

Lead creation and initial follow-up scheduling share one transaction. Booking creation, the `appointment_booked` transition, pending-follow-up cancellation, and their audit events share a second transaction. n8n still visibly owns the workflow before and after these operations. SMTP delivery is guarded by durable sent/cancelled state and PostgreSQL row locks for normal replay behavior; Phase 3 recovery queues are deliberately absent.

Appointment input is an offset-free Surrey business-local value with the explicit configured zone `America/Vancouver`. The backend converts it to a canonical timezone-aware instant for storage and rejects unsupported zones or nonexistent local wall times.

## Failure behavior

Invalid customer data takes the n8n validation branch and returns HTTP 422 with a safe message. No model call is made.

If NVIDIA is unavailable or returns invalid JSON/schema, n8n sends the original customer message and separately normalized processing text to the adapter with `ai_status=fallback_unavailable` or `fallback_invalid`, `needs_review=true`, and safe diagnostic state. The lead is still persisted. Provider errors and malformed model output remain distinguishable.

The CRM adapter validates all inbound data again. Its persistence operation uses a unique `submission_id` plus a stable fingerprint of normalized customer data, so a concurrent or sequential equivalent retry returns the original CRM lead without a second creation audit event. Reusing an ID for different customer data returns `409`; enrichment never rewrites an existing submission. On CRM failure or an invalid CRM acknowledgement, n8n returns a safe `502` response without stack details.

The client `received_at` is stored as source data. `created_at` is assigned by the persistence layer and recorded in the creation audit as the trusted server timestamp; the browser clock is not treated as authoritative.

## Development boundary

The working integration remains `DevelopmentCRMProvider` plus the small lifecycle service. No GoHighLevel, real calendar, external email provider, or failure-recovery subsystem is configured.
