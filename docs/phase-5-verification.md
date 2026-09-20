# Phase 5 verification

## Status

The Phase 5 reporting boundary, live Make routing, Google Sheets destination, same-key update,
and safe failure-isolation gates are verified for the synthetic local reference demo. The Make
webhook URL is intentionally absent from Git, tests, documentation, exported workflows, and
recorded command output.

Webhook acceptance and destination success were verified separately. The successful module path
alone was not treated as proof of business effect; manual inspection of the destination exposed
and then verified the correction of a real Update Row mapping defect.

## Business purpose and isolation

The report answers: “What happened in the synthetic HVAC business on this business date, and
is anything currently requiring attention?” It reads committed PostgreSQL state through a
narrow FastAPI projection. A separate n8n workflow validates that projection and makes the
outbound HTTPS request to Make from private runtime configuration.

```text
PostgreSQL durable truth
  -> authenticated FastAPI reporting GET
  -> separate manual n8n reporting workflow
  -> Make Custom Webhook
  -> Make Data Store routing by report_key
  -> Google Sheets management destination
```

Make is absent from intake, persistence, booking, follow-up, recovery, and incident recording.
The reporting API performs SQL reads only. The reporting workflow contains only one internal GET
and one outbound Make POST; it has no customer-critical API path and no Schedule Trigger.

## Reporting API contract

Endpoint: `GET /api/reporting/management-summary`

- The endpoint reuses the existing `X-CRM-Adapter-Key` n8n-to-FastAPI boundary. No second secret
  mechanism and no browser credential were added.
- `business_date=YYYY-MM-DD` is optional. Omission selects the date containing `generated_at` in
  `America/Vancouver`.
- `report_key` is deterministic: `hvac-daily:YYYY-MM-DD`.
- The response model is an explicit aggregate allowlist. It contains no customer identity,
  messages, AI summary, provider metadata, recovery payload, lease/quota data, credentials,
  authorization headers, or webhook URL.
- No migration or reporting table was added.

The contract contains only:

```text
report_version
report_type
report_key
business_date
business_timezone
window_start_utc
window_end_utc
generated_at
leads_received
furnace_requests
air_conditioning_requests
other_or_unknown_requests
needs_review
appointments_booked
follow_ups_sent
open_recovery_incidents_at_generated_at
```

## Exact metric semantics

Every event-window metric uses the inclusive/exclusive predicate
`window_start_utc <= timestamp < window_end_utc`.

| Metric | Durable source and meaning |
| --- | --- |
| `leads_received` | `Lead.created_at`; server-persisted Lead creation during the selected Vancouver business date. Browser-supplied `client_received_at` is not used. |
| `furnace_requests` | Same Lead population where `Lead.service_type == furnace_service`. |
| `air_conditioning_requests` | Same Lead population where `Lead.service_type == air_conditioning_service`. |
| `other_or_unknown_requests` | Every other value, including null/missing enrichment, within the same Lead population. The three categories reconcile to `leads_received`. |
| `needs_review` | Same Lead population where durable `Lead.needs_review` is true. |
| `appointments_booked` | `Appointment.created_at` during the window with durable `status == booked`. This is a booking-event count, not a same-day lead conversion rate. |
| `follow_ups_sent` | `FollowUp.sent_at` during the window with durable `status == sent`; pending and cancelled rows do not count. |
| `open_recovery_incidents_at_generated_at` | Current `RecoveryIncident.state == open` snapshot without a business-day creation filter. It is not labelled as incidents created that day. |

Lead, appointment, follow-up, and incident aggregates are independent queries. No relational
cross-product can multiply counts.

## Timezone and DST

Python `zoneinfo.ZoneInfo("America/Vancouver")` derives each local midnight independently and
converts both instants to UTC. The implementation never adds a fixed 24 hours to a UTC start.

