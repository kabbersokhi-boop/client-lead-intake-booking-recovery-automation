# Phase 7 verification — durable HighLevel Opportunity lifecycle

## Deterministic evidence

The established disposable-PostgreSQL verifier passed after Phase 7 implementation:

- 187 Python/PostgreSQL tests, including lifecycle transactional outbox, coalescing rank,
  version advance while owned, lease reclaim, stale settlement, PostgreSQL remote-write guard,
  provider forward/no-op/ahead/missing/ambiguous/unmanaged/closed cases, failure classes,
  `Retry-After`, restart durability, protected worker API, and read-only Operations projection.
- 33 browser/helper tests, including queued 202 `blocked`/`needs_review` acceptance and safe
  stage Operations rendering.
- 47 n8n workflow tests, including the stage worker's sanitization, finite timeout, idle branch,
  and result validation. Ruff, JSON, JavaScript, shell, Compose, diff, and tracked-secret checks
  passed in the same verifier.

These simulator and deterministic tests are not live HighLevel fault evidence. The verifier
uses a disposable database and does not reset preserved runtime volumes or n8n executions.

## Live synthetic sequence — 2026-09-27 Asia/Kolkata

Before mutation, `scripts/phase7_live_preflight.py` verified `highlevel_live`, the official
HTTPS API host, the expected location, `HVAC Service Pipeline`, New Lead/Contacted/Appointment
Booked order and IDs, and all three custom identity fields. The backend reported a token present,
zero active CRM faults, and no local record for the fresh submission. A read-only remote Contact
lookup found no matching synthetic Contact. No test fault was armed.

Fresh synthetic submission: `4de0f2cf-309b-4a29-85dc-6cb7b1457e40`, correlation
`b9741654-dbd2-4de2-8331-06ba23fdd28e`, email
`synthetic-hvac-phase7-4de0f2cf309b@example.com`. The actual n8n intake webhook returned
HTTP 201 `created`, matching both identities and local `new_lead`. Read-only HighLevel lookup
found Contact `ZTHjrHMQ7v81jws6UVhr` and Opportunity `3zggkwx8E83xXwJj6UZ2`, linked in
the configured location and HVAC pipeline at New Lead.

The normal scheduled follow-up became due and sent through the existing local Mailpit boundary.
The Lead became `contacted`; the stage-sync row completed desired version 1 with one verified
attempt. Read-only HighLevel lookup found the same Contact and Opportunity in Contacted.

The actual n8n booking webhook returned HTTP 201 `created` for booking request
`7e72f987-a2c9-4840-813b-6cf3636b606e` at `2026-09-28T10:00` Vancouver business time.
The Lead became `appointment_booked` and the same desired row advanced to version 2. The active
stage-sync dispatch returned `completed`, desired `appointment_booked`, version 2, verified
remote `appointment_booked`. Read-only HighLevel lookup found the same Opportunity in Appointment
Booked, still linked to the same Contact and pipeline.

The exact intake replay returned HTTP 200 `replayed` with local `appointment_booked`; exact
booking replay returned HTTP 200 `replayed`. A post-replay read-only audit counted one local
Lead, one local Appointment, one matching live Contact, and one matching live Opportunity. It
verified the same Contact/Opportunity IDs, final Appointment Booked stage, completed sync row,
version 2, two attempts (`contacted` verified; `appointment_booked` verified), and no new stage
work. The Operations GET projection displayed the same desired/verified state and attempt history
without credentials or customer PII. No unrelated live Contact or Opportunity was mutated,
no records were deleted, and the native acknowledgement workflow remained Draft.

The first no-work stage dispatch surfaced an n8n webhook 500 (`No item to return was found`).
The export was corrected to always emit a claim item and return an explicit `idle` branch.
After reimport/publish/restart, an idle dispatch returned HTTP 200 with `state: idle`; the
original failed execution was not erased. The installed stage-sync workflow's ID, name, nodes,
connections, and settings matched the tracked sanitized export, and the runtime listed it as
active. The adjusted lead-intake queued-state export was likewise reimported and republished.

This proves one synthetic live sequence and exact replay, not universal exactly-once behavior,
production traffic, bidirectional CRM sync, or HighLevel Calendar reservation.
