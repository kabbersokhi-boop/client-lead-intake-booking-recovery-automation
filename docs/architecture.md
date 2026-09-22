# Current reference architecture

## Responsibilities

| Component | Responsibility |
| --- | --- |
| Browser form | Captures a manual synthetic enquiry and optional business-local appointment, creates UUID request identities, and retains an unchanged pending identity after an ambiguous outcome. |
| n8n | Owns intake, scheduled follow-up, and booking orchestration while calling narrow development CRM/domain boundaries. |
| NVIDIA NIM | Performs bounded extraction from the original message only. |
| DevelopmentCRMProvider | Persists the authoritative local Lead, initial FollowUp, and creation audit state. It is not GoHighLevel. |
| Lifecycle service | Owns transactional booking/follow-up state and the development email boundary to Mailpit. |
| HighLevel adapter | Optional HighLevel-specific HTTP projection for the documented contact/opportunity subset. It composes local persistence rather than replacing PostgreSQL reliability truth. |
| HighLevel Contract Simulator | Separate loopback-only HTTP service and interview UI. It is local test infrastructure, not HighLevel or a vendor sandbox. |
| PostgreSQL | Stores lead, follow-up, appointment, source/server timestamp, idempotency, and audit state by correlation ID. |
| CRM recovery job | Stores the validated payload before delivery, bounded lease, attempt history, safe errors, due time, and final CRM identity independently of a Lead row. |
| Mailpit | Accepts local development SMTP messages and exposes them on a loopback web UI. It is not an external email provider. |
| Operations read projection | Exposes allowlisted summaries, paged jobs, job detail, and incidents from the same local PostgreSQL records. It does not invoke recovery actions or external services. |

## Demonstration service-request source

The browser form is one controlled website service-request source used to make the live
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

The safe default remains `DevelopmentCRMProvider` plus the existing lifecycle and CRM-write
recovery services. Optional `highlevel_simulator` mode preserves that local persistence and adds a
separate HighLevel-specific HTTP projection to the local contract simulator. `highlevel_live` is a
separately credentialed, official-host-pinned Contact/Opportunity projection whose synthetic
real-sub-account verification is recorded in `docs/phase-6-live-highlevel-verification.md`. No
live calendar, appointment sync, external email provider, or automatic HighLevel lifecycle-stage
synchronization is configured.

Simulator mode accepts only exact local HTTP hosts with an explicit port and does not use
environment proxy settings. It cannot be configured with an arbitrary external/vendor URL.

The simulator implements only contact upsert/read/lookup and opportunity search/create/update.
Automatic lifecycle and appointment synchronization are omitted because they require a durable
external-sync boundary to preserve the approved booking transaction semantics.

## Read-only operations view

`/operations.html` is a local demonstration page over `/api/operations/*`, separate from protected recovery-worker contracts. It reports current durable job-state counts at an explicitly labelled observation time, pages jobs by `created_at DESC, id DESC`, and shows safe attempt/incident history for a selected job. A due time is eligible retry information only for `retry_wait`; it is not evidence of an attempted failure. A completed job may be an ordinary intake rather than a recovery.

Browser projections omit payloads, lease/quota tokens, credentials, provider response bodies, and arbitrary audit metadata. GET handlers issue ordinary reads: they do not lock, claim, expire, retry, resolve, commit, or call n8n, NVIDIA, SMTP, or the CRM write boundary. Numeric execution references may link to the configured loopback n8n editor route; all other values remain text. This is a local synthetic-data boundary, not production authentication or health monitoring.
