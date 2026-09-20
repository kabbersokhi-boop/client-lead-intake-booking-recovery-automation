# Phase 3 verification

Verified locally on 2026-09-20 IST from reviewed baseline `c11a6c13ab1885901aea81e93a748b19984e987c`. That baseline is an ancestor of the Phase 3 commits. All records are synthetic. This is a controlled local fault-injection test, not evidence of a vendor quota or historical client outage.

## Deterministic verification

`scripts/verify_phase3.sh` was executed. It created a disposable PostgreSQL 16 container, discovered every configured test file, and removed that container on exit.

- Python/PostgreSQL: 79 passed, 0 skipped.
- Browser helpers: 13 passed, 0 skipped.
- Workflow code/structure: 32 passed, 0 skipped.
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

## 2026-09-20 correction-pass evidence

This section appends evidence from the review of Phase 3 commit `6359d7aea8c59dfbe9c2353820338358438baa35`; it does not replace or alter the original failed execution.

### Corrected at-write 429 and attempt count

An authenticated durable intake for scoped job `00c659fa-4815-49da-939f-4fa2f6be7fed` exhausted the registered fault quota at the actual CRM write boundary. The response was HTTP 202 queued with no CRM lead ID and retained the real `Retry-After: 69` minimum. Exactly one outbound call created exactly one attempt:

- attempt `74ae988d-6531-4436-a933-299d5de586c2`, number 1;
- started `2026-09-20T00:43:40.289788Z`, finished `00:43:40.307459Z`;
- status 429, raw/parsed retry delay 69 seconds, durable state `retry_wait`.

Recovery execution `515` started attempt `4c55da18-d191-4127-b0ed-07a6919bde9d` at `00:45:01.272015Z` and completed at `00:45:01.374902Z`. The approximately 81-second interval did not shorten the 69-second minimum. The successful create is now recorded as status 201; replay results are recorded as 200.

After deploying that final export, synthetic no-AI job `d7d2c4b6-349b-40bc-8f31-98b895c828d8` completed in n8n execution `583`. Its sole attempt `68415751-06e0-48ab-9a22-8085245d231f` ran from `01:16:37.728708Z` to `01:16:37.820940Z` and persisted status 201, confirming the runtime uses the corrected export.

Two setup calls are retained but are not claimed as rejection evidence: one 40-second window elapsed before the call, and one job was reclaimed by the scheduled recovery worker. They returned normal created/replayed outcomes and did not have their histories edited.

### Correction batch, replay, and restart

Review fixture run `f544fc34-8c6b-4dc8-94f9-f125f867c4aa` contains six stable fictional identities. All six were prepared through the real intake contract while delivery was held. The backend was restarted with all six jobs still pending. After release, the recovery workflow completed 6/6 jobs and CRM leads with zero missing IDs, zero duplicate IDs, and zero correlation/fingerprint mismatches. Six jobs produced six actual write attempts; quota deferrals did not increment attempt counts.

The same manifest was recovered again. Before and after remained 6/6 complete and matching, and attempts remained 6 rather than increasing. No lead, follow-up, appointment, or confirmation effect was recreated.

The original twelve-ID manifest remains 12/12 unique and matching. Skyler Martin remains `appointment_booked` with appointment `d489e88a-2620-4aa9-8742-71348a6f14d2`, the same cancelled follow-up, and an unchanged confirmation timestamp.

### Ordinary intake and Mailpit

With all fault controls disabled, ordinary n8n intake for submission `b4d6ffcc-a113-4e18-be85-6ace90f7d633` returned 201 and created lead `dc4fe054-edba-4338-824f-51c33cb8d8ba`. The observed AI state was honestly recorded as `fallback_invalid`; no repeated model probe was used to force enrichment.

Actual Mailpit raw messages were inspected without erasing the inbox:

- Follow-up Mailpit ID `5Nj6evFTJAs3mdkuhUK8uQ`, subject `Follow-up: Electrical Service request`, has `multipart/alternative` text/plain and text/html parts, persisted service/location values, and the development notice.
- Booking Message-ID `<bKhgFNLojiL8jCcDwUo4Ho@mailpit>`, subject `Appointment confirmed: Furnace Service`, has both MIME parts and displays the persisted appointment as `Tuesday, September 22, 2026 at 10:30 AM (America/Vancouver)`. It mentions cancellation because that lead's stored follow-up is actually `cancelled`.

This was a raw MIME and content inspection, not a claimed browser screenshot or full visual automation run.

### Runtime parity and safe state

The deployed recovery workflow is active and the diagnostic workflow is inactive. Their nodes, connections, settings, finite timeouts, and `phase3-crm-recovery-error` links were compared with the sanitized exports. Executions `146`, `283`, `284`, and `515` remain retained. SQLite inspection included the WAL and SHM files so current execution rows were not mistaken for a stale main-file snapshot.

All registered fault runs were disabled with delivery holds off at the end. No volume, prior execution, Mailpit message, lead, or audit history was deleted. The deterministic verifier's live skip is intentional; the local runtime checks above were executed separately.
