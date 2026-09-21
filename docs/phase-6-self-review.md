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

### Phone mapping must be symmetric

The application accepts common formatted phone input, while the documented exact lookup requires
E.164. The initial adapter compacted phone only for lookup but sent the original formatted value
to upsert, which could make a phone-only record unreconcilable in the simulator or vendor. The
same E.164 representation is now used for lookup and write. Non-E.164 numbers fail before any
external request, while the local durable Lead remains available for review/recovery.

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

### Completed replay must not reacquire upstream risk

The completed durable-intake branch initially called the full HighLevel delivery method again.
That was duplicate-safe but still allowed a new 429, timeout, or authentication failure to break
replay after the job had already confirmed its external effect. The provider contract now has an
explicit local replay operation. Completed jobs return their canonical PostgreSQL result without
network traffic; only unfinished jobs use external reconciliation and delivery.

### First-page absence is not global absence

Contact lookup and opportunity search originally requested their documented page maxima but did
not follow cursor/page-number pagination. A stable identity beyond page one could therefore have
been mistaken for absence and recreated. Reconciliation now follows up to fifty 20-contact pages
and ten 100-opportunity pages, rejects repeated/malformed cursors and cross-page duplicate
identities, and fails closed if either bounded search window is exhausted. Regressions place the
expected contact and opportunity on page two and a conflicting opportunity across page boundaries.

### Runtime mode must survive a clean Compose recreate

The final targeted rebuild exposed that the previous simulator mode/token had been inherited from
a shell session rather than persisted in protected local configuration. Compose correctly failed
safe to `development`, but that runtime could not support Phase 6 evidence. The final runtime now
stores an explicit simulator mode and fresh random token only in ignored `.env`; mode and token
presence were verified without revealing the token before all live-local checks were repeated.
Persisting the mode also exposed that pytest imported application settings from local `.env`;
test bootstrap now explicitly selects `development` before importing the application, keeping the
deterministic suite independent from protected runtime configuration.

## Security review

- Simulator and backend browser ports bind only to `127.0.0.1`.
- PostgreSQL retains no host port; n8n remains loopback-bound in the preserved runtime.
- The simulator token and adapter token are environment-only; `.env.example` contains placeholders.
- API Events are produced from a positive field allowlist and never receive or serialize request headers.
- API Events retain only the explicitly allowlisted `Retry-After` response value, never arbitrary headers.
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

The complete diff and runtime review found and fixed nine material issues. First, upsert originally
ran before
stable duplicate reconciliation, so vendor duplicate matching could have overwritten application
identity on an unrelated contact; lookup now precedes every upsert. Second, an email-first lookup
did not cover a separate phone duplicate; every supplied exact identifier is now checked. Third,
the normalized HighLevel 401/403 class blocked its own job but did not activate the established
global credential pause; the pause now recognizes it. Fourth, formatted phone values used
different lookup/write representations; the mapping is now symmetric E.164. Fifth, completed
intake replay reacquired upstream failure risk; it now returns canonical local state without
another HTTP call. Sixth, contact and opportunity reconciliation treated page-one absence as
global absence; both now follow bounded documented pagination. Seventh, opportunity pagination
could return the first stable match before detecting the same identity on a later page; it now
scans through termination and rejects cross-page duplicates. All corrections have dedicated
regressions. Eighth, simulator mode/token were session-only and a clean recreate fell back to
development; protected ignored configuration now makes the local runtime mode explicit, while
test bootstrap explicitly isolates deterministic tests from that runtime mode. Ninth, an
opportunity carrying the correct stable field could be accepted without independently confirming
its contact/location/pipeline linkage; reconciliation and stage acknowledgement now reject that
contradiction.

The deterministic verifier passes 126 Python, 28 frontend/helper, and 43 workflow tests (197
total), plus Ruff, simulator JavaScript syntax, JSON and shell checks, Compose validation, diff
checking, and tracked-content secret scanning. Live-local inspection confirmed two stable contacts
and two opportunities for two synthetic submissions, one completed replay with zero external
requests, one consumed 429 with `Retry-After: 3`, successful n8n recovery execution `2096`, zero external
appointments, Normal final fault state, and preserved historical execution evidence.
