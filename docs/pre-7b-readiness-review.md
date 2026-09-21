# Pre-7B readiness review

Review date: 2026-09-22

## Scope and starting point

This pass reviewed the completed Phase 1–6 and Phase 7A implementation as one interview-facing
automation product. It started from clean local and remote commit
`ffa877ffd88adaba53695a03e0a3ac68cb4010fd` (`Harden Phase 6 identity and simulator boundaries`).
Exact-SHA Backend CI run `35645604249` was successful before edits.

The purpose was presentation and factual coherence, not another architecture phase. No database
schema, migration, recovery lease, retry model, booking transaction, follow-up concurrency model,
n8n workflow topology, Make mapping, reporting contract, or provider-auth design was changed.

## Surfaces reviewed

- Main service-request page: empty form, populated saved result, booking panel/result, and persisted
  booked trace.
- Read-only Operations: summary, filters, jobs table, selected-detail structure, incidents, and
  safe n8n links.
- HighLevel Contract Simulator: Overview, Contacts, Opportunities/Pipeline, Appointments, API
  Events including an expanded event, and Fault Testing.
- Mailpit: retained HTML follow-up and historical appointment messages; plain-text and current
  HTML generation remain covered by lifecycle tests.
- FastAPI operations/reporting schemas and services, lifecycle email generation, all seven n8n
  exports, Make/Sheets evidence, architecture, handover, verification records, and interview
  runbook.

## Material findings and corrections

- The intake page led with CRM identifiers and raw states. It now presents request status, service,
  location, follow-up, appointment, and notification outcomes first; IDs and raw values remain in
  expandable technical details.
- The old linear flow implied email followed every intake. The compact diagram now branches after
  persistence into follow-up or locally saved appointment paths.
- Booking wording could be read as commercial capacity. It now says the demonstration persists
  local PostgreSQL state, cancels a pending follow-up when booking wins, and does not reserve a
  technician or update an external calendar.
- Trace output led with raw lifecycle codes. It now explains the customer journey with readable
  event labels while preserving raw event types, timestamps, durable IDs, and raw JSON.
- Operations showed `Open incidents: 2` without enough context. The summary now separates linked
  durable work from unlinked records. Executions `272` and `276` remain open and are identified as
  retained unlinked diagnostic records, not unresolved customer requests; `283` remains the linked,
  resolved controlled failure.
- Operations raw states remain unchanged but now have readable labels. UUIDs remain selectable and
  wrapped; tables keep explicit keyboard-focusable horizontal scrolling where technical columns
  require it.
- Appointment email subject/body and HTML heading disagreed. New messages consistently use
  **Saved appointment details** and retain deterministic, escaped, persisted-data-only copy with
  explicit development disclosure. Historical Mailpit messages were not rewritten.
- Simulator API Events required path inference. Events now label contact lookup, upsert,
  verification, opportunity search, create, and update while expanded details show only sanitized
  request IDs, trace references, Retry-After, query, request, and response fields.
- The simulator now states `LOCAL TEST ENVIRONMENT`, `NOT LIVE HIGHLEVEL`, and
  `NOT A HIGHLEVEL SANDBOX` as three prominent assertions. Its empty Appointments view explains
  the deliberate synchronization boundary instead of looking unfinished.
- A narrow simulator tab strip clipped neighboring labels after selection. At 390 px it now uses a
  two-column menu; desktop navigation is unchanged.
- Missing browser favicons created harmless but distracting 404 console noise. All three local
  browser surfaces now suppress the implicit favicon request without adding an asset.
- README/runbook grouping now maps the exact retained workflow names into customer journey,
  reliability/debugging, and management-reporting groups without renaming workflow IDs or exports.

## Cross-phase verdict

- **Phase 1:** no material implementation defect. The narrative remains optional AI, safe fallback,
  execution `146` exceeding the former approximately 10-second budget, the 18-second correction,
  bounded output, and later successful enrichment in `149`.
- **Phase 2:** no material durability defect. Booking, follow-up cancellation, replay, local
  `America/Vancouver` semantics, Mailpit, and SMTP/database uncertainty remain accurately bounded.
- **Phase 3:** no material recovery defect. The distinct `283 -> 284`, `283 -> 292`, `720 -> 722`,
  and `728` stories remain separate; `272` and `276` remain historical diagnostic artifacts.
- **Phase 4:** no material read-boundary defect. Operations remains GET-only, browser-to-FastAPI,
  and non-mutating; its incident presentation was clarified.
- **Phase 5:** no material reporting defect. The `1614` creation, `1627` green-but-stale mapping,
  and `1654` corrected same-row refresh story remains intact. Sheets remains downstream reporting,
  not a CRM.
- **Phase 6:** no material adapter/reconciliation defect. The local simulator presentation and API
  event teaching surface were improved without changing identity, HTTP contract, or recovery logic.
