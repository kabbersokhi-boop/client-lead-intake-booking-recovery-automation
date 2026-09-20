# End-to-End Lead Intake, CRM Routing, Booking and Failure-Recovery Automation

A fresh technical-interview capability demonstration for an end-to-end enquiry and booking lifecycle. All example data is synthetic. This is not a production client deployment and does not use a fictional product or client brand.

> Current scope: Phase 1 intake, Phase 2 lifecycle/booking, and Phase 3 bounded CRM-write recovery. Make, WhatsApp, real calendar/email providers, and a vendor CRM integration are not implemented. The CRM boundary remains an explicit development adapter.

## Architecture

```text
Browser Enquiry Form
        ↓
  n8n Intake Workflow
        ↓
Validation / Normalization
        ↓
NVIDIA NIM Enrichment
        ↓
FastAPI CRM Integration Boundary
        ↓
PostgreSQL Durable CRM Job + Lead + Pending Follow-up
        ↓
 n8n Follow-up or Booking Workflow
        ↓
 Development Email → Mailpit
```

- The browser creates a `submission_id`, `correlation_id`, and `received_at` for a pending enquiry. An unchanged retry reuses those values; editing the enquiry deliberately creates a new identity.
- n8n validates customer input before calling NVIDIA NIM, preserves the source message separately from normalized processing text, validates model output, and explicitly returns 422, 201/200, or a safe 502 response.
- NVIDIA NIM is used only to extract service context from the original message; it cannot establish availability, bookings, prices, CRM state, or contact details.
- The FastAPI **development CRM adapter** is a small persistence boundary, not GoHighLevel. `DevelopmentCRMProvider` and the future `GoHighLevelCRMProvider` contract keep n8n independent of the eventual CRM vendor.
- PostgreSQL stores leads, follow-ups, appointments, source and persistence timestamps, and safe audit metadata keyed by correlation ID. Email-capable leads receive one configurable pending follow-up; phone-only leads do not schedule unsupported email work.
- Every validated lead write is persisted before delivery. The first stored prepared payload remains canonical for creation even if a repeated intake has a different valid AI outcome; persisted CRM state remains canonical for replay. Confirmed writes remain `201`/`200`; unfinished durable work returns `202 queued` without a fabricated CRM ID or booking access.
- Recovery claims one due job with a lease, reconciles by stable submission identity, obtains shared quota permission, and then completes, retries, blocks, or holds the job for review. Four total automatic writes are allowed by default; manual requeue authorizes one additional operator attempt without deleting history.
- The booking operation atomically creates one active appointment per lead, moves the pipeline to `appointment_booked`, and cancels a still-pending follow-up. A repeated `booking_request_id` returns the same appointment; a different booking for that lead returns a controlled conflict.
- Mailpit is a local development SMTP sink, not a real customer email provider. The actual path is n8n HTTP orchestration → FastAPI development email gateway → SMTP → Mailpit; the public workflows do not use a native n8n SMTP node. Follow-up and booking messages are multipart text/HTML, escape stored values, show only persisted optional details, and carry an explicit development notice.

## Run locally

1. Copy `.env.example` to `.env`, using local-only database values. Generate a long random `CRM_ADAPTER_API_KEY`; do not add it, NVIDIA keys, or n8n secrets to Git.
2. Start PostgreSQL, the FastAPI service, and Mailpit:

   ```bash
   docker compose up --build
   ```

   The backend runs migrations before starting and serves the form at [http://localhost:18000](http://localhost:18000). Mailpit is available at [http://localhost:18025](http://localhost:18025). Both web interfaces are loopback-bound; PostgreSQL and SMTP have no host port.

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

4. Import and activate the sanitized workflows:

   - `n8n/lead-intake.json`
   - `n8n/appointment-booking.json`
   - `n8n/follow-up-dispatch.json`
   - `n8n/crm-recovery-error.json`
   - `n8n/crm-write-recovery.json`

   Keep `n8n/crm-write-diagnostic.json` disabled except during the controlled local fault test. Diagnostic and recovery use `phase3-crm-recovery-error` as their error workflow; exports contain this stable local link and no credentials.

   Put the two production webhook URLs in `N8N_WEBHOOK_URL` and `N8N_BOOKING_WEBHOOK_URL`. The workflow exports contain no secrets or credential references. The dispatcher checks every minute; `FOLLOW_UP_DELAY_SECONDS` defaults to a deliberately short 120 seconds so the local demonstration is repeatable. This is a demo delay, not a production contact-time claim.

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

The current Phase 3 verifier discovers 89 backend/Python/PostgreSQL tests, 13 browser-helper tests, and 36 workflow-code/structure tests. Live n8n, NVIDIA, and Mailpit checks remain separate and are documented rather than silently mocked.

## Live verification

See [docs/phase-1-verification.md](docs/phase-1-verification.md) for the approved intake baseline and [docs/phase-2-verification.md](docs/phase-2-verification.md) for both executed lifecycle paths. Real n8n executions have verified both safe fallback-to-persistence and successful live NVIDIA enrichment; see the sanitized [provider diagnostic record](docs/provider-diagnostics.md).

Phase 3 evidence and operations are in [docs/phase-3-verification.md](docs/phase-3-verification.md), [docs/phase-3-failed-run-postmortem.md](docs/phase-3-failed-run-postmortem.md), [docs/phase-3-runbook.md](docs/phase-3-runbook.md), and [docs/phase-3-self-review.md](docs/phase-3-self-review.md). Run `scripts/verify_phase3.sh` for deterministic verification and `scripts/phase3_demo.py --help` for authenticated local demo controls.

## Security

- `.env` is ignored and `.env.example` contains placeholders only.
- The n8n export is sanitized: it contains no keys, credential IDs, account identifiers, or private endpoints.
- The browser temporarily uses `sessionStorage` only for an ambiguous pending submission so it can retry with the same identity; it clears that data only after verified success. It stores no secrets.
- Read endpoints are verification-only and Compose keeps them loopback-only. CORS is not used as authentication; the n8n-to-CRM write route uses the shared adapter credential.
- Audit metadata intentionally stores only trace and operational state; it never stores secrets.
- Mailpit data is ephemeral local runtime state and is not committed.
- Lifecycle row locks prevent ordinary concurrent duplicate sends, but SMTP acceptance and the subsequent PostgreSQL commit are separate effects. A crash or lost acknowledgement between them is not an exactly-once guarantee; uncertain-delivery recovery remains outside Phase 2.
- Phase 3 recovery covers CRM lead writes only. It does not automatically replay uncertain SMTP sends, booking confirmations, appointments, or follow-up email effects.
- Appointments demonstrate durable booking state and timezone handling only. They are not backed by live service capacity or an external calendar.
