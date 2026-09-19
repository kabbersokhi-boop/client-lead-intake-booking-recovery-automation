# Phase 3 recovery runbook

## Inspect

Set `CRM_ADAPTER_API_KEY` only in the local operator shell; never put it in frontend code or committed files.

```bash
CRM_ADAPTER_API_KEY=... .venv/bin/python scripts/phase3_demo.py status
curl http://localhost:18000/api/traces/<correlation-id>
```

`pending` is ready, `processing` has a lease, `retry_wait` has a future due time, `completed` has a verified matching lead, `needs_review` exhausted or needs correction, and `blocked` requires credential/permission action. A queued browser receipt is not a CRM lead.

## Retry versus review

429 and transient/ambiguous failures retry only after reconciliation and their durable due time. Valid `Retry-After` wins and is never shortened. 400/404/409/422 go to review; 401/403 block work. Do not alter stored payloads or identities to bypass these states.

After correcting the cause, authenticated `POST /api/recovery/jobs/<job-id>/requeue` authorizes exactly one manual attempt. It does not delete history or reset `attempt_count`. Another failure returns the job to review.

## Pause, resume, and restart

Disable only `phase3-crm-write-recovery` to pause claims; do not delete jobs. Leases expire after 30 seconds and become reclaimable. A stale token cannot complete a reclaimed job. Resume by publishing that workflow. Restart only the relevant backend or n8n container; never remove `n8n_data` or PostgreSQL volumes.

## Controlled fault test

```bash
export CRM_ADAPTER_API_KEY=...
.venv/bin/python scripts/phase3_demo.py prepare
.venv/bin/python scripts/phase3_demo.py before
.venv/bin/python scripts/phase3_demo.py recover
.venv/bin/python scripts/phase3_demo.py disable
```

Use `PHASE3_MANIFEST` for the fresh fixture. `prepare` registers and holds only listed IDs. `before` releases and invokes the unsafe diagnostic webhook. Always run `disable`, even after failure. Keep the diagnostic workflow disabled outside the exercise.

## Preserve and hand over

Do not truncate tables, delete n8n executions, erase Mailpit, reset volumes, or edit failed status. Hand over the manifest/run ID, job states, attempts, incident, execution IDs, and whether faults/diagnostic are disabled. Payloads are private runtime data and must not be copied into public incident documents.
