# Phase 3 self-review

## Review relationship and method

This correction pass reviewed the repository and preserved runtime from Phase 3 commit `6359d7aea8c59dfbe9c2353820338358438baa35`. Git confirmed both that commit and the original reviewed baseline `c11a6c13ab1885901aea81e93a748b19984e987c` are ancestors of the correction work. The review was performed by the implementing Codex agent from a skeptical maintainer perspective; it is not represented as an independent human or second-model audit.

The complete Phase 3 diff, migrations, backend services, workflow code, browser contract, tests, scripts, documentation, deployed workflow settings, retained executions, database state, and Mailpit messages were inspected. Negative checks included duplicate admissions and incidents, changed payloads, stale leases and callbacks, lost acknowledgements, expired permits, overlapping workers, process restart, every required HTTP class, long and malformed `Retry-After`, malformed 2xx responses, contacted/booked replay, and public-control authentication.

## Reviewer findings R1-R5

### R1 — reproduced: one rejection could mutate recovery twice

The quota boundary created and failed a second attempt while the caller already owned an open attempt. One rejected write could therefore increment twice, leave the first attempt unfinished, and invalidate the caller's lease before settlement.

The fix makes attempt ownership explicit. `start_attempt` creates one attempt bound to the active lease; `complete` and `fail` require that exact attempt and lease. The quota layer only grants or rejects the HTTP write and never mutates attempts. Diagnostic writes explicitly claim and settle their own attempt. Duplicate or stale settlements return a conflict without changing state.

The corrected live at-write rejection produced job `00c659fa-4815-49da-939f-4fa2f6be7fed`, attempt `74ae988d-6531-4436-a933-299d5de586c2`, and exactly one increment. It started at `2026-09-20T00:43:40.289788Z`, finished at `00:43:40.307459Z`, recorded status 429 and `Retry-After: 69`, returned a truthful HTTP 202 queued receipt without a CRM ID, and entered `retry_wait`. Recovery execution `515` used attempt `4c55da18-d191-4127-b0ed-07a6919bde9d` at `00:45:01.272015Z` and completed at `00:45:01.374902Z`, more than the required 69 seconds later.

### R2 — reproduced: HTTP outcome normalization was incomplete

The exported code did not recognize n8n fixtures shaped as `error.status`, so 401, 403, 409, 422, and 429 could be mislabeled as ambiguous transport failures. Reconciliation also collapsed non-404 failures into a false absence decision.

Both workflow validation nodes now normalize the installed and tested safe shapes: `error.status`, `httpCode`, `statusCode`, nested response status, and top-level status. Reconciliation distinguishes verified match, confirmed 404 absence, credential failure, throttling, transient/ambiguous failure, malformed success, and identity mismatch. The backend owns durable classification: 401/403 block and pause claims, business errors require review, 429 preserves the parsed minimum delay, transient failures use bounded backoff, and malformed success never completes. Control calls use a three-second timeout and writes use six seconds within the 30-second lease.

The installed n8n 2.39.8 execution `283` stored the real 429 as `httpCode`; workflow fixtures also prove the `error.status` variants. A second review found that successful writes were always recorded as 200. The validator now derives 201 for `created` and 200 for `replayed`, and passes that verified status to attempt settlement.

### R3 — partially reproduced: lock inversion risk and stale quota state

The reported job/fault lock-order inversion was present by inspection. Coordinated PostgreSQL tests did not reproduce a deadlock, but the inconsistent graph was unsafe. More importantly, the review reproduced a stale SQLAlchemy identity-map bug: ten concurrent permissions could all observe the old quota counter and exceed a five-slot window. It also found that the claim query omitted `LIMIT 1`, unnecessarily locking the eligible backlog.

All paths now acquire job then fault locks, the locked fault row is refreshed with `populate_existing`, and claim selects one row with `FOR UPDATE SKIP LOCKED LIMIT 1`. A permit is bound to the exact lease and expires no later than five seconds, the quota window, or the lease. Claim/release clears it; another lease cannot consume it. A crashed reservation conservatively consumes its fixed-window slot until reset rather than permitting an excess write. Overlapping active fault scopes are rejected under an ordered lock of all fault rows.

Disposable PostgreSQL tests coordinate distinct job claims, permission versus direct diagnostic writes, stale permits, quota limits across workers, expired lease reclaim, and backlog locking.

### R4 — reproduced: ID-only completion could be false

Admission could create an immediately completed job for a pre-existing lead with the same submission ID but different business data. Completion also checked only the lead relation, not correlation ID and fingerprint.

