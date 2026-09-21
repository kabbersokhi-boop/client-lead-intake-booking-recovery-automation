# Project handover

This is the living continuity document for `kabbersokhi-boop/client-lead-intake-booking-recovery-automation`. A new review or implementation chat should read this file first, then inspect current `main` and the phase-specific evidence before changing anything.

Future phases must update this document before their final commit so the repository alone records the current approved state, evidence, boundaries, next work, and unresolved decisions.

## Current checkpoint

- Review date: 2026-09-21.
- Phase 6 fallback starts from approved Phase 7A checkpoint `bfc4d88dbfb291b2dbcb52eb77e2ab6c2a13dd1b`.
- Phase 6 implements a separate HighLevel HTTP adapter and loopback-only local contract simulator
  for the documented contact/opportunity subset. It is not a live integration or vendor sandbox.
- Phase 6 deterministic verification: 121 Python tests, 28 frontend/helper tests, and 43
  workflow tests (192 total), plus Ruff, simulator JavaScript/JSON/shell syntax, Compose
  validation, `git diff --check`, and tracked-content secret scanning.
- Phase 7A presentation-hardening implementation SHA: `235d1f55156820a1aa0a0b7416bf6a44a3533e4f`.
- Phase 7A deterministic verification: 98 Python tests, 28 frontend/helper tests, and 43
  workflow tests (169 total), plus Ruff, JavaScript/JSON/shell syntax, Compose validation,
  `git diff --check`, and tracked-content secret scanning. Exact-SHA CI is required after push.
- Approved Phase 5 implementation SHA: `69c2a9e6c65f939ecd59317d51f5a14d2afa5db3`.
- Phase 5 implementation exact-SHA CI: run `35535162885`, job `106142768361`, successful.
- Phase 5 CI counts: 98 backend/Python/PostgreSQL tests, 28 frontend/helper tests, and
  43 workflow tests, 169 total.
- Approved Phase 4 SHA: `3eba4ff17084ab953942b4928ce818ac11d6cf2a`.
- Previous Phase 4 baseline: `881bd0db75ca9b3e246fc716d72463c28f9d57e8`.
- Phase 4 exact-SHA CI: run `35523002102`, job `106110225411`, successful at the approved SHA.
- Phase 4 CI counts: 93 backend/Python/PostgreSQL tests, 28 frontend/helper tests, and
  36 workflow tests, 157 total. These categories must not be described as though every frontend
  test is a real-browser test or every backend test is a PostgreSQL test.
- Phases 1–4 are approved for their defined local reference-demo scope.
- Phase 5 is implemented and live-verified for the synthetic local reference-demo scope. The
  authenticated aggregate reporting API and separate inactive manual n8n workflow sent real
  reports through Make to Google Sheets. Executions `1614` and `1654` proved first-row creation
  and corrected same-key refresh without duplication. Isolated failure execution `1662` failed
  visibly without changing customer-critical durable counts. See
  `docs/phase-5-verification.md` for exact evidence and limitations.
- Phase 6 local fallback is implemented and live-local verified. Live HighLevel authentication,
  account mappings, responses, and effects remain unverified. Phase 7B screenshots, final case
  study, browser rehearsal, and final interview PDF remain incomplete.
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

## Phase 7A diagnostic incident review

Read-only inspection of current Operations projections, retained n8n execution rows, and the
recovery resolution rules established the following. Do not rewrite any execution history or
incident merely to improve the demonstration.

- Execution `272` is a `WrappedExecutionError` at `Validate Prepared Backlog`: the diagnostic
  precondition rejected input because it was not the expected bounded jobs array. Its incident is
  open and unlinked because no durable CRM-write job, attempt, or correlation was created.
- Execution `276` is an earlier `NodeApiError` at `Diagnostic CRM Write Without Recovery`: a
  controlled local rate-limit failure. Its incident is open and unlinked because it has no
  durable CRM-write job, failed attempt, or correlation for verified recovery to complete.
- Execution `283` is the canonical controlled rate-limit failure. Its durable failed attempt
  links it to job `e3f7d48d-64c3-4bd0-8d44-6d9d2d2c4e69` and correlation
  `236169e3-7c3e-4243-8a94-251ac4f9869a`; recovery execution `292` verified completion, which
  truthfully resolved the linked incident. Automatic Error Workflow execution `284` remains its
  preserved successful recorder evidence.

