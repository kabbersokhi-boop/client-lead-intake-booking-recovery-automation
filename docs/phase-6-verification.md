# Phase 6 fallback verification — HighLevel adapter and local contract simulator

## Status and truth boundary

The HighLevel-specific adapter is implemented and contract-tested over real HTTP against a local
simulator based on the documented API subset used by this project. The simulator is test
infrastructure, uses unmistakably local IDs, and is not a HighLevel sandbox, account, product, or
UI clone.

PostgreSQL remains the authoritative local reliability and audit ledger. n8n still owns the
customer-critical orchestration and the existing recovery workflow still owns retries, leases,
attempt budgets, `Retry-After`, and reconciliation. The simulator owns only its isolated external
test representation and sanitized API-event history.

Live HighLevel authentication, account-specific mappings, responses, limits, and side effects
were not verified because API access was unavailable. `highlevel_live` fails closed with an
explicit configuration error.

## Architecture selected

```text
Browser -> n8n -> FastAPI durable intake/recovery boundary -> PostgreSQL local truth
                         |
                         +-> HighLevelCRMProvider -> HighLevelClient -> real HTTP
                                                        |
                                                        v
                                           HighLevel Contract Simulator
```

`DevelopmentCRMProvider` remains the original local CRM persistence implementation. In
`highlevel_simulator` mode, `HighLevelCRMProvider` composes that local persistence service with a
separate documented HTTP projection. This preserves the existing Lead, follow-up, lifecycle,
audit, and recovery records while making the external simulator a real network boundary.

The provider returns the existing n8n-facing acknowledgement shape. Recovery completion still
links to the local `Lead` UUID because that row is the authoritative application result; local
simulator contact and opportunity IDs never replace application correlation truth.

## Provider modes

| Mode | Meaning |
| --- | --- |
| `development` | Default. Existing `DevelopmentCRMProvider`; no HighLevel claim or external HTTP effect. |
| `highlevel_simulator` | Local Lead persistence plus the HighLevel-specific HTTP adapter targeting an allowlisted local simulator URL only. |
| `highlevel_live` | Intentionally unavailable until credentials/access and real account mappings are reviewed and verified. |

Simulator URL: `http://localhost:18080`. The browser surface and backend remain loopback-bound.
The adapter target and local simulator token come from ignored/protected environment
configuration. No usable token is committed. Configuration accepts plain HTTP only on exact hosts
`highlevel-simulator`, `localhost`, `127.0.0.1`, or `[::1]`, requires an explicit port, rejects
userinfo/path/query/fragment forms, and disables environment proxy use. Simulator mode therefore
cannot be repointed to an arbitrary external or live-vendor URL.

## Official HighLevel source record

Reviewed 2026-09-22. Only official HighLevel documentation was used for API-contract facts.

