# Project handover

This is the living continuity document for `kabbersokhi-boop/client-lead-intake-booking-recovery-automation`. A new review or implementation chat should read this file first, then inspect current `main` and the phase-specific evidence before changing anything.

Future phases must update this document before their final commit so the repository alone records the current approved state, evidence, boundaries, next work, and unresolved decisions.

## Current checkpoint

- Review date: 2026-09-20.
- Approved Phase 4 SHA: `3eba4ff17084ab953942b4928ce818ac11d6cf2a`.
- Previous Phase 4 baseline: `881bd0db75ca9b3e246fc716d72463c28f9d57e8`.
- Exact-SHA CI: run `35523002102`, job `106110225411`, successful at the approved SHA.
- CI counts: 93 backend/Python/PostgreSQL tests, 28 frontend/helper tests, and 36 workflow tests, 157 total. These categories must not be described as though every frontend test is a real-browser test or every backend test is a PostgreSQL test.
- Phases 1–4 are approved for their defined local reference-demo scope.
- Phase 5 is next. Make reporting, Phase 6 GHL integration, and Phase 7 final presentation work are not implemented at this checkpoint.
- Approval does not assert universal bug freedom, production readiness, or a guaranteed hiring outcome.

Before new work, verify that current `HEAD`, `origin/main`, the worktree, runtime, and CI still match the intended starting point. Do not assume this recorded SHA is still current.

## Review provenance and limits

The approval review considered the GitHub branch, approved commit and diff, Operations backend and frontend, focused test code, actual CI logs, and committed verification evidence. The reviewer also ran 33 isolated backend URL/screening checks and 31 isolated frontend URL-validator checks; all passed. Those checks copied source functions rather than exercising a complete checkout or the user's runtime.

The review environment could not resolve `github.com`, so that reviewer did not obtain a local clone, run the full suite locally, or independently perform the authenticated n8n browser walkthrough. Authenticated Chrome 148 rendering of executions `283` and `292` and the desktop/390-pixel Operations layouts are committed Codex observations in `docs/phase-4-verification.md`, not browser observations independently witnessed by that reviewer. This distinction must be preserved when describing the evidence.

## Approved phase status

### Phase 1 — intake and enrichment

Approved local intake accepts and validates synthetic enquiries, preserves `submission_id` and `correlation_id`, calls optional NVIDIA enrichment within bounded time, and safely falls back when enrichment is unavailable or invalid. Intake persistence must not depend on AI success.

Retained execution `146` is NVIDIA timeout/fallback evidence. The optional enrichment failed, but the lead-preserving workflow succeeded; it must not be described as a red failed workflow or a lost lead.

### Phase 2 — lifecycle, booking, and email

Approved behavior includes persisted lead lifecycle state, scheduled follow-up, booking, follow-up cancellation when booking wins the race, confirmation delivery through Mailpit, replay-safe request identities, concurrency handling, and trace inspection.

This remains a synthetic development calendar and local email boundary. SMTP acceptance and the later PostgreSQL commit are separate effects, so the project does not promise universal exactly-once email delivery after crashes or lost acknowledgements.

### Phase 3 — durable CRM-write recovery

Approved behavior includes the canonical prepared payload, durable CRM-write jobs, attempts, bounded leases and retries, quota permits, `Retry-After`, reconciliation by durable identity, incident recording, n8n recovery workflows, and preserved failed-run evidence.

The diagnostic workflow is a deliberate local failure harness. It is not evidence of a real vendor outage or client incident. Error Workflow settings connect the diagnostic failure to the error recorder; intake and recovery are connected through shared durable jobs and API state, not a direct canvas wire.

### Phase 4 — read-only operations view

Approved Phase 4 adds `/operations.html` and read-only projections for summary, jobs, job detail, and incidents. It uses immutable applied-query semantics, request-generation guards, explicit timeout and stale-data behavior, allowlisted response schemas, recorded-text screening, and local n8n link validation.

The operations architecture remains:

