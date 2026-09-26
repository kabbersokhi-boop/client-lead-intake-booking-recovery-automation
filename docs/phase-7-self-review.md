# Phase 7 self-review

## Adversarial questions and corrections

An independent Luna High read-only review checked local-worker races, durable transaction
ownership, provider identity, lease expiry, retry timing, and live limits. I reproduced and
corrected its confirmed findings:

- A stage update initially forced `status: open` without checking a Won/Lost/Abandoned remote
  Opportunity. The provider now reads the exact Opportunity immediately before a write and
  holds non-open status for review. A closed-status regression proves there is no PUT.
- The stage worker initially ignored a valid 5xx `Retry-After`. It now takes the later of
  bounded backoff and that provider minimum; a 503/120-second regression checks this.
- An advancing desired version initially cleared the authentication error class while leaving
  the row blocked, which could release the shared credential pause. Blocked/review evidence is
  now retained until protected requeue, and a two-job regression checks the pause.
- An idle n8n dispatch returned HTTP 500 because no item reached its webhook response. The
  workflow now emits a safe `idle` result and returns HTTP 200 when there is no due work.
- The browser accepted only three durable queued 202 states although the backend can return
  `blocked` or `needs_review`. Both browser and n8n intake validation now accept all five
  genuine accepted states, with regressions. The identity and absence-of-CRM-ID checks remain.
- A slow initial CRM-create retry could otherwise consume stage-write attempts before an
  Opportunity exists. Stage sync now defers behind unfinished create work without spending an
  attempt, and surfaces blocked/review prerequisites. A regression covers eventual release.

Local follow-up and booking transitions update the desired row before their existing commit.
The provider call happens later. One row per Lead, rank/version coalescing, guarded claims,
lease-token settlement, and a PostgreSQL advisory lock prevent stale local Contacted work from
permanently completing or racing a newer local Appointment Booked write. PostgreSQL concurrency
tests force expiry while a Contacted write is delayed and verify later convergence. A missing or
ambiguous Opportunity never grants permission to create another one. Malformed 2xx, unknown
stage, closed status, and identity mismatch do not mark work completed. No raw provider body,
PIT, lease token, or arbitrary payload enters Operations.

## Remaining limits

HighLevel does not supply a conditional stage update precondition in the adapter's documented
PUT path. A person or another integration can edit the same Opportunity between our final GET
and PUT. The local advisory lock serializes this app's workers only. The provider reduces that
window with a fresh point read and refuses closed/unmanaged states observed there, but cannot
promise monotonicity against a simultaneous external writer. This limitation is documented in
the README and runbook, not hidden as an exactly-once claim.

Live Contact reconciliation remains bounded location-wide pagination. Large accounts may need
a more selective PIT-compatible identity lookup and a re-evaluated lease/timeout budget. The
new outbox covers lifecycle transitions after deployment; it does not bulk-edit historical
HighLevel Opportunities. The native acknowledgement workflow stays Draft. No OAuth, GHL Calendar
reservation, production SMTP, WhatsApp, Meta source, bidirectional sync, or generic queue was
added. Local email acceptance remains separate from its database sent marker.
