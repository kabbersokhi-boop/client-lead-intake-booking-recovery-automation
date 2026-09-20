# Phase 4 verification

## Scope

Phase 4 adds `http://localhost:18000/operations.html` plus `GET /api/operations/summary`, paged `GET /api/operations/jobs`, `GET /api/operations/jobs/{job_id}`, and paged `GET /api/operations/incidents`. The page reads the same durable records used by automation: an operator can locate an enquiry, inspect recorded attempts/retry timing, see a verified CRM lead where present, and follow correlation/execution references. Viewing it does not retry or change anything.

## Semantics and boundary

- Summary has all six current job states (including zero) and a separate open-incident count, at a server-generated observation time. Completed is not labelled recovered.
- Lists filter and paginate server-side (25 default, maximum 100); jobs order by `created_at DESC, id DESC`.
- No completed Lead renders as `Pending CRM creation`; retry eligibility appears only for `retry_wait`; reconciliation failures and actual write attempts remain separate.
- This local synthetic-demo surface is not production authentication or health monitoring. It excludes adapter keys, payloads, leases, quota permits, provider bodies, and arbitrary metadata. n8n links require numeric references and a configured loopback editor base.

## Initial focused checks

```bash
.venv/bin/python -m pytest -q backend/tests/test_operations.py
.venv/bin/ruff check backend/app backend/tests/test_operations.py
node --check frontend/operations.js
npm run test:browser
```

The disposable-fixture suite covers zero-state aggregates, multiple attempts per job, filtering, stable pagination, invalid/unknown IDs, pending and completed jobs, reconciled attempts, resolved/unlinked incidents, numeric/unsafe execution references, redaction canaries, and GET read purity. The PostgreSQL integration test exercises the same projection directly against the disposable migrated database.

## Final deterministic and runtime evidence

- `./scripts/verify_phase3.sh` passed on the final worktree: 92 Python/SQLite/PostgreSQL tests, 15 browser-helper/static frontend tests, and 36 workflow-code/structure tests; lint, Compose config, JSON/shell syntax, diff check, and tracked-content secret scan also passed.
- Rebuilt only the existing Compose backend, then received HTTP 200 from `/operations.html`, `/api/operations/summary`, and a retained job detail. The summary observed 36 completed jobs and 2 open incidents at `2026-09-20T13:43:17Z`.
- API job `e3f7d48d-64c3-4bd0-8d44-6d9d2d2c4e69`, correlation `236169e3-7c3e-4243-8a94-251ac4f9869a`, showed a retained failed HTTP 429 attempt in n8n execution `283`, then completed attempt `292`, a resolved linked incident, and a verified contacted Lead. Read-only PostgreSQL queries independently returned the same completed/2-attempt/resolved chain.
- No Phase 3 fault scope, recovery worker, n8n workflow, NVIDIA request, SMTP send, or Mailpit message was triggered for this phase.

No Chromium/Chrome/Playwright binary was available after checking the local toolchain, so no visual-browser automation was performed. Manual visual checklist: open `/operations.html` at desktop and narrow viewport; refresh; filter each state; paste a valid/invalid/unknown UUID; select two jobs quickly; inspect escaped error text and unlinked incidents; open the trace link and confirm the existing intake booking context is not changed; confirm the numeric n8n link opens only the local editor route.
