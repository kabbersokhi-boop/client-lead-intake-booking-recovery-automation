# Phase 3 verification

Verified locally on 2026-09-20 IST from reviewed baseline `c11a6c13ab1885901aea81e93a748b19984e987c`. That baseline is an ancestor of the Phase 3 commits. All records are synthetic. This is a controlled local fault-injection test, not evidence of a vendor quota or historical client outage.

## Deterministic verification

`scripts/verify_phase3.sh` was executed. It created a disposable PostgreSQL 16 container, discovered every configured test file, and removed that container on exit.

- Python/PostgreSQL: 56 passed, 0 skipped.
- Browser helpers: 13 passed, 0 skipped.
- Workflow code/structure: 26 passed, 0 skipped.
- Ruff, JSON parsing, shell syntax, Compose validation, `git diff --check`, and tracked-content secret scan passed.
- Live n8n/NVIDIA/Mailpit checks are explicitly skipped by that deterministic script and were executed separately below.

Exact command: `scripts/verify_phase3.sh`.

## Runtime preservation

n8n reported version `2.39.8`. Before and after the required restart it retained image reference `n8nio/n8n:latest`, volume `n8n_data:/home/node/.n8n`, loopback binding `127.0.0.1:5678`, the Compose network, and `unless-stopped` policy. Previous workflows and execution evidence, including Phase 1 execution `146`, were not deleted.

Runtime IDs: intake `GKMASmZ5xo0UaWUY`; booking `phase2-appointment-booking`; follow-up `phase2-follow-up-dispatch`; error recorder `phase3-crm-recovery-error`; diagnostic `phase3-crm-write-diagnostic`; recovery `phase3-crm-write-recovery`. Diagnostic and recovery were verified linked to the error recorder.

## A — failed run

Manifest run `1d3cbbed-58c3-44c9-bc2d-a174be090585` contains 12 stable submission/correlation pairs. Intake prepared real NVIDIA outcomes while CRM delivery was held.

- Failed n8n execution: `283`, status `error`, `2026-09-19T20:39:28.430Z`–`20:39:28.815Z`.
- Failed node: `Diagnostic CRM Write Without Recovery`.
- Cause: actual local CRM HTTP `429`; n8n stored `NodeApiError`, and durable attempts linked to execution `283` stored the actual `Retry-After: 10` interpretation.
- Automatic error workflow: execution `284`, status `success`, `20:39:28.917Z`–`20:39:28.989Z`.
- Incident key: `phase3-crm-write-diagnostic:283:Diagnostic CRM Write Without Recovery`, linked to job/correlation through attempt execution reference `283`.
- Before reconciliation: expected 12, actual leads 10, missing 2, duplicate submission IDs 0.

The diagnostic used direct authenticated POST writes with recovery and shared pacing disabled. It was a real published webhook execution; no execution status was edited.

## B — recovery

Skyler Martin (`submission_id=3204d9d5-cffc-4e35-8f72-6221b264ec90`) was written before the 429 and booked through n8n execution `287` while its follow-up was pending. Appointment `d489e88a-2620-4aa9-8742-71348a6f14d2` was created, the follow-up was cancelled, and Mailpit accepted one confirmation.

The n8n worker was restarted while durable jobs remained. Recovery executions `289`–`297` reconciled existing results and performed missing writes. Missing-job attempts in executions `292` and `294` completed at `20:41:20.022Z` and `20:41:22.328Z`. Final scoped result: 12 expected, 12 leads, zero missing, zero duplicate submission IDs. The linked incident moved to `resolved` only when execution `292` verified the CRM result.

## C — replay

The completed batch was dispatched again. Scoped counts remained exactly 12 leads, 12 follow-ups, and 2 appointments before and after. Skyler remained `appointment_booked`, with the same appointment and one `cancelled` follow-up. Attempt/audit history was retained.

## D — fresh work and pacing

Fresh run `f34edebe-7615-42c8-a795-bf3687a7babd` prepared six enquiries through live intake executions `301`–`305` and `307`. Recovery wrote the first five from `20:43:12.581Z` through `20:43:17.322Z`. Shared quota denied a sixth immediate permission without counting an attempt; execution `319` sent it at `20:43:23.843Z`, across the fixed ten-second window. Final result: 6/6 leads, zero missing, zero duplicates, one attempt per job.

## E — durability

Only n8n was restarted while the main batch had unfinished jobs. PostgreSQL and its volume were not restarted or cleared. The same jobs were claimed and completed after restart. Automated coverage separately proves expired-lease reclaim and stale-token rejection.

## F — regressions

- Ordinary intake execution `320` returned HTTP 201 with lead `1f0f0254-1e32-46c8-9408-8ec11447bb75`, NVIDIA `enriched`, and one pending follow-up.
- Booking executions `286`/`287` produced real Mailpit confirmations. Execution `287` is the pending-follow-up cancellation case.
- Follow-up execution `285` delivered scoped Phase 3 messages to Mailpit. Message IDs and recipients were inspected without deleting the inbox.
- Existing booking, timezone, lifecycle, and idempotency assertions remain in the complete deterministic suite.

## Final state and limits

Both fault runs were disabled and reset. The diagnostic workflow was disabled after evidence capture; recovery and error recording remain available. This phase does not establish a real vendor limit, solve uncertain SMTP delivery, reserve external calendar capacity, or provide exactly-once email.

The exact final-commit CI run is recorded in the completion report after push; a Git commit cannot embed its own eventual SHA without creating another commit.
