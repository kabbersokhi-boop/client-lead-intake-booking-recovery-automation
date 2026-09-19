# Phase 1 verification evidence

All data below is synthetic. This document distinguishes checks that ran from
checks that remain blocked; it does not treat a workflow export as execution evidence.

## Executed on 2026-09-19

| Check | Result | Evidence |
| --- | --- | --- |
| Backend migration and health | Passed | Compose applied `20260919_02`; `GET /health` returned `200`. |
| Backend lint and HTTP contract tests | Passed | `ruff check app tests`; 22 SQLite-backed tests passed. |
| PostgreSQL migration and concurrency test | Passed | 23 tests passed with a disposable PostgreSQL 16 container. |
| Browser retry and workflow code fixtures | Passed | 3 browser-helper and 6 exported-workflow JavaScript tests passed under Node 22. |
| Deployed workflow/export comparison | Passed | Workflow `GKMASmZ5xo0UaWUY` was updated locally; its validation, normalization, AI parsing, CRM request, and result-building logic matched `n8n/lead-intake.json` after export. |
| Real n8n webhook through CRM persistence | Passed with NVIDIA fallback | Execution `143` returned HTTP `201`; correlation `134d9b3a-2454-4769-bf25-fd62c536c743`; CRM lead `aacb40ff-ae90-43c4-a0e2-1d6dd6fe54d5`; `ai_status=fallback_unavailable`; one `crm.lead_created` audit event. |

The execution's persisted provider metadata was `provider=nvidia_nim`,
`outcome_class=provider_error`, `error_code=ERR_BAD_REQUEST`, and execution
reference `143`. It did **not** prove NVIDIA inference authorization: the
rotated credential has not yet been supplied and the selected model was unset.

## Not executed / blocked

| Check | Status | Required next action |
| --- | --- | --- |
| Browser GUI submission | Not executed | This environment has no installed browser automation binary. Open `http://localhost:18000`, submit the synthetic Maya Verma enquiry, and confirm the returned correlation ID in n8n and `/api/traces/<id>`. |
| Direct NVIDIA chat-completions verification after rotation | Blocked | Revoke the exposed NVIDIA key, place a replacement only in the secure local n8n/runtime secret channel, select one currently enabled model, then run one minimal synthetic direct request before updating the workflow environment. See `docs/provider-diagnostics.md`. |
| Live enriched end-to-end path | Blocked by the same credential/model authorization action | Re-run the browser flow after the direct request succeeds; the persisted lead must have `ai_status=enriched` and schema-valid enrichment. |

## Repeatable commands

```bash
docker compose up --build -d
curl http://localhost:18000/health

cd backend
../.venv/bin/ruff check app tests
../.venv/bin/python -m pytest -q

cd ..
npm run test:browser
npm run test:workflow
```

For PostgreSQL-specific tests, set `TEST_POSTGRES_URL` to a disposable
PostgreSQL database before running pytest. Public CI provisions that database;
it does not call n8n or NVIDIA.