```text
operations.html
  -> FastAPI /api/operations/... GET projections
  -> SQLAlchemy
  -> durable PostgreSQL records
```

The browser never connects directly to PostgreSQL. Viewing Operations must not claim, retry, requeue, resolve, send, invoke external services, schedule background work, or mutate durable records.

The installed n8n `2.39.8` execution route is:

```text
/workflow/{workflow-id}/executions/{execution-id}
```

Only `RecoveryIncident` currently stores both workflow and execution identity. Safe incident references may therefore become clickable local links. `CRMWriteAttempt` and `CRMWriteJob` store execution references without durable workflow identity, so those references remain visible text. Do not add guessed mappings, infer workflow identity from execution-number ranges, or rewrite historical evidence.

The Phase 4 deep-link correction, browser evidence, security constraints, read-purity checks, and residual limits are recorded in `docs/phase-4-verification.md` and `docs/phase-4-self-review.md`.

## Retained execution evidence

Keep these evidence chains distinct in documentation, screenshots, demonstrations, and interview explanations:

1. **Original controlled diagnostic and recovery:** diagnostic failure `283` -> automatic error-recorder execution `284` -> recovery executions including `292` and `294` -> 12/12 reconciliation.
2. **Corrected recovery Write-node throttling:** recovery execution `720` received the real local development CRM `429` and retained `Retry-After`; execution `722` completed after the required delay.
3. **Lost-acknowledgement reconciliation:** execution `728` reconciled a committed lead without issuing a duplicate create.
4. **Optional AI fallback:** execution `146` retained the lead despite NVIDIA timeout/fallback and is not a failed overall intake.

Additional retained Phase 4 reference data:

- Job: `e3f7d48d-64c3-4bd0-8d44-6d9d2d2c4e69`.
- Correlation: `236169e3-7c3e-4243-8a94-251ac4f9869a`.
- Linked chain: failed HTTP 429 attempt/execution `283`, later completed attempt/execution `292`, resolved incident, and contacted Lead.
- Authenticated Chrome verification at the approved Phase 4 SHA opened diagnostic execution `283` and directly opened recovery execution `292`. Operations links `283` because its incident durably identifies the workflow; it intentionally renders attempt/job reference `292` as text.

Do not delete, regenerate, cosmetically rewrite, or merge these separate evidence stories. Use retained evidence rather than reactivating fault injection unless a future phase explicitly requires a new controlled test.

## Current architecture and responsibility split

- **Browser UI:** synthetic intake, booking, trace, and read-only Operations views.
- **FastAPI application:** validation, durable domain state, development CRM boundary, lifecycle and booking services, email boundary, recovery control APIs, and operations projections.
- **PostgreSQL:** authoritative application, lifecycle, recovery-job, attempt, and incident records.
- **n8n:** customer-critical intake orchestration, booking orchestration, follow-up scheduling, error recording, and CRM-write recovery dispatch.
- **NVIDIA NIM:** optional structured enrichment with safe fallback; it is not allowed to decide whether a valid lead is preserved.
- **Mailpit:** local development SMTP capture, not a production email provider.
- **Development CRM adapter:** explicit local stand-in, never GoHighLevel.
- **Make:** not implemented; reserved for downstream management/reporting rather than customer-critical transaction ownership.

Preserve the separation that n8n owns customer-critical intake, booking, and recovery, while Make handles downstream management/reporting. A reporting failure must not undo a lead, block booking, or alter recovery truth.

## Honesty and security boundaries