| Official page | URL | Contract detail relied upon |
| --- | --- | --- |
| Private Integrations | https://marketplace.gohighlevel.com/docs/Authorization/PrivateIntegrationsToken/ | Private Integration Tokens are fixed scoped bearer tokens; tokens belong in the `Authorization` header and must be protected. |
| OAuth 2.0 | https://marketplace.gohighlevel.com/docs/Authorization/OAuth2.0/ | Authorization-code flow, sub-account installation, access/refresh-token behavior, and minimum-scope guidance. |
| Scopes | https://marketplace.gohighlevel.com/docs/Authorization/Scopes/index.html | `contacts.readonly`, `contacts.write`, `opportunities.readonly`, `opportunities.write`, and calendar event scopes. |
| Upsert Contact | https://marketplace.gohighlevel.com/docs/ghl/contacts/upsert-contact/ | `POST /contacts/upsert`, required `Version: v3`, `locationId`, contact/custom-field shape, duplicate-setting behavior, `createNewIfDuplicateAllowed=false`, and `{new, contact, traceId}` response. |
| Lookup Contact By Email Or Phone | https://marketplace.gohighlevel.com/docs/ghl/contacts/lookup-contact/index.html | `GET /contacts/lookup`, exact location-scoped email or E.164 phone lookup, max-20 cursor pagination, `Version: v3`, and the explicit OAuth-only channel limitation. |
| Get Contact | https://marketplace.gohighlevel.com/docs/ghl/contacts/get-contact/ | `GET /contacts/:contactId`, `Version: v3`, and `{contact}` response wrapper. |
| Search Opportunity | https://marketplace.gohighlevel.com/docs/ghl/opportunities/search-opportunity | `GET /opportunities/search`, contact/location/pipeline filters, pagination, v3 response/error shapes, bearer methods, and sub-account token requirements. |
| Create Opportunity | https://marketplace.gohighlevel.com/docs/ghl/opportunities/create-opportunity/ | `POST /opportunities/`, required location/pipeline/contact/name/status values, optional stage/custom fields, `Version: v3`, and 201 `{opportunity}` response. |
| Update Opportunity | https://marketplace.gohighlevel.com/docs/ghl/opportunities/update-opportunity/ | `PUT /opportunities/:id`, stage/status update shape, `Version: v3`, and `{opportunity}` response. |
| Create appointment | https://marketplace.gohighlevel.com/docs/ghl/calendars/create-appointment/ | Current `POST /calendars/events/appointments` contract, required calendar/location/contact/start-time fields, `Version: v3`, and response shape; used only to assess mapping readiness, not implemented. |
| Get Appointment | https://marketplace.gohighlevel.com/docs/ghl/calendars/get-appointment/ | Current documented appointment read path and v3 response wrapper; used only to assess mapping readiness. |
| Rate Limits | https://marketplace.gohighlevel.com/docs/other/rate-limits/index.html | OAuth public-API burst/daily limits and documented `X-RateLimit-*` response headers. The page does not document `Retry-After` as a universal HighLevel guarantee. |
| Changelog | https://marketplace.gohighlevel.com/docs/Changelog/ | Records `GET /contacts/lookup` as added on 2026-08-12; used to identify the new reconciliation contract and avoid relying on the removed legacy contact-list API. |

No reviewed official source established a general idempotency-key header or universal exactly-once
semantic. The implementation does not invent one. Contact upsert is treated as a documented
business operation whose duplicate behavior depends on location configuration, not as universal
transport idempotency.

## Implemented documented subset

The adapter and simulator implement only:

- `POST /contacts/upsert`;
- `GET /contacts/:contactId`;
- `GET /contacts/lookup`;
- `GET /opportunities/search`;
- `POST /opportunities/`;
- `PUT /opportunities/:id` for tested stage mapping readiness.

Every contract request requires bearer authentication and `Version: v3`. Simulator responses use
`sim_contact_*`, `sim_opportunity_*`, `sim_trace_*`, and `sim_req_*` identifiers. The simulator
validates the narrow request schema with extra fields forbidden.

## Contact and opportunity mapping

Contact upsert maps full name, optional normalized email/phone, configured `locationId`, a bounded
source label, `createNewIfDuplicateAllowed=false`, and configured custom fields for stable
`submission_id` and `correlation_id`. The adapter reads the contact back by ID and rejects an
acknowledgement that does not preserve those identities.

Because the documented exact phone lookup requires E.164, a supplied plus-prefixed formatted
number is compacted to E.164 for both lookup and upsert. A number that cannot be represented as
E.164 is rejected before any external request rather than written in a form that cannot be safely
reconciled. This is a project safety constraint, not a claim that contact upsert universally
requires E.164.

The adapter maps one open HVAC opportunity to the configured pipeline and `new_lead` stage, linked
to the external contact. A configured opportunity custom field carries `submission_id`. The
implemented stage table is:

| Local application stage | Configured simulator stage |
| --- | --- |
| `new_lead` | `sim_stage_new_lead` |
| `contacted` | `sim_stage_contacted` |
| `appointment_booked` | `sim_stage_appointment_booked` |