The only supported incident-resolution behavior resolves open incidents for a linked job after
verified CRM completion. It does not provide an arbitrary dismiss action. Therefore `272` and
`276` are intentionally unchanged and remain visible as historical unlinked incidents; `283` and
`284` are preserved exactly.

## Current architecture and responsibility split

- **Browser UI:** synthetic intake, booking, trace, and read-only Operations views.
- **FastAPI application:** validation, durable domain state, development CRM boundary, lifecycle and booking services, email boundary, recovery control APIs, and operations projections.
- **PostgreSQL:** authoritative application, lifecycle, recovery-job, attempt, and incident records.
- **n8n:** customer-critical intake orchestration, booking orchestration, follow-up scheduling, error recording, and CRM-write recovery dispatch.
- **NVIDIA NIM:** optional structured enrichment with safe fallback; it is not allowed to decide whether a valid lead is preserved.
- **Mailpit:** local development SMTP capture, not a production email provider.
- **Development CRM adapter:** explicit local stand-in, never GoHighLevel.
- **HighLevel adapter:** optional HTTP projection that composes the development persistence path
  in `highlevel_simulator` mode; it normalizes vendor-contract behavior but does not own retries.
- **HighLevel Contract Simulator:** separate isolated test service at `http://localhost:18080`;
  it implements only the used contact/opportunity subset and is not HighLevel or a vendor sandbox.
- **Make:** downstream management routing only. The private Custom Webhook, Data Store branch,
  and Google Sheets destination are live-verified for one synthetic report key. Make remains
  outside customer-critical transaction ownership and has no database credentials.

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

## Phase 5 — Make reporting

The local implementation now provides `GET /api/reporting/management-summary`, protected by the
existing adapter key, plus inactive manual workflow `phase5-management-reporting`. It reports a
minimal daily Vancouver aggregate from independent Lead, Appointment, FollowUp, and current
RecoveryIncident reads. `report_key` is deterministic per business date. The endpoint has no
write or external-service behavior, and the workflow is separate from all customer-critical
automation.

Local verification passes 98 Python/SQLite/PostgreSQL tests, 28 browser/helper tests, and 43
workflow tests. The preserved n8n runtime contains the inactive workflow; existing workflow states
and retained executions are unchanged. The backend and n8n-container GET returned sanitized
aggregate output without changing durable counts. See `docs/phase-5-verification.md` and
`docs/phase-5-self-review.md`.

Live evidence uses stable report key `hvac-daily:2026-09-20`:

- `1522`: Make learned the real sanitized 16-field contract.
- `1614`: New Report added exactly one Google Sheets row and recorded the Data Store key;
  `generated_at=2026-09-20T19:49:18.570975Z`.
- `1627`: Existing Report found and updated the same row without duplication, but manual
  destination inspection exposed stale field mappings: Update a Row sourced old values from
  Search Rows, so green modules did not produce the intended business change.
- `1654`: after keeping Row number from Search Rows and mapping all 16 values from Webhooks,
  Existing Report refreshed the same row to
  `generated_at=2026-09-20T20:08:34.813643Z`; Row 3 remained empty.
- `1662`: a per-process unreachable-loopback Make override produced a visible reporting error
  while counts stayed at 47 Leads, 5 Appointments, 41 FollowUps, 36 CRMWriteJobs,
  38 CRMWriteAttempts, and 3 RecoveryIncidents.

Do not claim webhook acceptance alone proves destination success or universal exactly-once
delivery. Do not purchase, upgrade, expose PostgreSQL/Operations, or create a tunnel.

## Phase 6 — HighLevel fallback adapter and local simulator

`DevelopmentCRMProvider` still creates the authoritative local Lead/follow-up/audit state and is
the default. `HighLevelCRMProvider` composes that persistence with `HighLevelClient`, which sends
real HTTP to a separately deployed local simulator in `highlevel_simulator` mode. PostgreSQL and
the existing n8n recovery workflow retain jobs, leases, attempt limits, `Retry-After`, and
reconciliation ownership. `highlevel_live` fails closed.

The implemented contract subset is contact upsert/read/exact lookup and opportunity
search/create/update. Stable submission/correlation custom fields and pre-write duplicate lookup
prevent a foreign same-email/phone contact from being relabelled. Appointment and automatic stage
sync are omitted because a correct implementation needs a durable lifecycle-sync boundary and
verified calendar/account IDs; Phase 2 booking was not weakened by an external call.

