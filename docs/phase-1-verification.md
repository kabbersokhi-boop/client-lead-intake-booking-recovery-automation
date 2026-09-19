# Phase 1 verification evidence

All data below is synthetic. This document distinguishes checks that ran from
checks that remain blocked; it does not treat a workflow export as execution evidence.

## Executed on 2026-09-19

| Check | Result | Evidence |
| --- | --- | --- |
| Backend migration and health | Passed | Compose applied `20260919_02`; `GET /health` returned `200`. |
| Backend lint and HTTP contract tests | Passed | `ruff check app tests`; 23 tests passed, including PostgreSQL migration and concurrent replay coverage. |
| PostgreSQL migration and concurrency test | Passed | 23 tests passed with a disposable PostgreSQL 16 container. |
| Browser retry, verified-result, trace-view, and workflow code fixtures | Passed | 4 browser-helper and 6 exported-workflow JavaScript tests passed under Node 22. |
| Deployed workflow/export comparison | Passed | Workflow `GKMASmZ5xo0UaWUY` was updated locally; its validation, normalization, AI parsing, CRM request, and result-building logic matched `n8n/lead-intake.json` after export. |
| Real n8n webhook through CRM persistence | Passed with NVIDIA fallback | Execution `143` returned HTTP `201`; correlation `134d9b3a-2454-4769-bf25-fd62c536c743`; CRM lead `aacb40ff-ae90-43c4-a0e2-1d6dd6fe54d5`; `ai_status=fallback_unavailable`; one `crm.lead_created` audit event. |
| Direct NVIDIA chat-completions request | Passed | One synthetic request using `openai/gpt-oss-20b` returned HTTP `200` and a non-empty chat response. The request used only `model`, `temperature`, and `messages`. |
| Real enriched n8n path | Passed | Execution `145` returned HTTP `201`; correlation `76f64b8c-05a6-4df3-bfac-bda5e8707745`; CRM lead `92ee5412-be41-4b2a-abbe-98fca7388407`; `ai_status=enriched`; schema-valid service context; one `crm.lead_created` audit event. |

The enriched execution persisted `provider=nvidia_nim`,
`model_id=openai/gpt-oss-20b`, `outcome_class=enriched`, `status_code=200`, and
execution reference `145`. Its persisted fields were `furnace_service`,
`Surrey`, `Tuesday afternoon`, and `medium`; its summary was present and within
the application schema bound. The earlier fallback execution remains retained
as evidence that AI is not a single point of failure.

## Not executed / blocked

| Check | Status | Required next action |
| --- | --- | --- |
| Browser GUI submission | Not executed | This environment has no installed browser automation binary. The webhook response contract was verified by the live synthetic POST above and by browser-helper tests. Open `http://localhost:18000`, submit the synthetic Maya Verma enquiry, and inspect the returned trace for a manual visual check. |

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
