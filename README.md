# End-to-End Lead Intake, CRM Routing, Booking and Failure-Recovery Automation

A fresh technical-interview capability demonstration for an end-to-end enquiry intake flow. All example data is synthetic. This is not a production client deployment and does not use a fictional product or client brand.

> Phase 1 scope: browser intake, n8n validation/normalization, bounded NVIDIA NIM extraction, and persistence through a development CRM adapter. Booking, recovery engineering, Make reporting, and an optional real GoHighLevel sandbox integration are later phases and are not implemented here.

## Architecture

```text
Browser Enquiry Form
        ↓
       n8n
        ↓
Validation / Normalization
        ↓
NVIDIA NIM Enrichment
        ↓
FastAPI CRM Integration Boundary
        ↓
    PostgreSQL
```

- The browser creates a `submission_id`, `correlation_id`, and `received_at` for every enquiry.
- n8n validates customer input before calling NVIDIA NIM, normalizes contact values, validates model output, and explicitly returns 422, 201, or a safe 502 response.
- NVIDIA NIM is used only to extract service context from the original message; it cannot establish availability, bookings, prices, CRM state, or contact details.
- The FastAPI **development CRM adapter** is a small persistence boundary, not GoHighLevel. `DevelopmentCRMProvider` and the future `GoHighLevelCRMProvider` contract keep n8n independent of the eventual CRM vendor.
- PostgreSQL stores leads and safe audit metadata keyed by the correlation ID.

## Run locally

1. Copy `.env.example` to `.env`, using local-only database values. Do not add NVIDIA or n8n secrets to Git.
2. Start PostgreSQL and the FastAPI service:

   ```bash
   docker compose up --build
   ```

   The backend runs migrations before starting and serves the form at [http://localhost:18000](http://localhost:18000). Health is available at [http://localhost:18000/health](http://localhost:18000/health).

3. Configure the existing n8n instance with environment variables, then restart that instance:

   ```text
   NVIDIA_NIM_API_KEY=<your key>
   NVIDIA_NIM_MODEL=<enabled NVIDIA model ID>
   CRM_ADAPTER_URL=http://host.docker.internal:18000
   ```

   On Linux Docker, add `host.docker.internal:host-gateway` to the existing n8n container's `extra_hosts`, then restart it. This container currently does not resolve that hostname. The workflow returns the required CORS response headers for `http://localhost:18000`; the browser deliberately uses a simple `text/plain` JSON request to avoid a preflight request.

4. Import `n8n/lead-intake.json` in n8n, activate it, and use the production webhook URL shown by n8n. Put that URL in `N8N_WEBHOOK_URL` before starting the backend. The export has no credentials or credential references: NVIDIA uses the n8n environment variable directly.

5. Submit the form with fictional data. Query the resulting records:

   ```bash
   curl http://localhost:18000/api/traces/<correlation-id>
   ```

   The page also includes a **Trace a persisted enquiry** panel. It displays the stored lead and safe audit events through this read-only endpoint; it is a verification view for the development CRM adapter, not a GoHighLevel UI.

## Development and automated checks

```bash
cd backend
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
pytest -q
ruff check app tests
```

Tests use SQLite and mocked/persisted fallback inputs only; they never call NVIDIA NIM or n8n. Public GitHub Actions runs the same lint and test commands without secrets.

## Live verification

Use the checklist in [docs/phase-1-verification.md](docs/phase-1-verification.md). A live NVIDIA NIM call and a live n8n execution must be recorded there only after they actually succeed. This repository does not claim that they have run merely because the workflow definition exists.

## Security

- `.env` is ignored and `.env.example` contains placeholders only.
- The n8n export is sanitized: it contains no keys, credential IDs, account identifiers, or private endpoints.
- Audit metadata intentionally stores only trace and operational state; it never stores secrets.