- All demonstrated customer records and scenarios are synthetic.
- This is a fresh technical-interview reference build, not a historical paid-client deployment.
- Controlled failures are not real vendor outages or client incidents.
- The development CRM must never be relabelled as GoHighLevel.
- The synthetic appointment calendar does not reserve external technician capacity.
- Mailpit delivery is not production delivery.
- The project demonstrates bounded idempotency, reconciliation, and concurrency behavior; it does not claim universal exactly-once external effects.
- Job completion is not a booked appointment. Job counts are not automatically lead counts. Business measures must come from the appropriate Lead and Appointment records.
- Do not invent conversion, revenue, ROI, time-saved, diagnosis, pricing, service area, technician dispatch, response-time, availability, or repair claims.
- Keep PostgreSQL and n8n loopback/private. Do not expose the database or Operations page merely to support reporting.
- Keep webhook URLs, API keys, tokens, OAuth credentials, authorization headers, and unrelated account information out of Git, chat, screenshots, fixtures, and documentation.
- Preserve the approved response allowlists, redaction canaries, GET read purity, safe-link rules, and Phase 1–3 business behavior.

## Phase 5 — next: Make reporting

Phase 5 is proposed, not implemented. The intended direction is a small, separate reporting flow that reads committed application state, sends a minimized management report to a Make custom webhook, and writes a management-readable result to an agreed destination such as Google Sheets.

Before implementation, settle and record:

- the exact management question and metric definitions;
- which Lead and Appointment fields truthfully support those metrics;
- report identity, idempotency, replay, and duplicate-handling behavior;
- reporting schedule and time zone;
- destination and table/sheet shape;
- error visibility and retry behavior that cannot affect customer-critical automation;
- the user's actual Make Free-plan workspace, available modules, and account access;
- the chosen destination and its real permissions.

Provide the user click-by-click Make UI guidance using the actual Free-plan interface. Do not purchase, upgrade, or rely on a paid feature without explicit user direction. The outbound Make request must not require a public PostgreSQL connection, a public Operations page, or an unnecessary tunnel.

## Phase 6 — conditional GHL status

Only a free GoHighLevel trial is in scope. Phase 6 must first verify actual account access, API availability, authentication options, and trial restrictions.

If live GHL API access is available, distinguish verified API behavior from UI-only configuration and document real mappings and evidence. If API access remains unavailable, clearly separate:

- GHL UI configuration;
- field and pipeline mapping readiness;
- proposed integration design;
- live integration that was not verified.

Never rename the development CRM as GHL, imply a live GHL result that was not observed, or hide trial/account limitations.

## Phase 7 — final polish and teaching

Phase 7 is committed future work, not completed work. It must include all sections below.

### HVAC business wording and email polish

- Present a clear synthetic furnace and air-conditioning service-business story. Existing broader home-service categories do not need to be removed only for presentation.
- Current email bodies are deterministic templates populated from persisted data, not newly AI-generated copy. Improve service labels, subjects, and wording so messages sound like useful furnace/AC customer communications rather than backend status output.
- Keep development/test disclosure visible.
- Never claim a real technician was dispatched, external capacity was reserved, or a customer's preferred time is a confirmed appointment unless the actual system proves it.
- Do not invent a diagnosis, repair recommendation, price, coverage area, response guarantee, availability, or visit status.
- Provide neutral wording when enrichment is missing.
- Preserve HTML and plain-text alternatives, escaping, header safety, sender identities, scheduling, follow-up cancellation semantics, and the SMTP/database uncertainty limitation.
- Give each follow-up a truthful purpose and usable next step. Do not add fake booking buttons, unsupported reply handling, fictitious contact details, or unsupported appointment-management links.
- No additional model call is required solely to polish deterministic wording.

### GitHub as a visual engineering case study

- Keep the README concise and readable; place detailed walkthroughs under `docs/` rather than creating a wall of screenshots.
- Add selected real screenshots with short captions explaining the business action, observed result, failure, diagnosis, correction, and verification.
- Include the lead form, n8n intake, persisted trace, booking state transition, Mailpit confirmation, Operations view, and actual Make/GHL results only where live-verified.
- Include failed-run and recovery evidence while keeping the separate execution chains accurate.
- Use only completed implementation evidence. Do not invent, cosmetically falsify, or stage results that the system did not produce.
- Remove secrets, webhook URLs, auth headers, unrelated account data, and real personal data. Retain only synthetic customer examples.
- Finish the README only after the external-integration status is known, so it accurately distinguishes local, configured, and live-verified components.

