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

- The browser creates a `submission_id`, `correlation_id`, and `received_at` for a pending enquiry. An unchanged retry reuses those values; editing the enquiry deliberately creates a new identity.
- n8n validates customer input before calling NVIDIA NIM, preserves the source message separately from normalized processing text, validates model output, and explicitly returns 422, 201/200, or a safe 502 response.
- NVIDIA NIM is used only to extract service context from the original message; it cannot establish availability, bookings, prices, CRM state, or contact details.
- The FastAPI **development CRM adapter** is a small persistence boundary, not GoHighLevel. `DevelopmentCRMProvider` and the future `GoHighLevelCRMProvider` contract keep n8n independent of the eventual CRM vendor.
- PostgreSQL stores leads, the client-provided source timestamp, a server persistence timestamp, and safe audit metadata keyed by the correlation ID. Phone shape checks require formatting-compatible text with at least seven digits; they do not prove that a number is reachable.

## Run locally

1. Copy `.env.example` to `.env`, using local-only database values. Generate a long random `CRM_ADAPTER_API_KEY`; do not add it, NVIDIA keys, or n8n secrets to Git.
2. Start PostgreSQL and the FastAPI service:

   ```bash
   docker compose up --build
   ```

   The backend runs migrations before starting and serves the form at [http://localhost:18000](http://localhost:18000). Health is available at [http://localhost:18000/health](http://localhost:18000/health). Compose publishes this service only to `127.0.0.1`; PostgreSQL has no host port.

3. Configure the existing n8n instance with protected runtime values, then restart it:

   ```text
   NVIDIA_NIM_API_KEY=<rotated key in protected runtime storage>
   NVIDIA_NIM_MODEL=<one currently enabled NVIDIA model ID>
   NVIDIA_NIM_TIMEOUT_MS=10000
   CRM_ADAPTER_API_KEY=<same locally generated adapter key>
   CRM_ADAPTER_TIMEOUT_MS=8000
   CRM_ADAPTER_URL=http://backend:8000
   ```

   When n8n is a separate Docker container, attach it to the Compose network and use `http://backend:8000`; this preserves private container-to-container access while both editor and browser-facing backend stay loopback-bound. The CRM write endpoint requires `X-CRM-Adapter-Key`; the workflow supplies it from n8n runtime configuration. The workflow returns CORS headers for `http://localhost:18000` and the browser uses JSON requests with a 15-second configurable acknowledgement timeout.

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

Tests use SQLite for fast API/schema tests and disposable PostgreSQL for migration, persistence, and concurrent replay coverage. Node tests execute the exported n8n code-node logic with deterministic fixtures and browser retry helpers. They never call NVIDIA NIM or n8n. Public GitHub Actions provisions PostgreSQL and runs all deterministic tests without secrets.

## Live verification

See [docs/phase-1-verification.md](docs/phase-1-verification.md) for executed evidence and unexecuted checks. A real n8n webhook execution has verified the safe fallback-to-persistence path. A successful live NVIDIA enrichment is **not** claimed; see the sanitized [provider diagnostic record](docs/provider-diagnostics.md).

## Security

- `.env` is ignored and `.env.example` contains placeholders only.
- The n8n export is sanitized: it contains no keys, credential IDs, account identifiers, or private endpoints.
- The browser temporarily uses `sessionStorage` only for an ambiguous pending submission so it can retry with the same identity; it clears that data only after verified success. It stores no secrets.
- Read endpoints are verification-only and Compose keeps them loopback-only. CORS is not used as authentication; the n8n-to-CRM write route uses the shared adapter credential.
- Audit metadata intentionally stores only trace and operational state; it never stores secrets.