The update mapping is contract-tested, but automatic lifecycle-stage synchronization is not wired
into booking/follow-up. Doing so correctly requires a durable lifecycle outbox/job boundary; an
unreliable HTTP call was not inserted inside the approved booking or email transactions.

## Appointment decision

Appointment create/read was deliberately omitted. Current official documentation now exposes
`POST /calendars/events/appointments` and `GET /calendars/events/appointments/:eventId` under
`Version: v3`. The project still has no verified live calendar, user, service, availability, or
meeting-location IDs. More importantly, a post-booking external write needs durable ownership to
avoid reporting a failed booking after the local transaction already committed; performing it
inside the booking transaction would hold database locks across an unreliable network without
making the two systems atomic. Phase 2 booking, follow-up cancellation, and Mailpit confirmation
remain unchanged and authoritative for this reference build.

The simulator UI includes an Appointments page that explicitly says synchronization is not
implemented. It never fabricates an external appointment.

## Identity, replay, and reconciliation

The local job retains the first canonical prepared payload. HighLevel contact lookup evaluates
every supplied documented identifier independently: exact case-insensitive email and documented
E.164 phone. Every non-empty identifier result must contain exactly one contact carrying the
expected submission and correlation fields, and all non-empty results must resolve to the same
contact ID. A foreign match, multiple matches for one identifier, or split email/phone contacts is
an identity conflict before upsert. One identifier may be absent when the other resolves exactly
to the expected contact; that reuses the known contact without rewriting it.

Contact lookup follows the documented opaque cursor in bounded 20-record pages and rejects a
repeated or malformed cursor. Opportunity reconciliation scans the location rather than filtering
first by contact or pipeline, then finds the stable submission custom field and validates its
contact/location/pipeline linkage. This prevents a same-submission opportunity on the wrong
contact or pipeline from being hidden by filters and recreated. It follows documented page-number
pagination in bounded 100-record pages, validates required response containers and identity data,
detects duplicates across pages, and refuses to infer absence beyond 1,000 location opportunities.
Recovery performs this read path before another uncertain write. If contact and opportunity
already exist, the local Lead result completes the durable job; if either effect is safely absent,
the existing recovery workflow may authorize another write.

Once a durable job is completed, an unchanged intake replay returns the canonical local result
without recontacting the upstream system. A fresh upstream 429 or timeout therefore cannot turn a
previously confirmed customer replay into a new failure. Explicit recovery reconciliation remains
the path for jobs whose external outcome is still uncertain.

This is at-least-once delivery/retries with idempotent business effects and explicit
reconciliation. It is not a universal exactly-once claim. The exact contact lookup endpoint is
officially OAuth-only, so live use of this strategy requires OAuth access or a separately reviewed
supported reconciliation design.

External contact/opportunity IDs are not persisted in the application database in this fallback;
the adapter reconciles from stable custom fields on each unfinished job. That is sufficient for
the implemented create/recovery path but makes reconciliation bounded and more expensive. Future
automatic lifecycle synchronization would likely need durable external-ID mapping plus its own
durable lifecycle-sync ownership.

## Local commit and external consistency

The composed `DevelopmentCRMService` commits the Lead, initial follow-up, and audit state before
the external HTTP projection runs. If contact upsert fails, the durable recovery job retries after
reconciliation. If contact succeeds and opportunity fails, the next reconciliation reuses the
contact and creates only the missing opportunity. If either acknowledgement is lost, lookup runs
before another write. If both external effects succeed but local recovery completion fails, a
later reconciliation can confirm them and finish the job without another create.

This means local follow-up can become due while external projection is still retrying. That is an
explicit eventual-consistency limitation of the fallback, not hidden atomicity. The established
Phase 3 job owns retry/lease/attempt state; the adapter has no second retry loop. A race between
the final duplicate lookup and vendor upsert also cannot be made universally atomic because the
official contract does not establish an idempotency key. Live verification must reassess that
residual against actual location duplicate settings.

## Error translation and faults

