# Phase 6 self-review

## Review method

The implementation is reviewed as a fallback integration, not as evidence of live vendor access.
The review covers the provider seam, canonical payload and recovery ownership, HTTP mappings,
strict simulator behavior, UI wording, secret boundaries, replay, controlled failures, default
development behavior, Compose exposure, historical runtime evidence, and complete regressions.

## Material design findings

### DevelopmentCRMProvider owns persistence

Inspection confirmed that `DevelopmentCRMProvider` is not a transport-only adapter: it creates the
authoritative local Lead, schedules the initial follow-up, writes audit events, commits the
transaction, and supplies data used by booking and follow-up. Replacing or subclassing it as
though it were already a vendor client would have compromised PostgreSQL lifecycle truth.

The correction is composition. `HighLevelCRMProvider` reuses the existing local persistence
service and adds a separate HighLevel-specific HTTP projection. The development provider remains
truthful and independently tested.

### Local Lead existence is not external reconciliation

The original lookup endpoint read only PostgreSQL. In simulator mode that would have completed a
recovery job after a local Lead commit even if no external contact/opportunity existed. Provider
lookup is now mode-aware: development mode preserves the old local lookup; simulator mode verifies
the documented external contact and opportunity identities before returning the local result.

### Contact upsert is not a universal idempotency key

Official documentation ties contact upsert duplicate behavior to location settings and does not
document a general idempotency-key header. The adapter therefore uses stable custom-field identity,
exact lookup, conflict detection, and opportunity search. Documentation explicitly preserves the
remaining account-configuration/OAuth limitation.

The full-diff review found that calling upsert before checking stable identity could let vendor
duplicate matching select an unrelated same-email/phone contact and overwrite its application
identity fields. The adapter now performs exact lookup first, rejects a foreign identity before
any write, and only upserts when no duplicate exists. A regression test proves no upsert is sent
for that conflict.

A later falsification pass found that checking only email when both email and phone were supplied
still left a phone-only duplicate exposed to vendor matching. Reconciliation now queries both
documented exact identifiers, merges results by contact ID, and rejects a foreign match on either
identifier before any upsert. The simulator also rejects non-E.164 phone lookup and undocumented
opportunity statuses. A proposed rejection of documented `all` was discarded after
rechecking the current official create/update pages.

### Authentication failures must preserve the global pause

The normalized HighLevel authentication error initially blocked its own job but was not included
in the recovery service's existing cross-job credential-pause query. That could have allowed other
jobs to keep attempting with the same invalid token. The established pause now recognizes the
HighLevel authentication class, with a regression test proving a second pending job is not claimed.

### Booking synchronization would need durable ownership

Calling the simulator after the current booking transaction could produce a locally committed
appointment and an HTTP failure returned to n8n. Calling it inside the transaction would hold
database locks across an unreliable network and still could not make the two systems atomic.
Appointment and automatic stage synchronization were therefore omitted rather than implemented
unsafely. The simulator UI states this directly.

## Security review

- Simulator and backend browser ports bind only to `127.0.0.1`.
- PostgreSQL retains no host port; n8n remains loopback-bound in the preserved runtime.
- The simulator token and adapter token are environment-only; `.env.example` contains placeholders.
- API Events are produced from a positive field allowlist and never receive or serialize headers.
- Authorization, adapter keys, Make URLs, NVIDIA keys, and unrelated environment values are absent.
- All new test/demo identities are synthetic and simulator IDs use an explicit `sim_` prefix.
- Fault controls change only isolated simulator memory and cannot claim, requeue, or edit PostgreSQL jobs.
- Simulator reset cannot delete PostgreSQL, n8n, Mailpit, or historical execution evidence.
- `highlevel_live` fails closed and cannot silently send to a vendor endpoint.

## Adversarial verification checklist

- repeated intake and direct provider replay;
- stable application identity and conflicting payload;
- contact duplicate with foreign submission identity;
- missing contact/opportunity reconciliation;
- 401/403 classification and credential pause compatibility;
- 429 raw delay preservation;
- 500/network/timeout ambiguity;
- malformed 2xx response;
- strict extra-field rejection;
- one-shot fault reset, including timeout;
- event-log authorization redaction;
- stage update acknowledgement validation;
- unchanged default development behavior;
- Phase 1–5 and Phase 7A regression suite;
- Compose loopback exposure and tracked secret scan;
- retained n8n execution and PostgreSQL evidence preservation.

## Final review result

The complete diff review found and fixed three material issues. First, upsert originally ran before
stable duplicate reconciliation, so vendor duplicate matching could have overwritten application
identity on an unrelated contact; lookup now precedes every upsert. Second, an email-first lookup
did not cover a separate phone duplicate; every supplied exact identifier is now checked. Third,
the normalized HighLevel 401/403 class blocked its own job but did not activate the established
global credential pause; the pause now recognizes it. All corrections have dedicated regressions.

The deterministic verifier passes 121 Python, 28 frontend/helper, and 43 workflow tests (192
total), plus Ruff, simulator JavaScript syntax, JSON and shell checks, Compose validation, diff
checking, and tracked-content secret scanning. Live-local inspection confirmed two stable contacts
and two opportunities for two synthetic submissions, one successful replay without duplication,
one consumed 429 with `Retry-After: 3`, successful n8n recovery execution `2096`, zero external
appointments, Normal final fault state, and preserved historical execution evidence.