### Interview PDF and teaching material

- Rebuild the final PDF from the completed system; the old PDF is only a draft.
- Include plain English, a glossary, technical architecture, phase history, business value, limitations, troubleshooting/runbook guidance, likely questions and answers, and exact phrases the user can rehearse.
- Teach the normal click-by-click journey: submit a fresh synthetic lead, show its intake execution, inspect persisted state, book before follow-up is due, show cancellation and booking confirmation in Mailpit, then inspect Operations.
- State exactly which workflows to open, in which order, how each is connected, and what proves the connection.
- Explain that the diagnostic workflow is a local failure harness, Error Workflow settings connect the error recorder, and shared durable PostgreSQL/API state connects intake to recovery. Do not invent a direct canvas connection.
- Keep execution `283`/`284`/`292`/`294`, `720`/`722`, `728`, and `146` as separate evidence stories.
- Explain idempotency versus global email deduplication, submission and booking IDs versus correlation IDs, canonical prepared payload, uncertain acknowledgements, leases, attempt counting, `Retry-After`, lifecycle races, PostgreSQL, and Mailpit.
- Do not promise universal exactly-once effects.
- Prepare a timed 10–15 minute core demonstration with optional technical depth, realistic interviewer questions, fallback material for unavailable external services, and a final real-browser rehearsal.
- Emphasize comprehension, honest boundaries, and maintainability; do not suggest the project guarantees a hiring outcome.

## Final demonstration sequence

The final rehearsal should use a fresh synthetic lead for the normal journey while preserving historical fault evidence:

1. Open the lead form and submit a new synthetic furnace/AC enquiry.
2. Open the matching n8n intake execution and identify validation, optional enrichment/fallback, canonical persistence, and acknowledgement.
3. Inspect the persisted correlation trace and explain submission versus correlation identity.
4. Book before the follow-up becomes due.
5. Show the follow-up cancellation and the appointment/booking confirmation captured in Mailpit.
6. Open Operations, refresh manually, locate the job by a durable identifier, inspect attempts/incidents, and follow safe trace/execution links.
7. Use retained diagnostic and recovery executions for failure teaching rather than recreating them.
8. Show Make and GHL only to the extent actually completed and live-verified in their future phases.

Prepare fallback screenshots and repository evidence in case an external service is unavailable during the interview.

## Review protocol for future phases

For each new phase:

1. Inspect current `main`, worktree, runtime, phase documentation, and relevant tests before editing.
2. Preserve unrelated approved behavior and retained evidence.
3. Treat reviewer findings as hypotheses: independently reproduce or falsify them.
4. Choose the narrowest correct architecture rather than patching wording mechanically.
5. Add negative and behavioral coverage for the real contract.
6. Review the complete phase diff adversarially after tests pass.
7. Run the appropriate focused checks and established full verifier without weakening existing tests.
8. Verify runtime evidence only through safe operations; do not trigger NVIDIA, SMTP, fault injection, workflow imports, or record mutation unless the phase explicitly requires it.
9. Update this handover and the phase-specific verification/self-review documents before the final commit.
10. Push the exact final SHA, verify `HEAD == origin/main`, require a clean worktree, and confirm exact-SHA CI.

Do not pursue endless speculative hardening at the expense of the interview business story. Fix material defects, preserve truth, and keep the implementation small enough to explain.

## Authoritative documents

Read these alongside this handover:

- `README.md`
- `docs/architecture.md`
- `docs/phase-1-verification.md`
- `docs/phase-2-verification.md`
- `docs/phase-3-verification.md`
- `docs/phase-3-failed-run-postmortem.md`
- `docs/phase-3-runbook.md`
- `docs/phase-3-self-review.md`
- `docs/phase-4-verification.md`
- `docs/phase-4-self-review.md`
- `backend/app/api/operations.py`
- `frontend/operations.js`

If this handover conflicts with current code or a later approved phase document, inspect history and current runtime evidence rather than silently choosing the more convenient claim. Update this file to resolve the discrepancy before closing the phase.
