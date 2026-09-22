# End-to-End HVAC Service Request, Booking and Failure-Recovery Automation

A fresh technical-interview capability demonstration for an end-to-end enquiry and booking lifecycle. All example data is synthetic. This is not a production client deployment and does not use a fictional product or client brand.

> Current scope: Phases 1–6 and Phase 7A are complete for the documented reference-demo boundary. The HighLevel Contact/Opportunity projection has been verified against a real HighLevel sub-account using synthetic data, including a website/n8n/FastAPI/PostgreSQL/live-HighLevel intake and exact replay. The committed `.env.example` keeps the safe `development` default; this local interview/demo runtime uses ignored, protected `.env` with `CRM_PROVIDER_MODE=highlevel_live`. PostgreSQL remains application and reliability truth.

## Architecture

```text
Website HVAC Service Request
        ↓
  n8n Intake Workflow
        ↓
Validation / Normalization / optional NVIDIA NIM enrichment
        ↓
FastAPI durable intake/recovery boundary
        ├── PostgreSQL application/reliability truth
        │     (Lead, CRM write job, attempt, follow-up, audit state)
        ├── HighLevel adapter → REAL HighLevel sub-account
        │                         → Contact + Opportunity
        │                         → HVAC Service Pipeline / New Lead
        └── Local lifecycle/email demo paths → Mailpit

HighLevel Contract Simulator
        → deterministic local fault/recovery infrastructure
        → 401 / 429 / 500 / timeout / uncertain-write testing
```

- The browser creates a `submission_id`, `correlation_id`, and `received_at` for a pending enquiry. An unchanged retry reuses those values; editing the enquiry deliberately creates a new identity.
- n8n validates customer input before calling NVIDIA NIM, preserves the source message separately from normalized processing text, validates model output, and explicitly returns 422, 201/200, or a safe 502 response.
- NVIDIA NIM is used only to extract service context from the original message; it cannot establish availability, bookings, prices, CRM state, or contact details.
- `development` remains the safe default runtime mode. In `highlevel_live` mode, the HighLevel-specific adapter projects the durable intake to the verified real sub-account Contact and Opportunity in `HVAC Service Pipeline / New Lead`; PostgreSQL remains reliability/audit truth.
- This workstation’s ignored `.env` persistently selects `highlevel_live`, so normal website intake projects to the real HighLevel sub-account after durable PostgreSQL intake. A normal Compose build, restart, or backend recreation reads the same protected configuration. The simulator remains the deterministic fault laboratory.
- The loopback-only simulator at `http://localhost:18080` remains separate deterministic test infrastructure. It implements the documented contact/opportunity subset, validates auth/version/request shapes, shows sanitized API events, and provides one-shot 401/429/500/timeout and uncertain-write testing. It is not a HighLevel sandbox or a substitute for the separate live-vendor evidence.
- PostgreSQL stores leads, follow-ups, appointments, source and persistence timestamps, and safe audit metadata keyed by correlation ID. Email-capable leads receive one configurable pending follow-up; phone-only leads do not schedule unsupported email work.
- Every validated lead write is persisted before delivery. The first stored prepared payload remains canonical for creation even if a repeated intake has a different valid AI outcome; persisted CRM state remains canonical for replay. Confirmed writes remain `201`/`200`; unfinished durable work returns `202 queued` without a fabricated CRM ID or booking access.
- Recovery claims one due job with a lease, reconciles by stable submission identity, obtains shared quota permission, and then completes, retries, blocks, or holds the job for review. Four total automatic writes are allowed by default; manual requeue authorizes one additional operator attempt without deleting history.
- The booking operation atomically creates one active local appointment per lead, moves the local pipeline state to `appointment_booked`, and cancels a still-pending follow-up. Automatic HighLevel `Contacted` / `Appointment Booked` stage synchronization and live appointment/calendar synchronization are not implemented. A repeated `booking_request_id` returns the same appointment; a different booking for that lead returns a controlled conflict.
- Mailpit is a local development SMTP sink, not a real customer email provider. The actual path is n8n HTTP orchestration → FastAPI development email gateway → SMTP → Mailpit; the public workflows do not use a native n8n SMTP node. Follow-up and booking messages are multipart text/HTML, escape stored values, show only persisted optional details, and carry an explicit development notice.
- The separate manual Phase 5 workflow reads an authenticated aggregate-only FastAPI projection and sends it to Make from protected n8n runtime configuration. Live executions verified first-row creation and a corrected same-key update without duplication; an isolated failed reporting execution left customer-critical durable counts unchanged. The workflow remains inactive/manual.

