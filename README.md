# HVAC Lead Automation — Intake, Booking & Recovery

[![Backend CI](https://github.com/kabbersokhi-boop/client-lead-intake-booking-recovery-automation/actions/workflows/ci.yml/badge.svg)](https://github.com/kabbersokhi-boop/client-lead-intake-booking-recovery-automation/actions/workflows/ci.yml)

**A customer enquiry becomes a verified CRM record, a saved appointment, and a refreshed management report—with durable recovery when an API fails.**

Built with **n8n · FastAPI · PostgreSQL · NVIDIA NIM · GoHighLevel · Make · Google Sheets**.

## Watch the complete demo

[![Preview of the HVAC automation demo: enquiry, n8n, live CRM, Make, and dashboard](docs/assets/portfolio/demo-preview.gif)](https://github.com/kabbersokhi-boop/client-lead-intake-booking-recovery-automation/raw/refs/heads/main/docs/assets/video/HVAC-End-to-End-Demo.mp4)

*Short looping preview above; click for the complete recording.*

**[Watch / download the full demo — 2:27, 1080p MP4](https://github.com/kabbersokhi-boop/client-lead-intake-booking-recovery-automation/raw/refs/heads/main/docs/assets/video/HVAC-End-to-End-Demo.mp4)** · Silent, ready for voiceover. This is the single edited portfolio video, not a collection of raw recordings.

The recording uses a synthetic customer with **live GoHighLevel, Make, and Google Sheets**. Booking is local; email is captured in Mailpit. Recovery evidence is presented separately below rather than staged into the video.

### The demo in six quick steps

| Time | What happens | What to look for |
|---|---|---|
| 0:05 | Type and submit a furnace-service enquiry | The actual customer-facing form and verified acceptance |
| 0:24 | Inspect the successful n8n intake | Validation, optional AI enrichment, persistence, and response verification |
| 0:38 | Open the live GoHighLevel Contact | The synthetic customer and linked Opportunity creation audit |
| 0:49 | Save an appointment and verify the lifecycle | Successful booking workflow, **Appointment Booked** in live CRM, local confirmation, and completed job |
| 1:24 | Run reporting through n8n and Make | Successful **New Report** branch and a fresh daily row in Sheets |
| 1:55 | Refresh the same report | Successful **Existing Report** branch, updated timestamp, no duplicate row, and refreshed dashboard |

[Screenshot tour and recording evidence](docs/portfolio-demo.md) · [Run the credential-free local demo](#guided-local-demo) · [Inspect retry and error recovery](#recovery-is-part-of-the-design) · [Architecture](docs/architecture.md)

## Why this system exists

Service businesses need more than a webhook that works once. This system captures enquiries, enriches them with AI, creates and updates CRM records, manages follow-up and local booking, and makes incomplete work inspectable and recoverable.

The project focuses on a problem that simple webhook automations usually ignore: an HTTP request can time out even after the remote system has saved the record. Retrying blindly can create duplicate contacts, opportunities, appointments, or messages. This system persists every intended operation, assigns stable identities, checks the remote result, and retries only when it is safe.

## What this project demonstrates

- **AI-assisted intake:** extracts service type, location, preferred time, urgency, and a short summary from free-form enquiries.
- **Durable workflow execution:** accepts valid leads into PostgreSQL before relying on an external CRM call.
- **Safe CRM recovery:** handles rate limits, server errors, timeouts, malformed responses, and lost acknowledgements.
- **Idempotency:** repeated submissions and booking requests reuse the original business operation instead of creating duplicates.
- **Auditable operations:** stores request identities, attempts, incidents, retry timing, and lifecycle history for inspection.
- **Customer lifecycle automation:** supports follow-up, local appointment booking, confirmation email, CRM stage updates, and daily reporting.
- **Honest AI boundaries:** invalid or unavailable AI results are marked for review while the original lead continues through the system.

## System architecture

```mermaid
flowchart LR
    Customer[Customer enquiry] --> N8N[n8n intake workflow]
    N8N --> AI[AI extraction and validation]
    AI --> API[FastAPI application]
    API --> DB[(PostgreSQL)]
    API --> CRM[HighLevel CRM]
    DB --> Recovery[n8n recovery worker]
    Recovery --> API
    Customer --> Booking[n8n booking workflow]
    Booking --> API
    API --> Mail[Email / Mailpit]
    DB --> Report[Daily aggregate report]
    Report --> Make[Make.com]
    Make --> Sheets[Google Sheets]
```

**Responsibility split:** n8n coordinates webhooks, schedules, and external calls. FastAPI owns validation, transactions, lifecycle rules, and provider adapters. PostgreSQL remains the source of truth for work that must survive workflow or service restarts.

## A complete lead journey

1. The browser creates a stable submission ID and correlation ID.
2. n8n validates and normalizes the enquiry.
3. NVIDIA NIM optionally extracts structured service information.
4. FastAPI stores a durable CRM job and its business-data fingerprint.
5. The HighLevel adapter finds or creates the matching Contact and Opportunity.
6. A repeated request is reconciled against the stored and remote identities.
7. Follow-up and booking update local state and the desired CRM stage.
8. Recovery workers retry incomplete work using persisted schedules and attempt history.
9. Aggregate daily results can be sent through Make to Google Sheets.

The [visual walkthrough](docs/portfolio-demo.md#1-customer-enquiry-and-verified-intake) shows the real form, successful n8n execution, appointment result, and persisted job—not just a workflow canvas.

## GoHighLevel CRM integration

In `highlevel_live` mode, the provider adapter uses the official HighLevel REST API to create or reconcile a Contact and its linked Opportunity in the configured service pipeline. Application-owned submission and correlation fields bind the remote records to the original request. The adapter reads the records back and verifies their identity, location, pipeline, stage, and Contact relationship before treating the operation as complete.

![Live GoHighLevel Opportunity at Appointment Booked](docs/assets/portfolio/06-live-pipeline.png)

*The recorded customer journey finishes with the linked Opportunity at Appointment Booked. Contact creation and the booking workflow are shown in the [screenshot tour](docs/portfolio-demo.md#2-live-crm-and-booking).*

### Native GoHighLevel automation

Alongside the API integration, the project includes a native **HVAC Lead Acknowledgement** workflow: **Opportunity enters New Lead → acknowledgement email**. It demonstrates CRM-side trigger configuration and a personalized message using `{{contact.first_name}}`.

<details>
<summary><strong>View the configured native GHL workflow (Draft)</strong></summary>

![Native GoHighLevel acknowledgement workflow with New Lead trigger and personalized email action, retained in Draft](docs/assets/readme/11_highlevel_native_ack_workflow.png)

*Configured workflow, retained in **Draft**. This screenshot demonstrates the trigger and email-action setup—not a verified execution or delivered email. It is separate from the recorded n8n/Mailpit confirmation path and was not activated for the video.*

</details>

## Recovery is part of the design

Each logical enquiry has a stable identity and normalized fingerprint. Before repeating a CRM write, the application checks whether the intended Contact or Opportunity already exists. This matters when a remote write succeeds but its response is lost.

The recovery layer includes:

- durable jobs and numbered attempts;
- bounded database leases for worker ownership;
- exponential retry scheduling and `Retry-After` support;
- reconciliation before another remote create;
- credential-wide pauses for authentication failures;
- terminal `needs_review` states for ambiguity or exhausted retries;
- operator-visible incident and attempt history;
- monotonic CRM stage progression, so later lifecycle states are not overwritten by older work.

The repository includes deterministic scenarios for normal intake, duplicate delivery, unavailable AI, CRM rate limiting, and a lost acknowledgement after the CRM has already committed the write.

### An error is evidence—not something to hide

| Failure boundary | Recovery decision |
|---|---|
| CRM returns HTTP 429 | Persist the failure and retry due time; respect `Retry-After` before another eligible attempt |
| A remote write succeeds but its reply is lost | Look up and verify the existing record before considering another create |
| n8n or a worker restarts | Resume from PostgreSQL jobs and bounded leases, not workflow memory |
| Identity is ambiguous or retries are exhausted | Stop in `needs_review` with the original attempt history intact |

<details>
<summary><strong>See the original failed n8n execution: HTTP 429, execution 283</strong></summary>

![Retained controlled HTTP 429 diagnostic failure in n8n](docs/assets/readme/07_controlled_429_failure_execution_283.png)

This is a controlled **local fault-injection diagnostic**, not a real HighLevel outage. The intentionally unsafe diagnostic fails; the durable recovery path subsequently verifies completion. The original failed execution is retained.

</details>

![Durable retry and recovery history](docs/assets/readme/08_durable_recovery_283_to_294.png)

*The same retained job shows attempt 1 failing with HTTP 429 (`Retry-After: 10`, execution 283) and attempt 2 completing (execution 294). This historical screenshot is preserved, not relabelled as part of the new live demo.*

The historical batch recovered **12/12 scoped leads with zero missing and zero duplicate submission IDs**. The [verification report](docs/phase-3-verification.md) also retains later corrections and stronger at-write retry evidence. The [guided demo](docs/guided-demo.md) provides repeatable 429 and lost-acknowledgement scenarios; the [operator runbook](docs/phase-3-runbook.md) explains retry, review, and credential-blocked states.

## AI extraction and evaluation

AI enrichment is advisory. It does not decide customer identity, consent, pricing, technician availability, booking confirmation, or CRM truth. A timeout, provider error, or invalid schema sets `needs_review`; it does not discard an otherwise valid enquiry.

The repository contains a frozen 60-case synthetic evaluation set, a versioned rubric, schema checks, durable request accounting, a request cap, and development/held-out result separation.

During evaluation, the original `openai/gpt-oss-20b` endpoint repeatedly timed out. A separately versioned NVIDIA Nemotron Lightning profile completed all 60 cases:

| Result | Development | Held out | Total |
|---|---:|---:|---:|
| Attempts | 40 | 20 | 60 |
| Schema-valid responses | 37 | 19 | 56 |
| Invalid responses | 2 | 0 | 2 |
| Timeouts | 1 | 1 | 2 |
| All scored fields matched | 9 | 6 | 15 |

The strict score exposes real classification disagreements and conservative exact-match grading. It is evidence from synthetic cases, not a claim of production accuracy. Summaries still require human review. See the [provider recovery report](docs/reviews/provider-recovery.md) and [full evaluation results](docs/reviews/milestone-2a-results-lightning.md).

The evaluated Lightning configuration is available as an opt-in workflow export generator. It has not been silently applied to the canonical workflow or a live deployment.

## Guided local demo

The isolated demo requires Docker with Compose, `curl`, and `openssl`. It uses synthetic records, a local HighLevel contract simulator, Mailpit, and a deterministic AI boundary, so no external credentials are required.

```bash
git clone https://github.com/kabbersokhi-boop/client-lead-intake-booking-recovery-automation.git
cd client-lead-intake-booking-recovery-automation
./scripts/demo up
```

Open **http://localhost:28000/demo.html** and run any of the five scenarios. Each scenario verifies the result against database and simulator evidence.

```bash
./scripts/demo down     # stop the isolated demo and retain its volumes
./scripts/demo reset    # remove only the isolated demo resources
```

The [written demo guide](docs/guided-demo.md) explains the scenarios, expected evidence, reset behavior, and troubleshooting.

## Business reporting

FastAPI produces a minimized 16-field daily aggregate without customer names, contact details, messages, or AI summaries. n8n sends it to Make, which creates or updates the matching Google Sheets row using a deterministic report key. Reporting failures cannot undo intake, booking, or CRM recovery.

The video demonstrates **both branches**: a first run adds the report, then a second run updates the same report key. Readback confirmed one report row, a changed `Generated At` value, and no duplicate row. See the [Make and Sheets evidence](docs/portfolio-demo.md#4-make-and-google-sheets-create-then-update).

![Management dashboard after the recorded Make refresh](docs/assets/portfolio/12-management-dashboard.png)

*The latest recorded report shows one request, one appointment, and one follow-up. The incident total includes retained historical diagnostics; it is not a failure count for this customer journey.*

## Technology

| Layer | Technology |
|---|---|
| Workflow automation | n8n |
| Application API | FastAPI, Python |
| Durable state | PostgreSQL |
| Customer interface | JavaScript, HTML, CSS |
| AI provider | NVIDIA NIM |
| CRM | HighLevel REST API and local contract simulator |
| Email development | Mailpit |
| Reporting | Make.com and Google Sheets |
| Local environment | Docker Compose |
| Verification | Pytest, Node test runner, Playwright, Ruff |

## Verification evidence

The previously verified engineering baseline includes:

- **197** Python/PostgreSQL tests;
- **33** browser and helper tests;
- **48** workflow tests;
- **33** AI evaluation tests;
- lint, JavaScript syntax, JSON, shell, Docker Compose, diff, and tracked-secret checks;
- real Chrome coverage for the five guided demo scenarios from Milestone 1;
- retained evidence from synthetic HighLevel, NVIDIA, Mailpit, Make, and Google Sheets exercises.

The [new recorded demo evidence](docs/portfolio-demo.md#verification-and-boundaries) separately confirms successful intake, booking, reporting, and reporting-refresh executions, verified live CRM stage synchronization, and Sheets readback. Screenshots are full-HD frames from the privacy-reviewed final video; older recovery screenshots remain clearly identified as historical evidence.

The test suites cover validation, database transactions, concurrent workers, lease expiry, retry timing, rate limits, replay conflicts, ambiguous CRM identity, lost acknowledgements, booking conflicts, stage synchronization, reporting minimization, and browser response validation.

```bash
npm ci
npm run test:browser
npm run test:workflow
npm run test:evaluation
node scripts/verify_portfolio.mjs
./scripts/verify_phase3.sh
```

## Repository map

```text
backend/app/                 FastAPI routes, services, models, and providers
backend/migrations/          PostgreSQL schema migrations
backend/simulator/           Local HighLevel contract and fault simulator
backend/tests/               Application and concurrency tests
frontend/                    Customer and operations interfaces
frontend/e2e/                Browser-driven demo verification
n8n/                         Sanitized workflow exports
n8n/evaluation/              Frozen AI datasets, rubrics, and evaluator tests
scripts/                     Demo, verification, diagnostics, and evaluation tools
docs/                        Architecture, runbooks, reports, and retained evidence
docs/assets/video/           Single edited end-to-end portfolio video
docs/assets/portfolio/       Full-HD screenshots and reproducible frame manifest
```

Start with the [architecture notes](docs/architecture.md), [guided demo](docs/guided-demo.md), [recovery runbook](docs/phase-3-runbook.md), and [project handover](handover.md).

## Scope and limitations

- The guided demo uses synthetic data and simulated external faults.
- Mailpit proves local message generation and SMTP acceptance, not production delivery.
- Local appointments do not reserve a technician or an external calendar slot.
- HighLevel integration uses a Private Integration Token; OAuth is outside the current scope.
- Make and Google Sheets are downstream reporting destinations and are not required for lead acceptance.
- AI evaluation uses synthetic, AI-assisted labels and does not establish production accuracy or ROI.
- The alternative Lightning profile still requires an isolated end-to-end acceptance run before activation in a deployed workflow.

## Engineering intent

This repository demonstrates how to build automation around unreliable networks and external APIs without hiding uncertainty. The design records what was intended, what was attempted, what was observed, and what still needs human review. That makes failures inspectable and recovery repeatable while preserving the original customer operation.