Admission and completion now require stable submission ID, correlation ID, and canonical payload fingerprint. CRM lookup and write acknowledgements validate the full typed identity, AI outcome, and allowed lifecycle/follow-up combination. Repeated admission reuses the stored validated payload; recovery does not rerun NVIDIA. A changed payload returns a controlled 409. Contacted and booked records retain persisted AI/lifecycle state, follow-up counts, appointments, and confirmation state. A late error event for already verified work is recorded as resolved rather than creating a false open incident.

### R5 — reproduced in part: demo success and cleanup were too weak

The CLI treated completed job labels as sufficient and did not fully prove exact manifest reconciliation. Failure cleanup could also obscure whether a scoped fault remained intentionally active for the next command.

The CLI now validates expected manifest identities, exact matching leads, zero missing IDs, zero duplicate IDs, fingerprint/correlation matches, and completed-job-to-lead linkage. It reports actual outbound attempts separately from quota reservations. Preparation restores only the invocation's prior scoped fault state on failure and explicitly reports the intentional hold on success. The expected diagnostic failure leaves its scoped quota active for the measured recovery; `disable` restores the safe state. It never truncates tables, erases inboxes, resets volumes, or edits execution history.

## Additional findings from the independent checklist

1. **Credential pause was job-local.** Other jobs could continue hammering the same invalid adapter credential. Any blocked 401/403 job now pauses new claims until authenticated manual requeue after the cause is corrected.
2. **Mixed-item incident correlation could select a successful attempt.** Incident lookup now prefers the failed attempt for the execution reference and normalizes the correlation ID from the durable job.
3. **Overlapping active fault runs were ambiguous.** Two operator-created runs could target the same submission. Activation now rejects overlap atomically.
4. **Successful attempt status lost 201 semantics.** The workflow now records 201 for created and 200 for replayed results.
5. **Repeated TestClient lifespan cycles could hang under Python 3.14.** Related authenticated fault assertions share one client-scoped test, and MIME parsing runs in an isolated subprocess. This preserves coverage without accepting a flaky rerun.
6. **The final runtime export had normalized defaults and layout not present in the committed JSON.** The live n8n nodes, connections, and settings were preserved in the sanitized export, including `binaryMode`, while runtime ownership/project metadata was deliberately excluded. Exact parity and the workflow suite were rerun after this correction.

No additional defect was found in the reviewed booking lock order, finite retry budget, HTTP-date parsing, committed-write reconciliation, manual one-shot requeue, queued browser truthfulness, lifecycle preservation, operator authentication, or SMTP separation. Their regression tests and the live evidence below support that conclusion within this project scope.

## Regression and live evidence

`scripts/verify_phase3.sh` passed with 79 Python/PostgreSQL tests, 13 browser tests, and 32 workflow tests, plus Ruff, migration, JSON, shell, Compose, diff, and tracked-content secret checks. The six-ID correction run `f544fc34-8c6b-4dc8-94f9-f125f867c4aa` survived a backend restart while pending and reconciled to 6/6 leads with zero missing, duplicates, or identity mismatches. Same-batch replay kept attempts at 6 and created no new business effects. The original 12-ID run remains 12/12, and booked Skyler remains booked with the original appointment and cancelled follow-up.

Mailpit contains newly generated multipart follow-up and booking messages. Raw MIME inspection confirmed equivalent text/plain and text/html bodies, escaped stored values, conditional details, the development notice, and Vancouver appointment rendering. The booking message `<bKhgFNLojiL8jCcDwUo4Ho@mailpit>` displays `Tuesday, September 22, 2026 at 10:30 AM (America/Vancouver)` and mentions cancellation because the persisted follow-up was actually cancelled. No screenshot or full browser visual automation is claimed.

## Residual risks and proof boundary

The work proves bounded durable recovery against the local development CRM, not a vendor quota or historical outage. The database quota is one local fixed-window simulator. SMTP acceptance and the later database commit remain separate effects; uncertain email sends are not automatically replayed. Mailpit is not a production provider, and appointments do not reserve external capacity. The deterministic verifier intentionally skips live n8n, NVIDIA, and Mailpit and identifies those separate checks. Phase 4, Make, and GHL were not started.

## Review of `d6fe8ccb40d29e953d1a515b9f6d798a56ad4719`

This later correction pass treated C1–C4 as hypotheses and reviewed the complete affected route, recovery service, workflow Code nodes, CLI, tests, runtime definitions, and retained executions. It preserved the earlier attempt-ownership, job-first locks, one-row claim, fingerprint, lifecycle, and multipart-email corrections.

### C1 — reproduced: immediate intake did not use the stored prepared payload

`RecoveryService.admit` correctly reused an existing matching job, but `durable_intake` passed the newest request payload to the provider. The fix validates `job.payload_json` back into `CRMLeadCreate` and uses it for every immediate creation/retry. When a Lead predates its first recovery job, admission reconstructs the canonical payload from the persisted Lead rather than a later NVIDIA result. Created results must match the stored AI state; replay/reconciliation may use a different valid persisted AI state only after submission ID, correlation ID, fingerprint, typed lifecycle, and follow-up validation.

