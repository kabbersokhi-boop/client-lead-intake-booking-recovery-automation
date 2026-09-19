# Phase 1–3 architecture

## Responsibilities

| Component | Responsibility |
| --- | --- |
| Browser form | Captures a manual synthetic enquiry and optional business-local appointment, creates UUID request identities, and retains an unchanged pending identity after an ambiguous outcome. |
| n8n | Owns intake, scheduled follow-up, and booking orchestration while calling narrow development CRM/domain boundaries. |
| NVIDIA NIM | Performs bounded extraction from the original message only. |
| Development CRM adapter | Validates n8n contracts, persists leads, applies transactional booking state, and sends development email to Mailpit. It is not GoHighLevel. |
| PostgreSQL | Stores lead, follow-up, appointment, source/server timestamp, idempotency, and audit state by correlation ID. |
| CRM recovery job | Stores the validated payload before delivery, bounded lease, attempt history, safe errors, due time, and final CRM identity independently of a Lead row. |
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

Lead creation and initial follow-up scheduling share one transaction. Booking creation, the `appointment_booked` transition, pending-follow-up cancellation, and their audit events share a second transaction. n8n still visibly owns the workflow before and after these operations.

Both booking and follow-up dispatch lock `Lead` and then reload/lock `FollowUp`, giving the lifecycle decision one consistent ordering. If booking commits first, dispatch observes cancellation and does not send. If dispatch owns the decision first, booking waits, then finishes with `appointment_booked`; concurrent dispatches serialize and send once in normal successful operation.

n8n invokes the FastAPI development email boundary over HTTP; FastAPI submits SMTP to Mailpit. SMTP acceptance happens before the database commit that records `sent_at`, so those effects are not universally atomic. Row locks and timestamps cover ordinary successful concurrency and replay, not crashes or lost acknowledgements after SMTP acceptance. No automatic retry is performed inside an aborted SMTP-containing transaction, and Phase 3 recovery queues are deliberately absent.

Appointment input is an offset-free Surrey business-local value with the explicit configured zone `America/Vancouver`. The backend converts it to a canonical timezone-aware instant for storage and rejects unsupported zones or nonexistent local wall times.

The appointment record is a synthetic durable booking-state demonstration. It does not assert real service availability or reserve capacity in an external calendar.

## Failure and recovery behavior

Invalid customer data takes the n8n validation branch and returns HTTP 422 with a safe message. No model call is made.

If NVIDIA is unavailable or returns invalid JSON/schema, n8n sends the original customer message and separately normalized processing text to the adapter with `ai_status=fallback_unavailable` or `fallback_invalid`, `needs_review=true`, and safe diagnostic state. The lead is still persisted. Provider errors and malformed model output remain distinguishable.

The CRM adapter validates all inbound data again. Its persistence operation uses a unique `submission_id` plus a stable fingerprint of normalized customer data, so a concurrent or sequential equivalent retry returns the original CRM lead without a second creation audit event. Reusing an ID for different customer data returns `409`; enrichment never rewrites an existing submission. On CRM failure or an invalid CRM acknowledgement, n8n returns a safe `502` response without stack details.

The client `received_at` is stored as source data. `created_at` is assigned by the persistence layer and recorded in the creation audit as the trusted server timestamp; the browser clock is not treated as authoritative.

Phase 3 persists the validated payload before delivery. Confirmed writes still return `201 created` or `200 replayed`; unfinished durable work returns `202 queued` with stable receipt identifiers but no CRM ID. Recovery processes one job per execution, claims with a bounded lease, reconciles by submission ID, obtains a shared database quota reservation, and only then counts and sends a write attempt. Quota deferral is not an attempt. Valid `Retry-After` values are never shortened.

The disabled-by-default fixed-window simulator affects only registered synthetic submission IDs. Scoped POST lead writes, including idempotent replays, count; reads do not. Rejection happens before the business write with HTTP 429 and `Retry-After`. Bookings, follow-ups, NVIDIA, and unrelated submissions are unaffected.

## Development boundary

The working integration remains `DevelopmentCRMProvider` plus small lifecycle and CRM-write recovery services. No vendor CRM, real calendar, external email provider, general job platform, or Phase 4 integration is configured.
