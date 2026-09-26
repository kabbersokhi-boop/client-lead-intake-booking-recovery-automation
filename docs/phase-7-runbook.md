# Phase 7 HighLevel stage-sync runbook

## What moves

Only new successful local lifecycle transitions in `highlevel_live` or
`highlevel_simulator` mode write desired stage sync work. An email follow-up that moves
`new_lead` to `contacted` creates desired `Contacted`; a committed booking advances the same
row to `Appointment Booked`. Existing historical local stages are not bulk backfilled. The
local transaction commits independently of HighLevel; n8n runs the external synchronization.

The active `phase7-highlevel-stage-sync` workflow checks once per minute and has a controlled
`POST /webhook/highlevel-stage-sync-dispatch` demonstration path. It claims one due row through
the adapter, then asks the adapter to reconcile and verify. An idle dispatch returns HTTP 200
with `state: idle`. The workflow export is sanitized; its `active: false` source flag is not
the deployed runtime state. The installed workflow is published in the local n8n instance.

## Inspect safely

Open `/operations.html` and use the HighLevel lifecycle sync section's exact submission-ID
lookup. `GET /api/operations/stage-sync?submission_id=<uuid>` exposes only safe desired state,
version, due time, attempts, last error class, and verified remote stage. It is read-only and
does not include tokens, raw provider bodies, or customer contact details.

`pending` is due work; `processing` has a lease; `retry_wait` is not eligible before `due_at`;
`completed` means exact identity and a managed remote stage at or beyond desired were read back;
`blocked` indicates credentials/permissions; `needs_review` requires human diagnosis. The
current desired version can advance while processing. An older attempt may be recorded as
`superseded` without completing the newer desired stage. The history is retained.

## Failure and recovery

- 429 uses a parseable `Retry-After` minimum; 5xx uses bounded exponential backoff and does
  not shorten a valid `Retry-After`; timeout/network uncertainty retries after reconciliation.
- 401/403 blocks the affected work and pauses further stage claims for the shared credential.
  Fix the PIT or permissions before an operator requeues the blocked job.
- 400/409/422, ambiguous or foreign identity, closed Opportunity, and unmanaged stage move to
  review. Missing Contact/Opportunity retries for a bounded period because initial creation may
  still be converging. Attempt exhaustion moves to review. Stage sync never creates a Contact
  or Opportunity.
- If the initial CRM-create job is still pending or retrying, stage sync defers without
  spending a stage-write attempt. It resumes after creation completes. A blocked or review
  state on that prerequisite is surfaced on stage sync rather than prompting a duplicate create.
- After the cause is corrected, the existing adapter-key-protected
  `POST /api/stage-sync/<job-id>/requeue` moves only `blocked` or `needs_review` work back to
  pending. It preserves attempts and resets the current generation's retry allowance. Do not
  call it repeatedly without correcting the cause.

Keep `CRM_ADAPTER_API_KEY`, the PIT, and live resource IDs in ignored runtime configuration.
Do not send them through the browser or put them in n8n exports. Never delete PostgreSQL/n8n
volumes or old executions to make a retry appear successful. No active synthetic CRM fault or
temporary database trigger should remain after a demonstration.

## Live synthetic demonstration

Run `scripts/phase7_live_preflight.py` from the repository root before a live test. It uses
read-only official-host calls to verify the configured location, HVAC Service Pipeline, three
stage IDs, and identity field IDs. Confirm live mode, token presence, no active CRM fault, and
a fresh synthetic submission/Contact identity before sending an intake. Use a fictional
`synthetic-hvac-…@example.com` email. The actual n8n intake webhook should create the Contact
and Opportunity in New Lead. Let the normal follow-up become due, then inspect the same
Opportunity in Contacted. Book a future Vancouver time through the booking workflow; let or
trigger the stage-sync dispatch and inspect the same Opportunity in Appointment Booked.

Replay the exact submission and booking request IDs, inspect the one stage-sync row and its
two attempts, then use read-only HighLevel lookup to confirm one Contact, one Opportunity,
the original Contact/Opportunity IDs, correct pipeline, and no stage regression. The native
HighLevel acknowledgement workflow stays Draft; do not publish it for this test. This does
not reserve a HighLevel Calendar slot or prove production email delivery.

The app serializes its own stage writes, including expired-lease overlap. It cannot serialize
edits made directly in HighLevel or by another integration between its final GET and PUT;
HighLevel's update endpoint has no compare-and-swap precondition in this implementation. Avoid
competing manual edits during the demonstration and review any unexpected remote state.