## Run locally

1. For a new checkout, copy `.env.example` to `.env` and use local-only database values. Generate long, separate random values for `CRM_ADAPTER_API_KEY` and `HIGHLEVEL_SIMULATOR_TOKEN`; do not add them, NVIDIA keys, or n8n secrets to Git. The example keeps `CRM_PROVIDER_MODE=development` as its safe default. This interview/demo checkout’s ignored `.env` is already protected and configured for `highlevel_live`; do not replace it with the example file.
2. Start PostgreSQL, the FastAPI service, and Mailpit:

   ```bash
   docker compose up --build
   ```

   The backend runs migrations before starting and serves the form at [http://localhost:18000](http://localhost:18000). Mailpit is available at [http://localhost:18025](http://localhost:18025), and the local contract simulator at [http://localhost:18080](http://localhost:18080). All browser surfaces are loopback-bound; PostgreSQL and SMTP have no host port.

3. Configure the existing n8n instance with protected runtime values, then restart it:

   ```text
   NVIDIA_NIM_API_KEY=<rotated key in protected runtime storage>
   NVIDIA_NIM_MODEL=<one currently enabled NVIDIA model ID>
   NVIDIA_NIM_TIMEOUT_MS=18000
   CRM_ADAPTER_API_KEY=<same locally generated adapter key>
   CRM_ADAPTER_TIMEOUT_MS=6000
   CRM_CONTROL_TIMEOUT_MS=3000
   CRM_ADAPTER_URL=http://backend:8000
   ```

   When n8n is a separate Docker container, attach it to the Compose network and use `http://backend:8000`; this preserves private container-to-container access while both editor and browser-facing backend stay loopback-bound. The CRM write endpoint requires `X-CRM-Adapter-Key`; the workflow supplies it from n8n runtime configuration. The workflow returns CORS headers for `http://localhost:18000` and the browser uses JSON requests with a 30-second configurable acknowledgement timeout.

4. Import the sanitized workflows. Preserve their IDs and names because retained execution evidence
   depends on them. Their interview grouping is:

   **Customer journey**

   - `Lead Intake - Validation, AI Enrichment and CRM Persistence` (`n8n/lead-intake.json`)
   - `Lifecycle - Appointment Booking and Confirmation` (`n8n/appointment-booking.json`)
   - `Lifecycle - Dispatch Due Follow-ups` (`n8n/follow-up-dispatch.json`)

   **Reliability / debugging**

   - `CRM Lead Write Recovery Dispatch` (`n8n/crm-write-recovery.json`)
   - `CRM Recovery Failure Recorder` (`n8n/crm-recovery-error.json`)
   - `Controlled CRM Rate-Limit Diagnostic` (`n8n/crm-write-diagnostic.json`, inactive)

   **Management reporting**

   - `Management Reporting - HVAC Snapshot` (`n8n/management-reporting.json`, manual/inactive)

   Keep `n8n/crm-write-diagnostic.json` disabled except during the controlled local fault test. Diagnostic and recovery use `phase3-crm-recovery-error` as their error workflow; exports contain this stable local link and no credentials.

   Put the two customer-journey webhook URLs in `N8N_WEBHOOK_URL` and `N8N_BOOKING_WEBHOOK_URL`. The workflow exports contain no secrets or credential references. The dispatcher checks every minute; `FOLLOW_UP_DELAY_SECONDS` defaults to a deliberately short 120 seconds so the local demonstration is repeatable. This is a demo delay, not a production contact-time claim.

5. Submit the form with fictional data, then book from the verified result or let the follow-up become due. Query the complete lifecycle trace:

   ```bash
   curl http://localhost:18000/api/traces/<correlation-id>
   ```

   The page displays pipeline, AI, follow-up, appointment, confirmation, and audit state. Booking input is explicitly interpreted in `America/Vancouver`; PostgreSQL stores the canonical appointment instant. Read-only trace endpoints are local-development verification surfaces, not a production CRM UI.

## Development and automated checks

```bash
cd backend
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
pytest -q
ruff check app tests
```

Tests use SQLite for fast API/schema tests and disposable PostgreSQL for migration, persistence, and concurrent replay coverage. Node tests execute the exported n8n code-node logic with deterministic fixtures and browser retry helpers. They never call NVIDIA NIM or n8n. Public GitHub Actions provisions PostgreSQL and runs all deterministic tests without secrets.

Exact-SHA [Backend CI run 35759169287](https://github.com/kabbersokhi-boop/client-lead-intake-booking-recovery-automation/actions/runs/35759169287) passed 165 Python tests, 32 browser/helper tests, and 43 workflow tests: 240 passing checks total. This differs from the focused local Phase 6 verification invocation, which recorded 154 Python passes with 11 skips and ran 3 browser test files plus 4 workflow test files; file counts are not test counts. Live n8n, NVIDIA, Mailpit, Make, and simulator checks remain separately identified evidence rather than silently mocked.

## Live verification

See [docs/phase-1-verification.md](docs/phase-1-verification.md) for the approved intake baseline and [docs/phase-2-verification.md](docs/phase-2-verification.md) for both executed lifecycle paths. Real n8n executions have verified both safe fallback-to-persistence and successful live NVIDIA enrichment; see the sanitized [provider diagnostic record](docs/provider-diagnostics.md).

Phase 3 evidence and operations are in [docs/phase-3-verification.md](docs/phase-3-verification.md), [docs/phase-3-failed-run-postmortem.md](docs/phase-3-failed-run-postmortem.md), [docs/phase-3-runbook.md](docs/phase-3-runbook.md), and [docs/phase-3-self-review.md](docs/phase-3-self-review.md). Run `scripts/verify_phase3.sh` for deterministic verification and `scripts/phase3_demo.py --help` for authenticated local demo controls.

Open [http://localhost:18000/operations.html](http://localhost:18000/operations.html) for the local, synthetic, read-only operations view. Refresh job-state counts, filter or paste an exact job/submission/correlation UUID, select a job, inspect persisted attempts and incidents, then follow its correlation trace or safely constructed local n8n execution link. The page never sends the adapter key to the browser and cannot claim, retry, requeue, resolve, send, or mutate records. Phase 4 verification and self-review are in [docs/phase-4-verification.md](docs/phase-4-verification.md) and [docs/phase-4-self-review.md](docs/phase-4-self-review.md).

Phase 5 reporting semantics, live Make/Google Sheets evidence, failure isolation, and limitations are recorded in [docs/phase-5-verification.md](docs/phase-5-verification.md) and [docs/phase-5-self-review.md](docs/phase-5-self-review.md). Do not configure the private Make webhook in source-controlled files.

Phase 6 simulator semantics and local fault evidence are recorded in [docs/phase-6-verification.md](docs/phase-6-verification.md) and [docs/phase-6-self-review.md](docs/phase-6-self-review.md). The authoritative real-vendor record is [docs/phase-6-live-highlevel-verification.md](docs/phase-6-live-highlevel-verification.md). Appointment/calendar and automatic lifecycle-stage synchronization remain deliberately omitted rather than inserted unsafely into the approved booking transaction.

For an interview-ready, browser-first local walkthrough, see [docs/interview-demo-runbook.md](docs/interview-demo-runbook.md). It preserves the retained failure and reporting stories without asking the presenter to recreate faults.

The final system-wide review before Phase 7B is recorded in [docs/pre-7b-readiness-review.md](docs/pre-7b-readiness-review.md). Phase 7B remains presentation packaging: manager-facing Sheets polish, the final visual case study, screenshots/redaction, rehearsal, interview Q&A, and the final PDF.

## Security

- `.env` is ignored and `.env.example` contains placeholders only.
- The n8n export is sanitized: it contains no keys, credential IDs, account identifiers, or private endpoints.
- The browser temporarily uses `sessionStorage` only for an ambiguous pending submission so it can retry with the same identity; it clears that data only after verified success. It stores no secrets.
- Read endpoints are verification-only and Compose keeps them loopback-only. CORS is not used as authentication; the n8n-to-CRM write route uses the shared adapter credential.
- `/operations.html` uses narrow same-origin browser-safe read projections only. Its local n8n execution links require a numeric reference and configured loopback editor base; arbitrary stored values remain copyable text.
- `/api/reporting/management-summary` is an adapter-key-protected aggregate-only GET for n8n. It excludes customer PII and recovery internals, and it never calls Make or another external service.
- Audit metadata intentionally stores only trace and operational state; it never stores secrets.
- Mailpit data is ephemeral local runtime state and is not committed.
- Lifecycle row locks prevent ordinary concurrent duplicate sends, but SMTP acceptance and the subsequent PostgreSQL commit are separate effects. A crash or lost acknowledgement between them is not an exactly-once guarantee; uncertain-delivery recovery remains outside Phase 2.
- Phase 3 recovery covers CRM lead writes only. It does not automatically replay uncertain SMTP sends, booking confirmations, appointments, or follow-up email effects.
- Appointments demonstrate durable booking state and timezone handling only. They are not backed by live service capacity or an external calendar.