- **Phase 7A:** no material regression. This pass aligned the remaining HTML heading and extended
  the business-first presentation consistently across intake, trace, Operations, and simulator.

## Browser and responsive verification

Headless Chromium inspected live local pages at 1440 × 1000 and 390 × 844. The review covered the
main page, populated result, demonstration booking result, persisted booked trace, Operations,
simulator Overview/Contacts/Appointments/API Events/Fault Testing at both widths, simulator
Opportunities at desktop, an expanded API event, and retained Mailpit follow-up/appointment HTML.
No page-level horizontal overflow remained. Narrow Operations intentionally retains a scrollable
technical table; the page itself does not overflow. The mobile simulator menu no longer clips.

The populated main-page result and booking state were rendered from existing persisted synthetic
trace values in the browser only. No submission or booking endpoint was called. The retained
appointment email predates the current safer template and remains historical evidence; current
plain-text/HTML output was verified in source and tests rather than sent again.

## Deterministic verification

`./scripts/verify_phase3.sh` passed:

- 153 Python tests with SQLite and disposable PostgreSQL coverage;
- 32 frontend/helper tests;
- 43 workflow-code/structure tests;
- 228 tests total;
- Ruff;
- simulator JavaScript syntax;
- JSON parsing;
- shell syntax;
- Compose validation;
- `git diff --check`;
- tracked-content secret scan.

The final release commit still requires exact-SHA GitHub Actions success after push.

## Runtime verification

- FastAPI, PostgreSQL, Mailpit, and the HighLevel Contract Simulator were running locally; n8n
  `2.39.8` was healthy separately.
- PostgreSQL retained 49 leads, 5 appointments, 43 follow-ups, 38 CRM-write jobs, 41 attempts, and
  3 incidents after the review.
- Operations reported 38 completed jobs, zero unfinished jobs, 2 open incidents, 0 linked open
  incidents, and 2 unlinked open incidents.
- Simulator state remained 2 contacts, 2 opportunities, 0 appointments, 14 sanitized events, and
  normal fault mode. Static UI assets were updated without recreating the container so this
  in-memory evidence was preserved.
- Active project workflows remained intake, appointment booking, follow-up dispatch, recovery
  dispatch, and failure recorder. The controlled diagnostic and management-reporting workflows
  remained inactive.
- Retained execution references `146`, `149`, `272`, `276`, `283`, `284`, `292`, `294`, `720`,
  `722`, `728`, `1522`, `1614`, `1627`, `1654`, `1662`, and `2096` remained retained.
- No new synthetic business record was created. NVIDIA, Make, SMTP submission, booking, diagnostic,
  recovery, and reporting workflows were not invoked by this pass.

## Security review

- Protected `.env` permissions remained owner-only; only variable names, never values, were
  inspected.
- No authorization header, simulator token, adapter key, NVIDIA key, Make webhook, or environment
  value was added to browser output, documentation, tests, or tracked files.
- Simulator event rendering remains allowlisted and HTML-escaped. Authorization and arbitrary raw
  headers remain absent.
- All inspected data was synthetic. Temporary browser screenshots remained under `/tmp` and were
  not committed.

## Known limitations deliberately retained

- Live HighLevel authentication, account IDs, pipeline/calendar IDs, live responses, vendor rate
  limits, and production-scale opportunity reconciliation are not verified.
- Automatic HighLevel lifecycle-stage synchronization, appointment synchronization, and persistent
  external-ID mapping are not implemented.
- Exact contact lookup retains the documented OAuth limitation.
- Mailpit is a development sink. SMTP acceptance and PostgreSQL commit remain separate effects;
  universal exactly-once email delivery is not claimed.
- Local booking does not reserve technician capacity or an external calendar.
- Make/Google Sheets is non-customer-critical management reporting. A green Make execution alone
  does not prove the Sheet business effect.

## Explicit Phase 7B deferrals

- Manager-facing **HVAC Operations Dashboard** formatting, summary cards, service-demand view, and
  trends; the `Daily Reports` tab remains the machine-readable Make destination.
- Final visual README/case-study rewrite and final architecture diagram.
- Screenshot selection, redaction, captions, happy path, failure/debug stories, Make story,
  simulator story, reliability section, and limitations section.
- Final real-browser rehearsal, timed 10–15 minute click path, fallback route, interview teaching,
  challenge questions, and concise Q&A.
- Final interview PDF, only after browser, screenshots, README, and demo path are frozen.

## Readiness decision

The implemented local system is technically coherent, business-readable, inspectable in depth, and
truthful about every external boundary. After exact-final-SHA CI succeeds, remaining work is
presentation packaging rather than core system repair: **READY TO START PHASE 7B**.
