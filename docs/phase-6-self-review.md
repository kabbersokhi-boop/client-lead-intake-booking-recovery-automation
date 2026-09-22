# Phase 6 self-review

## Review method

The implementation is reviewed as a fallback integration with a separately verified synthetic
live vendor projection; it is not evidence of production traffic or customer messaging.
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
documented exact identifiers independently. Every non-empty result must identify exactly one
contact with the expected submission/correlation fields, and every supplied identifier must
converge on the same contact ID. A split email/phone identity, foreign match, or ambiguous result
fails before upsert; one absent identifier plus one exact expected match safely reuses the known
contact without rewriting it. The simulator also rejects non-E.164 phone lookup and undocumented
opportunity statuses. A proposed rejection of documented `all` was discarded after rechecking the
current official create/update pages.

### Simulator mode must be structurally local

Mode naming alone did not prevent `highlevel_simulator` from accepting an arbitrary external base
URL. Settings now require plain HTTP with an explicit port on exact hosts
`highlevel-simulator`, `localhost`, `127.0.0.1`, or `[::1]`; userinfo, paths, queries, fragments,
deceptive host suffixes, numeric host aliases, HTTPS, and missing ports fail configuration.
`HighLevelClient` also disables environment proxy discovery. The existing Compose service URL
continues to work while a vendor URL cannot be selected in simulator mode.

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

### Opportunity filters can hide identity conflicts

Searching by expected contact and pipeline before inspecting the stable submission field could
hide the same submission identity on a wrong contact or pipeline and then create a second logical
opportunity. Reconciliation now scans bounded location-scoped pages, locates submission identity,
and only then validates contact and pipeline linkage. Missing response containers, malformed
pagination metadata, or absent/malformed custom-field structures fail as upstream contract errors
rather than being treated as safe absence.

### Provider exceptions must remain normal exceptions

`HighLevelProviderError` was a frozen dataclass. A real unexpected propagation path showed Python
context-manager traceback assignment could raise `FrozenInstanceError`, obscuring the actual
provider failure. The exception remains a dataclass for normalized fields but is no longer frozen.

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
- Simulator mode rejects non-local HTTP targets and ignores environment proxy settings.
- PostgreSQL retains no host port; n8n remains loopback-bound in the preserved runtime.
- The simulator token and adapter token are environment-only; `.env.example` contains placeholders.
- API Events are produced from a positive field allowlist and never receive or serialize request headers.
- API Events retain only the explicitly allowlisted `Retry-After` response value, never arbitrary headers.
- Authorization, adapter keys, Make URLs, NVIDIA keys, and unrelated environment values are absent.
- All new test/demo identities are synthetic and simulator IDs use an explicit `sim_` prefix.
- Fault controls change only isolated simulator memory and cannot claim, requeue, or edit PostgreSQL jobs.
- Simulator reset cannot delete PostgreSQL, n8n, Mailpit, or historical execution evidence.
- `highlevel_live` requires a distinct PIT, provisioned non-simulator IDs, and the exact official
  HTTPS host; it cannot silently use simulator credentials or an arbitrary vendor endpoint.

## Adversarial verification checklist

- repeated intake and direct provider replay;
- stable application identity and conflicting payload;
- contact duplicate with foreign submission identity;
- split email/phone identity and ambiguous identifier matches;
- deceptive/external simulator targets;
- missing contact/opportunity reconciliation;
- 401/403 classification and credential pause compatibility;
- 429 raw delay preservation;
- 500/network/timeout ambiguity;
- malformed 2xx response;
- malformed opportunity identity and pagination structures;
- strict extra-field rejection;
- one-shot fault reset, including timeout;
- event-log authorization redaction;
- stage update acknowledgement validation;
- unchanged default development behavior;
- Phase 1–5 and Phase 7A regression suite;
- Compose loopback exposure and tracked secret scan;
- retained n8n execution and PostgreSQL evidence preservation.

## Final review result

The earlier Phase 6 review fixed nine material issues: pre-upsert duplicate safety, checking both
identifiers, global credential pause, symmetric phone mapping, local-only completed replay,
contact/opportunity pagination, cross-page duplicate detection, durable runtime mode configuration,
and opportunity linkage acknowledgement.

This senior correction found six further material issues and one presentation ambiguity. Split
email/phone matches could still select the one contact carrying expected custom fields; identifier
results now must independently prove and converge on one identity. Simulator mode accepted an
arbitrary base URL; it is now restricted to exact local HTTP targets and ignores proxy settings.
Opportunity filtering could hide the same submission on a wrong contact/pipeline, and malformed
custom-field/search metadata could be mistaken for absence; bounded reconciliation now scans the
location first and fails malformed structures closed. A frozen provider exception could obscure a
real error with `FrozenInstanceError`; it is now a normal mutable exception object. The official
appointment-create page had moved to v3 while docs retained the obsolete version rationale; the
source record and omission rationale are now current. Finally, the README diagram placed the
optional adapter under booking/follow-up, implying lifecycle synchronization that does not exist;
the diagram and booking wording now identify it as intake/recovery projection only.

The current focused regression run passes 154 Python tests with 11 skipped, all three browser test
files, and all four workflow test files, plus changed-file Ruff, helper compilation, Compose
validation, diff checking, and a working-tree credential-pattern scan. The live verification
record now confirms seven synthetic Contact/Opportunity pairs, including one website/n8n/FastAPI/
PostgreSQL/live-HighLevel journey and an exact no-new-effect replay. Simulator-only controlled
fault behavior remains the evidence for 401, 429, 500, and timeout handling; no live account
fault was manufactured.

This focused local invocation is not the full exact-SHA CI total. Backend CI run `35759169287` for
the live-verification commit passed 165 Python tests, 32 browser/helper tests, and 43 workflow
tests: 240 passing checks. The local counts of three browser test files and four workflow test
files are file counts, not test counts.
