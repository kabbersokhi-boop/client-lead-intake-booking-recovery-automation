# Phase 1 verification evidence

All data below is synthetic. This document distinguishes checks that ran from
checks that remain blocked; it does not treat a workflow export as execution evidence.

## Executed on 2026-09-19

| Check | Result | Evidence |
| --- | --- | --- |
| Backend migration and health | Passed | Compose applied `20260919_02`; `GET /health` returned `200`. |
| Backend lint and HTTP contract tests | Passed | `ruff check app tests`; 23 tests passed, including PostgreSQL migration and concurrent replay coverage. |
| PostgreSQL migration and concurrency test | Passed | 23 tests passed with a disposable PostgreSQL 16 container. |
| Browser retry, verified-result, trace-view, and workflow code fixtures | Passed | 6 browser-helper and 6 exported-workflow JavaScript tests passed under Node 22. |
| Deployed workflow/export comparison | Passed | Workflow `GKMASmZ5xo0UaWUY` was updated locally; its validation, normalization, AI parsing, CRM request, and result-building logic matched `n8n/lead-intake.json` after export. |
| Real n8n webhook through CRM persistence | Passed with NVIDIA fallback | Execution `143` returned HTTP `201`; correlation `134d9b3a-2454-4769-bf25-fd62c536c743`; CRM lead `aacb40ff-ae90-43c4-a0e2-1d6dd6fe54d5`; `ai_status=fallback_unavailable`; one `crm.lead_created` audit event. |
| Direct NVIDIA chat-completions request | Passed | One synthetic request using `openai/gpt-oss-20b` returned HTTP `200` and a non-empty chat response. The request used only `model`, `temperature`, and `messages`. |
| Real enriched n8n path | Passed | Execution `145` returned HTTP `201`; correlation `76f64b8c-05a6-4df3-bfac-bda5e8707745`; CRM lead `92ee5412-be41-4b2a-abbe-98fca7388407`; `ai_status=enriched`; schema-valid service context; one `crm.lead_created` audit event. |
| Manual browser submission | Passed operationally with AI fallback | Execution `146` persisted the submitted synthetic lead and returned an accepted intake result with `ai_status=fallback_unavailable`. It remains retained as evidence that intake persistence does not depend on AI availability. |
| Timeout correction and browser-equivalent webhook retry | Passed | Execution `149` returned HTTP `201`; correlation `f3dd6910-0aa8-4bfa-b281-46752617014f`; CRM lead `5c59bd59-1e12-41b4-a09e-dc40148649f8`; `ai_status=enriched`; `furnace_service`, `Surrey`, `Tuesday afternoon`, and schema-valid `medium` urgency persisted with `needs_review=false` and one `crm.lead_created` audit event. |

The enriched executions persisted `provider=nvidia_nim`,
`model_id=openai/gpt-oss-20b`, `outcome_class=enriched`, `status_code=200`, and
execution references `145` and `149`. The `149` persisted fields were `furnace_service`,
`Surrey`, `Tuesday afternoon`, and `medium`; its summary was present and within
the application schema bound. The earlier fallback execution remains retained
as evidence that AI is not a single point of failure.

## Timeout evidence and revised budgets

Execution `146` started at `2026-09-19T18:32:42.674Z` and stopped at
`2026-09-19T18:32:52.771Z`: an elapsed `10.097` seconds. Its NVIDIA node
recorded `ECONNABORTED`. At that time, the n8n runtime had no
`NVIDIA_NIM_TIMEOUT_MS` value, so the workflow's configured default of
`10,000` ms applied. This confirms a configured request timeout rather than
an assumed provider-entitlement failure.

During the correction, three minimal synthetic NVIDIA extraction requests
using the same model completed in approximately `1.71`, `5.23`, and `12.35`
seconds. A request with the now-deployed `max_tokens=180` bound also returned
HTTP `200` with valid structured output in approximately `14.94` seconds.

The deployed budgets are NVIDIA `18,000` ms, CRM `6,000` ms, and browser/n8n
acknowledgement `30,000` ms. The combined downstream caps leave six seconds
for workflow and network overhead; a timeout still enters the safe fallback
path. The bounded output limit prevents the extraction response from growing
without limit.

## NVIDIA structured-output reliability correction

HTTP `200` did not guarantee usable model output. A recent baseline request
using `openai/gpt-oss-20b`, `temperature=0`, and `max_tokens=180` ended with
`finish_reason=length` and unusable/empty `message.content`. Adding JSON mode
alone (`response_format: { type: "json_object" }`) was accepted by the
endpoint but still truncated. During diagnosis, combining JSON mode with
`reasoning_effort: "low"` returned HTTP `200` in about `10.3` seconds and
produced output that passed the exact five-field application schema.

The tracked intake request now includes those two NVIDIA request fields. The
model, temperature, output limit, and NVIDIA timeout remain unchanged; the
timeout is still `18,000` ms. The strict application validator remains
mandatory: malformed JSON, missing or extra keys, unsupported enum values, and
invalid field types enter the existing safe fallback. AI enrichment remains
optional, and lead persistence continues through `fallback_invalid` or
`fallback_unavailable` if NVIDIA output is unusable or the provider fails.

| Check | Status | Evidence |
| --- | --- | --- |
| Fresh synthetic n8n intake after structured-output correction | Passed | Execution `3642` returned HTTP `201`; correlation `d31a50f6-04bb-4e1e-b961-a578bcb88c82`; `ai_status=enriched`; persisted `furnace_service`, `Surrey`, `Tuesday afternoon`, `medium`, and `Furnace not heating`; one `crm.lead_created` audit event. The active runtime CRM provider was `development`; the phone-only lead scheduled no email follow-up. |

## Remaining manual check

| Check | Status | Required next action |
| --- | --- | --- |
| Browser GUI visual result card after timeout correction | Not automated | This environment has no installed browser automation binary. The manual browser submission that produced execution `146` verified the operational path; execution `149` verified the updated production webhook contract. Open `http://localhost:18000`, submit the synthetic Maya Verma enquiry, and confirm the green `enriched` AI chip and persisted trace visually. |

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
