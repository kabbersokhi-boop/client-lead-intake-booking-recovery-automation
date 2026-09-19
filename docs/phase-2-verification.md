# Phase 2 Verification — Lifecycle + Booking

Verified locally on 2026-09-20 IST from the approved Phase 1 baseline `eb7cf645aa9937127b1cac1591b5a2cb0a1d9f35`. All names, addresses, phone numbers, messages, and identifiers below are synthetic.

## Lifecycle design

The pipeline stays deliberately small:

- `new_lead`: intake persisted; scheduling alone does not imply contact.
- `contacted`: the due follow-up email was accepted by the local development email sink.
- `appointment_booked`: an appointment was durably created.

Email follow-ups have separate `pending`, `sent`, and `cancelled` states. An email-capable lead schedules one follow-up at creation using `FOLLOW_UP_DELAY_SECONDS`; the local default is 120 seconds solely to keep the demonstration repeatable. Phone-only leads schedule no email follow-up.

The booking domain operation is a single database transaction: it creates the appointment, transitions the lead, cancels a pending follow-up, and records concise audit events. n8n visibly orchestrates validation, that semantic operation, confirmation delivery, and the browser response. The backend remains the development CRM/domain boundary rather than becoming the overall automation engine.

## Booking and time handling

The browser sends an offset-free business-local value plus `America/Vancouver`. The backend rejects another timezone, resolves the value with the configured business zone, rejects nonexistent local times, and stores the canonical timezone-aware appointment instant. The UI labels displayed appointment values as Surrey business time.

Each new attempt receives a `booking_request_id`. An unchanged ambiguous retry reuses it. The database uniquely constrains both that request identity and the active appointment per lead. A replay returns the same appointment and the confirmation boundary reports `already_sent`; a different request after an active appointment returns HTTP 409. This is idempotency with state checks, not an exactly-once claim. Rescheduling and cancellation are outside Phase 2.

## Local email boundary

Mailpit is a loopback-visible development/test sink at `http://localhost:18025`; its SMTP port is private to Compose services. It is not a production email provider and no external recipient was contacted. Templates are intentionally simple, and audit metadata records delivery state without storing full email bodies.

## Scenario A — due follow-up

Synthetic correlation ID: `42e49521-2d01-452d-8dd6-fcfa7573c89e`

1. n8n intake execution `151` persisted the lead with safe `fallback_invalid` AI handling, `pipeline_stage=new_lead`, and follow-up `67dd11da-8f60-45c4-9432-e6431578fb02` in `pending` state. Its due time was `2026-09-19T19:11:53.726636Z`.
2. The active scheduled workflow executed successfully at one-minute intervals. Execution `157` ran after the due time and generated a real Mailpit message with subject `Following up on your service request`.
3. The trace then showed follow-up `sent`, `sent_at=2026-09-19T19:12:16.075786Z`, pipeline `contacted`, and `follow_up.sent` plus `pipeline.stage_changed` audit events.
4. Execution `158` rechecked the same state on the next scheduler tick. Mailpit remained at two total scenario messages, proving this already-sent follow-up did not send again.

Result: passed.

## Scenario B — book before follow-up

Synthetic correlation ID: `e519621d-8730-4544-92c4-253593793bb2`  
Synthetic booking request ID: `4c228a78-5fe1-424c-abb6-2df0929a1c4f`

1. n8n intake execution `152` created a second lead with `new_lead` and pending follow-up `b6671cb9-148a-49a0-a2ac-6b86c8431251`.
2. Booking execution `154` created appointment `750acb6b-0675-4977-a7bb-b21ef5a3e3a5` for `2026-09-22T10:30` America/Vancouver (`2026-09-22T17:30:00Z`).
3. The same transaction moved the pipeline to `appointment_booked` and changed the pending follow-up to `cancelled`. The trace contains `appointment.booked`, `pipeline.stage_changed`, and `follow_up.cancelled`.
4. Mailpit accepted one message with subject `Your appointment is booked`; `booking_confirmation.sent` and its timestamp are visible in the trace.
5. Execution `155` replayed the identical booking request. It returned HTTP 200, the same appointment ID, `booking_state=replayed`, and `confirmation_state=already_sent`. Mailpit did not receive another message.
6. The original follow-up due time passed. Scheduled executions `157` and `158` left it cancelled with `sent_at=null`; Mailpit still held only the two expected messages across both scenarios.
7. A distinct booking request for the same lead returned controlled HTTP 409 and did not send email.

Result: passed.

## Live-tested boundaries