The adapter normalizes authentication/permission failures, request/mapping validation, rate
limiting, retryable upstream failures, network/timeout ambiguity, identity conflicts, unexpected
statuses, and malformed success responses. It does not retry internally. Existing durable
recovery classification remains primary; a valid simulator `Retry-After` is passed through to the
existing bounded scheduling logic.

The simulator supports visible one-shot modes: Normal, 401 Unauthorized, 429 Rate Limited with a
bounded 1–30 second `Retry-After`, 500 Server Error, and Timeout. A non-normal fault resets before
its response is emitted, so even a client timeout cannot leave the fault silently armed.

API Events records method, documented path, sanitized query/body/response, status, simulator
request ID, timestamp, intentionally propagated submission reference, and only the allowlisted
`Retry-After` response value. Logging is allowlist based. Authorization, adapter keys, arbitrary
headers, environment data, and private URLs are not stored or returned.

## Deterministic coverage

Focused coverage proves request/header mapping, strict response parsing, exact external identity,
split-identifier refusal, local-only target validation, location-wide opportunity identity,
one external contact/opportunity after replay, conflicting-payload refusal before an external
rewrite, opportunity stage mapping, 401, 429 and `Retry-After`, 500, timeout, malformed success,
strict simulator validation, event redaction, one-shot reset, provider-mode truth, the unchanged
development provider, and durable recovery ownership around a simulated 429.

The complete verifier runs 153 Python tests, 28 frontend/helper tests, and 43 workflow tests: 224
tests total. It also runs Ruff across the application, simulator, tests, and demo helper; checks
simulator JavaScript syntax; parses tracked workflow/fixture JSON; checks shell syntax; validates
Docker Compose; runs `git diff --check`; and scans tracked content for secret patterns.

## Controlled live-local evidence

The final Phase 6 runtime used the separate healthy simulator container over Docker HTTP. The
normal synthetic submission `e43a9631-3ba2-4acf-85cf-d3b7a1366f52` completed with local Lead
`e0a8c654-3ca7-40da-90b6-731a1b37c92f` and exactly one logical external contact/opportunity.
After rebuilding and resetting only the isolated simulator from final code, the authenticated CRM
boundary reprojected the stored canonical synthetic payload as contact
`sim_contact_5559fcbdeb164d50` and opportunity `sim_opportunity_b5563a8d11fa45cf`. A subsequent
completed durable replay returned the same local Lead with HTTP 200 while the simulator event
count remained exactly 12, proving that confirmed replay added no upstream request.

A separate request `ff09e6a2-2fa4-4508-b166-a6c90520c42a` consumed one synthetic 429 with
`Retry-After: 3`. Its first attempt failed with `highlevel_rate_limited`; the fault reset to
Normal. Existing active n8n recovery execution `2096` performed reconciliation, authorized the
second write, and completed it with HTTP 200. Destination inspection found exactly contact
and opportunity effects for that stable submission identity. Final-code reprojection after the
isolated reset produced contact `sim_contact_32d25c73c42243cd` and opportunity
`sim_opportunity_6975db0213da4348`. A final adapter lookup consumed another one-shot 429 with
`Retry-After: 3`, recorded simulator request `sim_req_5f28d86ff0c64946`, reset automatically,
and the following reconciliation lookup returned 200.

Pre-correction inspected simulator state: two contacts, two opportunities, zero appointments, 19
events, Normal fault mode, and no serialized Authorization field. PostgreSQL counts were 49 Leads, 5
Appointments, 43 FollowUps, 38 CRMWriteJobs, 41 CRMWriteAttempts, and 3 RecoveryIncidents, with no
active CRM fault. Backend, simulator, PostgreSQL, Mailpit, and the preserved n8n instance remained
healthy.