Tests prove the 2026-03-08 spring transition is a 23-hour UTC window and the 2025-11-02 fall
transition is a 25-hour UTC window. The installed timezone database reflects British Columbia's
2026 rule change, so the historical 2025 fall date is the correct 25-hour regression fixture;
the production calculation remains driven by `America/Vancouver` rules rather than a hard-coded
offset.

## n8n reporting workflow

- ID: `phase5-management-reporting`
- Name: `Management Reporting - HVAC Snapshot`
- Export: `n8n/management-reporting.json`
- Trigger: manual only
- Runtime status: imported, inactive, and executed manually through the CLI only
- Nodes: manual trigger -> fetch summary -> validate exact contract -> send to Make -> validate
  HTTP result
- Internal GET timeout: `CRM_CONTROL_TIMEOUT_MS`, default 3 seconds
- Make timeout: `MAKE_REPORTING_TIMEOUT_MS`, default 10 seconds
- Retry behavior: none; a visible failed report is preferred to a new recovery subsystem

Validation requires the exact top-level field set, version/type, deterministic key, real business
date, `America/Vancouver`, timezone-bearing timestamps, matching Vancouver midnight boundaries,
a 23–25 hour window, safe non-negative integer counts, and reconciled lead categories. An extra
PII field or malformed result throws before the Make node.

The Make HTTP node uses only `$env.MAKE_REPORTING_WEBHOOK_URL`. It preserves full HTTP status and
accepts a text response body because a Make Custom Webhook need not return JSON. The final node
distinguishes 2xx webhook acceptance, non-2xx, timeout, network failure, and missing status. A 2xx
result is labelled only `make_webhook_accepted`; it does not claim Google Sheets success.

## Deterministic verification

`./scripts/verify_phase3.sh` remains the established complete verifier and discovers the new tests.
The final verification gate passed:

- 98 Python/SQLite/PostgreSQL tests;
- 28 browser/helper tests;
- 43 workflow-code/structure tests;
- Ruff;
- JavaScript workflow and browser execution;
- JSON parsing and shell syntax;
- Compose validation;
- `git diff --check`;
- tracked-content secret scanning.

Focused coverage includes zero state, non-empty aggregates, inclusive/exclusive edges, 23/25-hour
DST dates, classification reconciliation, review/booked/sent/open counts, deterministic identity,
repeated GET stability except `generated_at`, PII/secret/internal-field absence, GET read purity,
PostgreSQL aggregation, exact n8n contract validation, malformed-report rejection, runtime-only
Make URL, non-2xx/timeout/network failure, and absence of customer-critical write paths.

## Local runtime evidence

The rebuilt existing backend returned HTTP 200 for the authenticated reporting endpoint and HTTP
401 without the adapter key. The request from inside the preserved n8n container returned this
sanitized business-date result:

```json
{
  "report_key": "hvac-daily:2026-09-20",
  "business_date": "2026-09-20",
  "leads_received": 0,
  "furnace_requests": 0,
  "air_conditioning_requests": 0,
  "other_or_unknown_requests": 0,
  "needs_review": 0,
  "appointments_booked": 0,
  "follow_ups_sent": 0,
  "open_recovery_incidents_at_generated_at": 2
}
```

This zero-event daily window is the truthful current result; the two open incidents are a current
snapshot. Before and after the n8n-container GET, durable counts remained exactly 47 Leads, 5
Appointments, 41 FollowUps, 36 CRMWriteJobs, 38 CRMWriteAttempts, and 3 RecoveryIncidents.

The imported runtime workflow matched the sanitized export by canonical SHA-256 and
remained inactive. Existing intake, booking, follow-up, recovery, and error workflows retained
their prior active/inactive states. Executions `146`, `283`, `284`, `292`, `294`, `720`, `722`,
and `728` remain present with their original workflow IDs and statuses. Final inspection found
zero active fault scopes, zero held deliveries, and zero temporary Phase 3/fault/permit triggers.

No NVIDIA request, SMTP message, Mailpit message, recovery claim, Phase 3 fault injection, or
customer-state mutation was used for the reporting verification.