The live prepared job `110491c1-a835-40be-9b9e-5d630802b490` was admitted as enriched, then repeated with the same business identity and a valid fallback AI result. It completed with one attempt; job, response, and Lead remained enriched with the original prepared summary. Lost-ack job `5ca59c16-3572-4e5e-bf4a-472d60793cde` committed Lead `29c57e8d-4256-49fb-aba4-85df747b016c`, deliberately omitted completion, expired its lease, and was reconciled by execution `728`. Its only attempt `7147e6c5-d69e-467b-bb6d-66cb0059c5a8` became `reconciled`; no second write occurred. A no-AI replay of booked Skyler returned persisted `appointment_booked`/`fallback_invalid`, one cancelled follow-up, one appointment, and the unchanged confirmation timestamp.

### C2 — reproduced: Retry-After parsing could crash settlement

Unicode `²` passed `isdigit()` but failed `int()`, and an oversized ASCII integer overflowed the due-time calculation. Parsing now accepts only ASCII decimal seconds, handles HTTP dates, and checks both PostgreSQL integer and Python datetime representability. Malformed values use the documented fallback without raising. An unrepresentable valid 429 minimum moves work to `needs_review`; write attempts retain `retry_after_raw`, and reconciliation holds escaped raw evidence in the safe job message. HTTP meaning takes precedence when the header is irrelevant: 401/403 still block even if they carry an oversized header. Tests cover normal seconds, 7200 seconds, HTTP date, missing/malformed, `²`, the 32-bit boundary, huge numeric values, year-9999 dates, write settlement, and reconciliation settlement.

### C3 — reproduced and closed against installed n8n

No retained execution proved a real 429 at the recovery workflow's own Write node. The first new setup was pre-empted by the minute scheduler and produced a normal 201, so it is not claimed as rejection evidence. Execution `703` then proved the Write node received 429, but inspection of the installed 2.39.8 envelope showed only `error.status`; response headers were absent, and the attempt used the generic fallback. That falsified the prior assumption that the configured parser could always see headers.

The supported HTTP Request options `Never Error` and `Include Response Headers and Status` now create an explicit `{body, headers, statusCode}` boundary for lookup and write, while Code nodes remain compatible with tested legacy error shapes. A subsequent setup (`717`/`718`) retained the header, but a harness query error disabled the fault before recovery; it is not claimed as same-quota evidence. The definitive run is execution `720`: `Write CRM Lead` stored status 429, `retry-after: 20`, and the real controlled detail; validation emitted `http_429`; attempt `802307c7-2595-4402-8166-292f0cc82c77` recorded one increment and due time exactly 20 seconds after settlement. Immediately before recovery the same run `4a948cc3-57c6-432d-b9c3-b0002d2f4fd9` was active with limit 1/window 20/count 1. Execution `722` created the Lead on attempt 2 after the window elapsed. No NVIDIA call was made; the stored payload was reused.

### C4 — reproduced in part: failure disposition was incomplete

`recover` raised without cleanup or an explicit named-scope disposition, and state inspection after successful mutation could occur outside protected sections. Preparation and diagnostic failures now restore only the invocation's newly created or prior named scope where possible. Cleanup failure reports both the original and cleanup errors. Recovery failure/exhaustion preserves evidence, inspects and prints the exact scoped state, and gives exact resume/disable commands rather than silently destroying the measured quota. Tests cover request failure, post-mutation inspection failure, cleanup ownership, recovery exhaustion, and intentional successful preparation that retains its hold.

### Additional findings from the second independent pass

1. **Lease expiry after CRM commit returned 500.** If the lead committed just before settlement lost its lease, immediate intake raised despite durable recoverability. It now returns truthful 202 queued without a CRM ID; the regression expires the lease after commit and completes through lookup reconciliation.
2. **Explicit non-2xx could be hidden by a success-shaped body.** After enabling full responses, typed validation initially checked the body but not the explicit status. Both reconciliation and write validation now require a missing legacy status or an actual 2xx. A 503 carrying a valid-looking CRM body cannot complete work.
3. **Unrepresentable Retry-After initially overrode credential semantics.** The first parser correction evaluated representability before status class. It now applies the special hold only to 429; 401/403 remain blocked and business failures keep their meaning.

No new defect was found in attempt-budget counting, stale callback rejection, quota lock order, permit ownership, duplicate admission, changed business-data conflicts, incident deduplication, booking/follow-up preservation, operator authentication, email MIME/idempotency, or diagnostic activation. Focused adversarial tests and the complete verifier cover those claims within this repository's synthetic boundary.
