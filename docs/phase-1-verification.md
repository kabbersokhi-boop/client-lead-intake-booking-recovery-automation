# Phase 1 verification runbook

This runbook is deliberately evidence-oriented. Do not mark a live step complete until it has happened.

## Automated

```bash
cd backend
pytest -q
ruff check app tests
```

Expected coverage includes valid input, missing name/contact data, malformed email, normalization, CRM persistence, audit creation, fallback-invalid, fallback-unavailable, and correlation ID persistence.

## Local services

1. Run `docker compose up --build`.
2. Confirm `GET http://localhost:18000/health` returns `{"status":"ok"}`.
3. Confirm startup logs include the Alembic upgrade.

## Live NVIDIA NIM

From the configured n8n workflow, use the supplied synthetic furnace enquiry. Open the execution data for **Extract Service Context with NVIDIA NIM** and **Validate AI Extraction**. Record the execution URL/ID privately; do not commit private n8n URLs or raw request headers. Confirm the final CRM lead has `ai_status=enriched` and a schema-valid enrichment object.

## Live end-to-end

1. Open `http://localhost:18000`.
2. Enter the fictional Maya Verma enquiry and submit.
3. Confirm a 201 browser state with its correlation ID.
4. In the actual n8n instance, confirm one successful execution follows all named nodes.
5. Query `GET /api/leads?correlation_id=<id>` and verify the original customer message, identifiers, enrichment, and `new_lead` stage.
6. Query `GET /api/audit-events?correlation_id=<id>` and verify `crm.lead_created`.

Record the final synthetic correlation ID in the final phase report, not in the repository. Never place a credential, token, or private n8n execution URL in this document.