## Live Make and Google Sheets evidence

After the user configured the capability URL in ignored mode-600 runtime configuration, the
existing n8n container was recreated with the same `n8nio/n8n:latest` image reference,
`n8n_data:/home/node/.n8n` volume, loopback `127.0.0.1:5678` binding, Compose network, and
`unless-stopped` restart policy. Existing workflows and retained executions remained present.

The first CLI invocation did not load or execute the workflow because its task broker attempted
to reuse the running server's port 5679. It created no execution row and could not contact Make.
Installed n8n configuration identified the supported `N8N_RUNNERS_BROKER_PORT` override. A
nonexistent-workflow diagnostic on port 5680 proved the alternate CLI bootstrap without running
any node.

The live history is intentionally preserved as four distinct stories:

### Execution 1522 — schema learning

- Sent the real sanitized 16-field management contract to the private Make Custom Webhook.
- Make accepted the request with HTTP 200 and learned the webhook data structure.
- This proved webhook receipt only; it did not prove a management-destination write.

### Execution 1614 — first destination write

- Sent `report_key=hvac-daily:2026-09-20` with
  `generated_at=2026-09-20T19:49:18.570975Z`.
- Make's Data Store existence check selected the New Report fallback.
- Google Sheets Add a Row ran once and Data Store Add/replace recorded the report key once.
- The user opened `HVAC Management Reporting` / `Daily Reports` and verified exactly one data row.

### Execution 1627 — green modules, stale business effect

- Replayed the same logical report key. Data Store Exists, Existing Report, Search Rows, and
  Update a Row executed; New Report and Add a Row did not execute, so no duplicate was created.
- Manual inspection showed that `Generated At` did not change. Update a Row was incorrectly
  sourcing all report columns from Search Rows, so it read the old row and wrote the old values
  back into that same row.
- This execution is not represented as successful update verification. It demonstrates why green
  automation modules are insufficient without checking the intended downstream business state.

### Execution 1654 — corrected same-row refresh

- Kept Row number sourced from Search Rows but remapped all 16 report values from the fresh
  Webhooks payload.
- Replayed `report_key=hvac-daily:2026-09-20` with
  `generated_at=2026-09-20T20:08:34.813643Z`; Make accepted it with HTTP 200.
- Existing Report, Search Rows, and Update a Row each ran once. New Report, Add a Row, and the
  New Report Data Store write did not run.
- The user verified Row 3 remained empty, exactly one logical row existed, and Row 2's
  `Generated At` changed from the execution 1614 value to the execution 1654 value.

This proves an upsert-like downstream design for the demonstrated report key. It does not claim
exactly-once delivery or that HTTP 200 alone proves Sheets success.

## Safe reporting-failure isolation

Execution `1662` ran the same inactive reporting workflow through the n8n CLI with only that
process's Make URL overridden to an unreachable loopback endpoint and a one-second timeout. The
real private Make URL, scenario, persistent n8n volume, and customer workflows were untouched.

- The reporting execution ended visibly with `status=error` and CLI exit code 1.
- The workflow surfaced a sanitized Make network-failure error.
- Before and after counts were identical: 47 Leads, 5 Appointments, 41 FollowUps,
  36 CRMWriteJobs, 38 CRMWriteAttempts, and 3 RecoveryIncidents.
- No customer-critical workflow was invoked. The test created only the expected failed reporting
  execution record in n8n.

This proves the tested failure mode can lose a management report without losing a lead, blocking
booking/follow-up, or mutating CRM recovery truth.

## Residual limitations

- The Make scenario and Google Sheet are account-managed external configuration, not exported or
  reproducibly provisioned by this repository.
- The destination behavior is verified for one synthetic logical report key, not a universal
  exactly-once guarantee under every Make/Google failure mode.
- A 2xx n8n receipt means the Make webhook accepted the payload; destination success still
  requires Make execution and Sheet inspection evidence.
- Scheduling remains intentionally absent/inactive to avoid silently consuming Make operations.