Live-local evidence on 2026-09-21:

- Normal submission `e43a9631-3ba2-4acf-85cf-d3b7a1366f52` completed once locally and produced
  one contact and one opportunity. After rebuilding/resetting only the isolated simulator from
  final code, exact replay restored contact `sim_contact_e5a894882a2547d2` and opportunity
  `sim_opportunity_d533b972920844e0` without duplicating either logical effect.
- A one-shot 429 for submission `ff09e6a2-2fa4-4508-b166-a6c90520c42a` preserved
  `Retry-After: 3`; active recovery execution `2096` reconciled and completed attempt 2, producing
  exactly one logical contact and opportunity. Final exact-code replay restored contact
  `sim_contact_694623499a4b47ea` and opportunity `sim_opportunity_521c5a5676b84f05`.
- Simulator destination state held two contacts, two opportunities, zero appointments, 16
  sanitized API events, no serialized Authorization field, and fault mode Normal.
- Durable counts after the controlled evidence were 49 Leads, 5 Appointments, 43 FollowUps, 38
  CRMWriteJobs, 41 CRMWriteAttempts, and 3 RecoveryIncidents; no CRM fault run was active.
- The direct durable-intake route was used for the normal request to avoid an unnecessary NVIDIA
  call. Execution `2096` proves the preserved n8n recovery path through FastAPI, the adapter, and
  the external simulator service. No SMTP, booking, diagnostic injection, or real vendor call ran.

See `docs/phase-6-verification.md` and `docs/phase-6-self-review.md` for the official documentation
source record, contract details, tests, security review, and limitations. Never present the
simulator as a HighLevel sandbox or the adapter as live-verified.

## Phase 7 — presentation hardening and remaining work

Phase 7A improves only presentation clarity. It preserves the approved architecture, retained
execution history, recovery truth model, and read-only Operations surface. The deterministic
follow-up and appointment emails now use neutral furnace/air-conditioning service wording,
retain persisted details only, provide explicit local-development disclosure, and continue to
state that no technician, commercial service, or external calendar is reserved. Multipart
alternatives, escaping, CR/LF header safety, booking idempotency, and follow-up cancellation are
unchanged. The self-contained browser-first walkthrough is
`docs/interview-demo-runbook.md`; it includes the `272`/`276`/`283` distinction and the Phase 5
Make `1614`/`1627`/`1654` debugging story.

HighLevel live integration remains unverified. `DevelopmentCRMProvider` remains a distinct local
implementation; the Phase 6 adapter and simulator are an optional, explicitly non-live path.

The remaining Phase 7 work is screenshot selection/redaction, final README case-study polish,
browser rehearsal, and rebuilding the final interview PDF. Do not treat those deliverables as
complete.

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
- Include the Phase 5 Make replay mapping bug as a distinct debugging story: green modules but a
  stale business effect; manual `Generated At` inspection exposed Update Row values sourced from
  Search Rows; remapping fresh values from Webhooks let execution `1654` prove a real same-row
  refresh without duplication.
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
8. Show Make only to its recorded live verification extent; show the HighLevel Contract Simulator
   only as local contract-test evidence, never as a live vendor account.

The visual case study must continue to preserve these distinct evidence stories: the Phase 1
NVIDIA timeout/fallback, `283 -> 284` error-workflow chain, separate `720 -> 722` Retry-After
recovery, separate `728` lost-ack reconciliation, Phase 4 bad n8n deep-link bug/fix, and the Phase
5 Make stale-mapping diagnosis/correction. Do not merge them into a fictional sequence.

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
- `docs/phase-5-verification.md`
- `docs/phase-5-self-review.md`
- `docs/phase-6-verification.md`
- `docs/phase-6-self-review.md`
- `backend/app/providers/highlevel.py`
- `backend/simulator/main.py`
- `backend/app/api/operations.py`
- `backend/app/api/reporting.py`
- `backend/app/services/reporting_service.py`
- `frontend/operations.js`

If this handover conflicts with current code or a later approved phase document, inspect history and current runtime evidence rather than silently choosing the more convenient claim. Update this file to resolve the discrepancy before closing the phase.