- Existing standalone n8n `2.39.8`; no second installation was created.
- All three public workflow exports imported, published, restarted, and confirmed active.
- Real n8n webhook executions for both intake and booking, plus real schedule-trigger executions.
- Existing NVIDIA NIM model `openai/gpt-oss-20b` was called on both new intakes. Both live Phase 2 calls returned model output that failed the application schema and therefore persisted through the approved safe fallback. The approved Phase 1 successful-enrichment evidence remains in `docs/phase-1-verification.md`.
- Real PostgreSQL migration and durable state transitions.
- Real SMTP generation into Mailpit: exactly two messages, one per required business path.
- Booking replay, distinct-booking conflict, already-sent follow-up recheck, and cancelled-follow-up non-send.
- Trace API returns the new lifecycle state and audit sequence.

No browser automation binary was used. The browser helper logic is deterministic-test covered and the updated assets were served by the live backend; final visual layout remains a human check at `http://localhost:18000`.

## Development-only and excluded

The CRM adapter, synthetic appointment calendar, read-only trace UI, short follow-up delay, and Mailpit delivery are development/demo components. No GoHighLevel, Make.com, external email, calendar provider, SMS/WhatsApp, recovery queue, deliberate failure injection, or other Phase 3 feature was implemented.

## Review correction verification

The following checks were run after the Phase 2 review corrections. They supplement rather than replace the original evidence above.

### Lifecycle replay contracts

- Scenario A correction correlation: `bd4ce7ca-b15c-4c6a-9bb1-48923ab5235f`.
- Scenario B correction correlation: `f66046a0-fbb2-4eaa-b8c7-6e4f8397edaa`.
- Scenario B booking request: `f78df2e5-ed92-4704-9562-8d8d97c5ed64`; appointment: `b8d8511b-3b4f-411b-b91f-528ccc0fbc25`.

n8n execution `188` created Scenario A with safe `fallback_invalid`, `new_lead`, and a pending follow-up. Scheduled execution `196` sent that follow-up and moved the pipeline to `contacted`. Execution `197` replayed the exact original intake after contact and returned HTTP 200 with the same lead, persisted `fallback_invalid`, `contacted`, and `sent` state.

n8n execution `190` created Scenario B with live successful NVIDIA enrichment. Execution `191` booked the appointment, moved the pipeline to `appointment_booked`, cancelled the pending follow-up, and sent one confirmation. Execution `192` replayed the exact original intake after booking and returned HTTP 200 with the same lead, persisted `enriched`, `appointment_booked`, and `cancelled` state. Execution `193` replayed the booking with the same appointment ID and `confirmation_state=already_sent`.

Mailpit contained two messages before these correction scenarios, three after Scenario B confirmation, and four after Scenario A dispatch. Both intake replays and the booking replay left the count at four. The scheduled dispatcher also passed Scenario B's cancelled due time without sending.

These results do not rewrite the earlier Phase 2 NVIDIA record: the original two Phase 2 calls remain `fallback_invalid`. In the correction run, Scenario A was `fallback_invalid` because output failed application schema validation, while Scenario B was enriched. Neither result is described as an entitlement failure.

### Response and error boundaries

The installed n8n `2.39.8` error envelope was exercised through a real past-date booking request. The backend HTTP 422 was preserved by n8n as HTTP 422 with a safe business-time validation message, and Mailpit did not change.

Executable workflow fixtures additionally verify that malformed successful booking bodies, missing or invalid canonical appointment timestamps, wrong timezones, and identity mismatches stop before the confirmation branch. Backend 404/409/422 statuses retain controlled user-facing responses. Once an appointment response is verified, a confirmation transport or response-validation failure returns the known appointment ID/time with `confirmation_state=unconfirmed` rather than claiming booking failure. The same booking may retry that existing confirmation boundary; no recovery queue was added.

### PostgreSQL concurrency

A deterministic disposable-PostgreSQL coordination test reproduced the pre-fix lock inversion as `DeadlockDetected`; this was a local test reproduction, not a previously observed client incident. The repaired implementation locks `Lead` first, then reloads and locks `FollowUp` before deciding whether email may send.

Four coordinated PostgreSQL tests now pass with bounded event waits:

- booking owns the lifecycle decision first, so later dispatch observes `cancelled` and sends zero messages;
- dispatch owns it first, sends once, then booking finishes with final pipeline `appointment_booked`;
- two dispatchers send one message;
- two booking-confirmation requests send one message and the second returns `already_sent`.

SMTP acceptance and the later database commit remain separate effects. The lock tests prove normal successful serialization, not universal exactly-once delivery after a crash or lost acknowledgement. The code does not blindly retry an aborted SMTP-containing transaction; uncertain-delivery recovery remains outside Phase 2.

### Browser state boundary

Browser-helper tests verify that beginning lead B clears lead A as the accepted booking target and hides A's booking result, while successful acceptance of B binds the booking context to B and keeps A's old result hidden. Pending request records in `sessionStorage` are retained for idempotent matching rather than discarded. The live assets were served, but the lead-A/failed-lead-B visual sequence still requires a human browser layout check.