The final targeted rebuild initially exposed that simulator mode/token existed only in the prior
shell environment, so Compose correctly fell back to `development`. This was rejected as invalid
Phase 6 evidence. A new random token and explicit `CRM_PROVIDER_MODE=highlevel_simulator` were
stored only in ignored local `.env`, the two services were recreated, mode/token presence was
verified without printing the token, and every final runtime check above was rerun. Pytest
bootstrap explicitly forces `development` before application import so deterministic verification
does not inherit protected simulator configuration from `.env`. After the final linkage hardening,
the rebuilt backend reconciled the stored submission with HTTP 200 and completed replay again
added zero requests (19 events before and after).

The 2026-09-22 senior correction rebuilt only backend and simulator from the corrected code, then
reprojected the same two stored canonical synthetic payloads without changing PostgreSQL or n8n.
Destination inspection found two contacts (`sim_contact_18bb2e0cb3684146` and
`sim_contact_94eafe650a5940a8`), two opportunities (`sim_opportunity_29403ff56d324167` and
`sim_opportunity_f60b5b103d754e45`), and zero appointments. An authenticated completed replay
returned HTTP 200 with event count unchanged at 12. A simulator-only one-shot 429 recorded request
`sim_req_021296d4a0374e7a` with `Retry-After: 3`; the next lookup returned 200 and fault state reset
to Normal. Final state held 14 sanitized events, the current documentation review date, and none of
the configured simulator token, adapter key, or `Authorization` label. Durable counts remained 49
Leads, 5 Appointments, 43 FollowUps, 38 CRMWriteJobs, 41 CRMWriteAttempts, and 3 RecoveryIncidents,
with no active CRM fault. No n8n, NVIDIA, Make, SMTP, booking, or historical diagnostic execution
was triggered during this correction check.

The preserved n8n state remained unchanged: intake, appointment booking, follow-up dispatch,
recovery dispatch, and recovery error recording stayed active; controlled diagnostic and
management reporting stayed inactive. Retained executions `146`, `283`, `284`, `292`, `294`,
`720`, `722`, `728`, `1522`, `1614`, `1627`, `1654`, and `1662` all remained present with their
original success/error states. New recovery execution `2096` is separate Phase 6 local-simulator
evidence.

The normal evidence used the authenticated n8n-facing durable-intake API directly rather than the
website/n8n intake workflow, specifically to avoid spending or making an unrelated NVIDIA call.
Execution `2096` supplies the n8n-to-FastAPI-to-adapter-to-simulator proof for recovery. No SMTP,
booking, diagnostic fault injection, real HighLevel, Make, or NVIDIA call was triggered.

## Verified locally

- HighLevel-specific mapping and parsing;
- real HTTP between the backend container and separate simulator container;
- contact and opportunity destination effects actually inspected in simulator state;
- strict headers/auth/version validation;
- one-shot fault behavior and redacted API events;
- replay/reconciliation with one logical contact and opportunity;
- existing PostgreSQL recovery ownership and `Retry-After` behavior;
- unchanged default `DevelopmentCRMProvider` path.

## Not verified

- live HighLevel authentication or token scopes;
- real account/location, pipeline, stage, custom-field, user, service, or calendar IDs;
- live contact duplicate-setting behavior;
- live response bodies or error envelopes;
- live rate-limit behavior beyond the official documentation record;
- live HighLevel contact, opportunity, or appointment side effects;
- automatic external lifecycle or appointment synchronization.

## Interview wording

“I couldn't obtain live HighLevel API credentials in time, so I did not mock a live integration
and claim it was finished. I implemented the HighLevel-specific adapter against the current
documented API contract and test it over real HTTP against this local contract simulator.
PostgreSQL still owns reliability and audit state. If access becomes available, the remaining work
is live OAuth/vendor authentication, account-specific IDs and mappings, and verification against
the actual account.”

“The development provider is the existing local CRM implementation used by the reference build.
It is not HighLevel. The HighLevel adapter is a separate external integration path.”

“The surrounding intake and recovery architecture should not need redesign. Live deployment still
requires supported OAuth or another reviewed reconciliation path, real location/pipeline/custom-
field IDs, live response verification, and separate durable ownership for any future lifecycle or
calendar synchronization.”
