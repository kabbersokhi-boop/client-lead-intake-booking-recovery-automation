# HVAC Lead Automation — n8n, GoHighLevel, Recovery & Reporting

An end-to-end HVAC lead automation system that captures service enquiries, validates and enriches context, persists durable workflow state, projects verified records into HighLevel (GoHighLevel), supports booking and follow-up lifecycle automation, recovers uncertain CRM writes, and publishes aggregate management reporting through Make and Google Sheets.

\`n8n\` · \`HighLevel (GoHighLevel)\` · \`FastAPI\` · \`PostgreSQL\` · \`NVIDIA NIM\` · \`Make\` · \`Google Sheets\` · \`Mailpit\` · \`Docker Compose\`

[![Backend CI](https://github.com/kabbersokhi-boop/client-lead-intake-booking-recovery-automation/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/kabbersokhi-boop/client-lead-intake-booking-recovery-automation/actions/workflows/ci.yml)

## What this system does

| Capability | Implementation |
| --- | --- |
| Lead capture | Customer-facing form → n8n validation/normalization → FastAPI |
| AI enrichment | NVIDIA NIM extracts bounded service context; invalid or unavailable output falls back safely |
| CRM projection | Real HighLevel Contact + Opportunity in **HVAC Service Pipeline → New Lead** |
| Durable state | PostgreSQL stores canonical lead, lifecycle, audit, CRM job, attempt, lease and incident state |
| Lifecycle | Replay-safe local booking, scheduled follow-up, cancellation rules and development email |
| Recovery | Reconciliation-before-retry, bounded attempts, \`Retry-After\`, leases, quota pacing and operator review |
| Operations | Read-only recovery dashboard with job, attempt, incident and trace visibility |
| Reporting | FastAPI aggregates → n8n → Make → Google Sheets dashboard, without customer PII |

The core design is intentionally split by responsibility:

> **n8n orchestrates. PostgreSQL remembers. FastAPI owns the application and reliability boundary. HighLevel is the external CRM projection. The simulator is the deterministic failure laboratory.**

## Architecture

\`\`\`mermaid
flowchart TB
    C[Customer] --> W[Website request form]
    W --> I[n8n · Lead Intake]
    I --> V{Request valid?}
    V -- "no" --> X[Return validation error]
    V -- "yes" --> N[Optional NVIDIA NIM extraction<br/>validated result or safe fallback]
    N --> A[FastAPI application boundary]
    A --> P[(PostgreSQL<br/>durable application + recovery state)]
    A --> H[HighLevel adapter]
    H --> HL[REAL HighLevel sub-account<br/>Contact + Opportunity<br/>HVAC Service Pipeline · New Lead]

    W --> B[n8n · Appointment Booking]
    B --> A
    F[Scheduled n8n · Follow-up Dispatch] -- "poll due items" --> A
    A --> M[SMTP development email]
    M --> MP[Mailpit · local test inbox]

    P --> R[FastAPI · aggregate reporting endpoint]
    R --> MR[n8n · Management Reporting]
    MR --> MK[Make]
    MK --> S[Google Sheets dashboard]

    H -. "separate fault-test configuration" .-> SIM[Local HighLevel contract simulator<br/>deterministic failure laboratory]
\`\`\`

A valid enquiry is persisted before an external CRM effect is trusted. Workflow executions can end; the durable record of what should happen, what was attempted, and what completed survives in PostgreSQL.

## HighLevel (GoHighLevel) CRM integration

HighLevel is a real external integration in this project, not a simulated happy path. The live adapter uses a protected **Private Integration Token (PIT)** against the official HighLevel API and was verified end to end through the website, n8n, FastAPI/PostgreSQL and a real HighLevel sub-account.

### What the integration owns

| Area | Behavior |
| --- | --- |
| Contact projection | Reuse an application-owned matching Contact or create one when safely absent |
| Opportunity projection | Create/reconcile the matching Opportunity in **HVAC Service Pipeline → New Lead** |
| Stable identity | Contact stores submission + correlation identity; Opportunity stores submission identity |
| Replay safety | Reconcile existing CRM effects before any repeat create |
| Identity conflicts | Ambiguous, foreign or mismatched records fail closed instead of being overwritten |
| Authentication | PIT-based server-to-server integration; OAuth is not claimed or implemented |
| Provider boundary | HighLevel-specific translation and reconciliation stay behind the FastAPI provider layer |
| Native automation | A saved **HVAC Lead Acknowledgement** workflow targets the New Lead stage |
| Reusable configuration | A selective Snapshot contains the pipeline, acknowledgement workflow and integration identity fields |

The custom identity fields are important because email and phone alone are not sufficient business identities. A remote write may commit even if its acknowledgement is lost; the adapter therefore needs a stable way to determine whether the intended Contact and Opportunity already exist before another create is safe.

The live PIT path also validates vendor responses rather than treating any 2xx response as proof. Contact and Opportunity identity, location, pipeline and custom-field linkage are checked before the application accepts reconciliation as complete.

![Synthetic Contact projected into the real HighLevel sub-account](docs/assets/readme/03_highlevel_contact_jordan_live.png)

*Live HighLevel evidence shows an integration-created Contact carrying the application identity fields and linked Opportunity activity.*

![Synthetic Opportunity projected into the HVAC Service Pipeline](docs/assets/readme/04_highlevel_opportunity_new_lead.png)

*The live Opportunity is linked to the projected Contact and placed in HVAC Service Pipeline → New Lead.*

The native acknowledgement workflow remains **Draft/unpublished** because the demo sub-account is not configured as a production sender. Its saved trigger/action configuration is evidence of native HighLevel workflow setup; it is separate from the Mailpit development-email path.

A selective Snapshot packages only reusable CRM configuration: the pipeline, acknowledgement workflow and three integration identity fields. It deliberately excludes Contacts, Opportunities and their history.

**Current lifecycle boundary:** the initial Contact + Opportunity projection is live and verified. Later local \`contacted\` and \`appointment_booked\` transitions do **not** automatically move the existing HighLevel Opportunity stage, and the local appointment does not reserve a HighLevel calendar slot. A production-grade extension should use a separate durable desired-state/outbox process with retries, reconciliation and supersession of stale stage requests rather than an inline booking HTTP call.

The retained live evidence and provider review are in [Phase 6 live HighLevel verification](docs/phase-6-live-highlevel-verification.md), [Phase 6 verification](docs/phase-6-verification.md) and [Phase 6 self-review](docs/phase-6-self-review.md).

## End-to-end customer journey

The browser creates two different identifiers for two different jobs:

- \`submission_id\` identifies the logical business operation that should be applied once.
- \`correlation_id\` traces that operation across intake, persistence, CRM delivery, attempts, incidents and lifecycle events.

An unchanged browser retry reuses both identifiers. Editing the customer input intentionally creates a new submission identity.

n8n rejects invalid input before the AI call, normalizes contact data while preserving the original message, and optionally asks NVIDIA NIM for service context. FastAPI validates the resulting application contract again, admits the durable CRM job, persists canonical state in PostgreSQL, and projects through the configured CRM provider.

A customer-facing success response is returned only after the expected identity and lifecycle shape are verified. If the application has durably accepted the work but the external CRM effect is not yet confirmed, the response is **queued** rather than fabricating CRM success.

![Saved HVAC request in the customer-facing website](docs/assets/readme/01_website_saved_request.png)

*The customer view presents the saved lifecycle state while keeping low-level identifiers behind expandable technical details.*

![Successful n8n lead-intake execution](docs/assets/readme/02_n8n_intake_success.png)

*The intake workflow validates, normalizes, performs bounded enrichment, persists through FastAPI and returns a contract-checked result.*

## Booking, follow-up and development email

Booking and follow-up are separate workflows from lead intake.

A booking request uses its own stable \`booking_request_id\`. The backend validates Surrey business time (\`America/Vancouver\`), serializes concurrent lifecycle changes with PostgreSQL row locks, persists one appointment, advances the local lifecycle to \`appointment_booked\`, and cancels a still-pending follow-up in the same database transaction. Replaying the same booking is safe; a different second booking for the same lead is a controlled conflict.

The scheduled follow-up workflow polls FastAPI for due pending follow-ups. If follow-up dispatch wins the database lock first, it sends once and moves the local lifecycle to \`contacted\`; if booking wins first, the pending follow-up is cancelled and no follow-up email is sent.

![Successful appointment-booking workflow](docs/assets/readme/05_n8n_appointment_booking_success.png)

*The booking workflow validates the request, persists the lifecycle change, then separately attempts confirmation delivery.*

![Booking confirmation rendered in Mailpit](docs/assets/readme/06_mailpit_booking_confirmation.png)

*Mailpit shows the generated development message with persisted service, location, preferred time and appointment details.*

Mailpit is a local SMTP sink. It proves message generation, personalization, SMTP acceptance and rendering; it does **not** prove production email delivery. The saved local appointment also does not reserve technician capacity or an external calendar.

## Durable CRM delivery and recovery

> **“I didn't just connect n8n directly to HighLevel and hope retries were safe. I separated orchestration, durable state, vendor projection, and deterministic fault testing.”**

A remote CRM write can fail cleanly, be rate-limited, time out, or commit remotely while its acknowledgement is lost. Blindly replaying a create after an uncertain result can duplicate customer records.

The recovery design persists the intended business effect first, then makes the external effect recoverable:

\`\`\`mermaid
flowchart TD
    P[Persist canonical CRM job in PostgreSQL]
    P --> L[Claim one due job with a bounded lease]
    L --> R[Reconcile by stable submission identity]
    R --> E{External effect verified?}
    E -- "yes" --> C[Complete without another create]
    E -- "confirmed absent" --> Q[Obtain shared quota permission]
    E -- "inconclusive" --> H[Defer, block or hold for review]
    Q --> A[Record a real API attempt]
    A --> W[Write only the missing CRM effect]
    W --> V{Response + identity verified?}
    V -- "yes" --> C
    V -- "429 / transient / timeout" --> T[Persist failure<br/>honor Retry-After or bounded backoff]
    V -- "credential / business / identity" --> H
    T --> P
\`\`\`

PostgreSQL retains the prepared payload, payload fingerprint, job state, lease ownership, attempt history, retry timing and incident linkage. Expired leases can be reclaimed; stale workers cannot complete work owned by a newer lease. Scheduling deferrals do not pretend to be API attempts. Authentication failures can pause new claims until operator intervention. Retry history remains visible instead of being reset.

The delivery model is **at-least-once retry with idempotent business effects and explicit reconciliation**. It does not claim universal exactly-once transport semantics.

### Controlled HTTP 429 proof

Execution **283** is retained evidence from a deliberately orchestrated local fault-injection test. It is **not** a production incident and **not** evidence of a real HighLevel rate limit.

The test first persisted 12 synthetic CRM jobs, then deliberately sent the prepared batch through an unsafe diagnostic path against the controlled local CRM boundary. Earlier writes committed before a real HTTP 429 caused n8n execution 283 to fail. The Error Trigger workflow recorded the incident while the intended work remained durable in PostgreSQL.

Recovery did not rerun the batch blindly. It reconciled each unfinished job by stable identity, skipped effects that already existed, and wrote only confirmed-missing effects. The final scoped result was **12/12 completed with zero duplicate submission IDs**.

![Controlled local HTTP 429 failure in n8n execution 283](docs/assets/readme/07_controlled_429_failure_execution_283.png)

*The diagnostic path intentionally bypasses normal pacing so a real HTTP 429 can be observed safely against the controlled local boundary.*

![Durable recovery history after the controlled failure](docs/assets/readme/08_durable_recovery_283_to_294.png)

*The durable attempt history preserves the failed 429 and the later verified recovery; the original failed n8n execution remains truthful.*

The full retained chain is documented in [Phase 3 verification](docs/phase-3-verification.md) and the [execution 283 postmortem](docs/phase-3-failed-run-postmortem.md).

## Read-only operations view

The project includes a local operator-facing view at \`/operations.html\` for inspecting recovery state without mutating it.

It exposes allowlisted projections of:

- recovery job counts and state filters;
- exact lookup by job, submission or correlation ID;
- selected job state, attempt history and next eligibility;
- linked incident history and retained unlinked diagnostic records;
- lifecycle trace context;
- safe local n8n execution links only when the workflow/execution route matches the configured loopback editor boundary.

The Operations API intentionally omits prepared payloads, lease tokens, quota permits, authorization material and unsafe recorded values. Its GET routes are tested to leave durable state unchanged. Recovery actions such as retry/requeue remain controlled operator operations outside this read-only UI.

See [Phase 4 verification](docs/phase-4-verification.md) for the retained evidence.

## AI is a bounded helper

NVIDIA NIM is used only for service-context extraction. The n8n request asks for five fields: service type, location, preferred time, urgency and a short summary. Output is constrained to JSON mode, bounded in size, and validated against exact keys, allowed enums and field types.

**HTTP 200 is not treated as model success unless the payload passes application validation.**

Timeouts, provider errors, malformed JSON, extra fields, unsupported enums or unusable values result in a safe fallback. A valid customer enquiry continues without AI enrichment and can be marked for review.

The model does not decide contact identity, consent, pricing, availability, appointment truth, CRM truth or technician dispatch. Recovery reuses the canonical stored payload instead of rerunning AI and allowing model drift to change an already-admitted business operation.

## Management reporting with Make + Google Sheets

Reporting is deliberately downstream and non-critical:

\`\`\`text
PostgreSQL → FastAPI aggregate endpoint → n8n Management Reporting
           → Make Custom Webhook → Make Data Store routing
           → Google Sheets Daily Reports → HVAC Management Dashboard
\`\`\`

FastAPI performs the database aggregation and returns an authenticated, sanitized **16-field** management contract. n8n validates the exact field set, report identity, Vancouver business-day window and count reconciliation before sending anything to Make.

The report contains aggregate counts and service categories, not customer names, email addresses, phone numbers or enquiry text. Individual customer records belong in the application and HighLevel; the Sheets dashboard is intentionally aggregate-only.

The Make scenario uses a stable daily \`report_key\`: the first report for a business date adds a row, while subsequent reports search for and update that same row. Destination inspection caught a real mapping mistake where every Make module was green but the Sheet still contained stale values; the mapping was corrected so the existing row receives values from the fresh webhook payload.

![Make management-reporting scenario](docs/assets/readme/09_make_reporting_scenario.png)

*Make routes a new daily report to Add Row and an existing report key to Search Rows → Update Row.*

![HVAC aggregate management dashboard in Google Sheets](docs/assets/readme/10_management_dashboard.png)

*The dashboard is a management aggregate, not a second customer database.*

The n8n reporting workflow is currently manual/inactive by design. A Make or Google Sheets failure cannot prevent intake, booking or durable CRM recovery. See [Phase 5 verification](docs/phase-5-verification.md).

## Workflow inventory

| Area | n8n workflow | Responsibility |
| --- | --- | --- |
| Intake | \`Lead Intake - Validation, AI Enrichment and CRM Persistence\` | Validate, normalize, enrich, persist and return a truthful intake result |
| Lifecycle | \`Lifecycle - Appointment Booking and Confirmation\` | Persist a local appointment, transition lifecycle and hand off confirmation |
| Lifecycle | \`Lifecycle - Dispatch Due Follow-ups\` | Poll due follow-ups, send the development message and record lifecycle state |
| Recovery | \`CRM Lead Write Recovery Dispatch\` | Claim one job, reconcile identity, obtain quota permission, attempt/settle delivery |
| Recovery | \`CRM Recovery Failure Recorder\` | Capture safe n8n error context as a durable recovery incident |
| Diagnostic | \`Controlled CRM Rate-Limit Diagnostic\` | Inactive fault-injection path used only against the controlled local boundary |
| Reporting | \`Management Reporting - HVAC Snapshot\` | Validate aggregate report contract and send it to Make; manual/inactive |

Responsibilities are split so a customer-intake workflow does not also become the retry engine, reporting pipeline and operator console.

## Engineering ownership

| Component | Owns |
| --- | --- |
| Website | Request identity, form submission, truthful result display, booking UI and trace access |
| n8n | Visible orchestration and scheduling |
| FastAPI / Python | Schemas, domain services, lifecycle APIs, recovery APIs, provider boundary, reporting and safe operations projections |
| PostgreSQL | Durable application, lifecycle, audit and recovery truth |
| HighLevel adapter | Vendor-specific Contact/Opportunity mapping, identity checks, projection and reconciliation |
| HighLevel | Real external CRM representation |
| Local HighLevel contract simulator | Deterministic contract/fault testing only; never presented as the live CRM |
| NVIDIA NIM | Optional, schema-validated service-context extraction |
| Mailpit | Local SMTP acceptance and rendered-message inspection |
| Make + Google Sheets | Non-critical aggregate management reporting |
| Docker Compose | Repeatable local service topology |

## Verification

The deterministic suite currently covers:

- **165 Python tests**, including the **58-test focused HighLevel adapter subset**;
- **32 browser/helper tests** across the customer UI, Operations UI and simulator helpers;
- **45 n8n workflow tests**;
- Ruff linting, JSON parsing, shell syntax, Docker Compose validation, diff checks and tracked-content secret scanning.

The HighLevel subset is included inside the 165 Python tests, not additive.

Beyond deterministic CI, the repository retains separate live/manual evidence for NVIDIA NIM, n8n, Mailpit, Make/Google Sheets and the real HighLevel integration. The CI badge above follows \`main\`; exact historical verification checkpoints are retained in [docs/](docs/) rather than hard-coding a commit that becomes stale on the next documentation change.

The test suite specifically exercises replay/idempotency, PostgreSQL concurrency, booking/follow-up races, stale leases, exact attempt ownership, \`Retry-After\`, credential pauses, lost acknowledgement, identity conflicts, malformed upstream success, DST-aware reporting windows, PII minimization, read-only Operations projections and controlled CRM faults.

## Scope and boundaries

This repository uses synthetic test/demonstration data. It is an engineering case study and reference implementation, not a claim that this exact repository handled historical production customer traffic.

The verified boundaries are intentionally explicit:

- real HighLevel evidence covers initial Contact + Opportunity projection and replay reconciliation;
- automatic later lifecycle-stage synchronization to HighLevel is not implemented;
- local appointments do not reserve technicians or external/HighLevel calendar slots;
- the HighLevel acknowledgement workflow is configured but unpublished, and no production HighLevel email send is claimed;
- Mailpit is development email only;
- simulator failures are controlled tests, not vendor outage or vendor-rate-limit evidence;
- the reporting path is aggregate-only, downstream and non-critical;
- SMTP acceptance and the later database commit are not an atomic distributed transaction;
- delivery uses at-least-once retry with idempotent business effects and explicit reconciliation rather than a universal exactly-once guarantee.

## Explore the implementation

| Area | Code and evidence |
| --- | --- |
| Customer website | [\`frontend/\`](frontend/) |
| n8n workflows and tests | [\`n8n/\`](n8n/) |
| FastAPI routes and schemas | [\`backend/app/api/\`](backend/app/api/), [\`backend/app/schemas/\`](backend/app/schemas/) |
| Persistence models and migrations | [\`backend/app/models/\`](backend/app/models/), [\`backend/migrations/\`](backend/migrations/) |
| Lifecycle service | [\`backend/app/services/lifecycle_service.py\`](backend/app/services/lifecycle_service.py) |
| Durable recovery service | [\`backend/app/services/recovery_service.py\`](backend/app/services/recovery_service.py) |
| Reporting service | [\`backend/app/services/reporting_service.py\`](backend/app/services/reporting_service.py) |
| HighLevel provider/client | [\`backend/app/providers/highlevel.py\`](backend/app/providers/highlevel.py) |
| Controlled HighLevel simulator | [\`backend/simulator/\`](backend/simulator/) |
| Backend tests | [\`backend/tests/\`](backend/tests/) |
| Verification and self-review | [\`docs/\`](docs/) |

## Run locally

For a fresh checkout, copy the safe root [\`.env.example\`](.env.example) to \`.env\`, replace the local placeholder credentials, then run:

\`\`\`bash
docker compose up --build
\`\`\`

The tracked configuration defaults to the local \`development\` CRM provider. The project also supports an explicitly local \`highlevel_simulator\` mode for deterministic contract/fault tests and an opt-in \`highlevel_live\` mode that requires a protected PIT plus verified resource mappings. Live secrets belong only in protected runtime configuration and must never be committed, logged or placed in screenshots.

Local interfaces:

| Interface | Address |
| --- | --- |
| Customer website | \`http://localhost:18000\` |
| Read-only Operations | \`http://localhost:18000/operations.html\` |
| n8n | \`http://localhost:5678\` |
| Mailpit | \`http://localhost:18025\` |
| Controlled simulator | \`http://localhost:18080\` |

For the browser walkthrough and retained operational procedures, see the [demo runbook](docs/interview-demo-runbook.md) and [recovery runbook](docs/phase-3-runbook.md).
