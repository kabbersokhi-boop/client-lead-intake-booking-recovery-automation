# Phase 5 self-review

## Findings and corrections

- **UTC-midnight shortcut — not present.** Both Vancouver local midnights are constructed with
  `ZoneInfo` and converted independently. Tests cover 23-hour and 25-hour dates.
- **Obsolete 2026 fall-transition assumption — reproduced in the first test draft.** The installed
  timezone rules reflect British Columbia's 2026 change, so 2026-11-01 is no longer a 25-hour
  Vancouver day. The regression now uses the real 2025 fallback while keeping 2026 spring-forward
  coverage. Production code remains timezone-rule-driven.
- **Window duration without date binding — reproduced in the first workflow draft.** The n8n
  validator initially accepted any 23–25 hour interval. It now proves both instants are the exact
  Vancouver midnights for the declared business date and next date.
- **Cross-realm object check — reproduced in executable workflow tests.** A prototype-identity
  check rejected a valid object across the Node VM boundary. The validator now uses a JSON-safe
  object check and retains exact-key/type validation.
- **String-shaped transport errors — hardened.** The Make result validator handles either an
  object or string error envelope and still separates timeout from other network failure.
- **Running-server CLI broker collision — reproduced without an outbound request.** The first
  `n8n execute` invocation stopped during bootstrap because port 5679 belonged to the existing
  task broker. It created no execution and could not contact Make. The installed configuration
  exposed the supported `N8N_RUNNERS_BROKER_PORT` override; a no-op diagnostic proved port 5680
  before the real workflow ran once as successful execution `1480`.
- **Green Make modules but stale destination values — reproduced live.** Execution `1627`
  selected the existing-report route, found the correct row, and ran Update a Row without adding
  a duplicate. Manual inspection showed `Generated At` was unchanged because every report column
  was mapped from Search Rows rather than the fresh Webhooks payload. Row number remains sourced
  from Search Rows; all 16 report values now come from Webhooks. Execution `1654` proved the same
  row genuinely refreshed while Row 3 remained empty.

## Adversarial review results

- Lead reporting uses `Lead.created_at`, not browser `client_received_at`.
- Independent table aggregates avoid Lead × FollowUp × Appointment × Incident multiplication.
- Start is inclusive and end is exclusive; PostgreSQL tests place rows immediately before, at,
  immediately before the end, and at the end.
- Furnace, air-conditioning, and other/unknown categories reconcile exactly to the Lead total.
- Appointments are booking events by `Appointment.created_at`; no conversion claim is made.
- Open incidents are explicitly a current state snapshot, not a daily incident count.
- The response allowlist cannot serialize customer PII, messages, AI summaries, provider data,
  payloads, tokens, headers, arbitrary errors, or the Make URL.
- The endpoint requires the existing adapter key and exposes no new browser secret or public
  database access.
- GET implementation imports no provider, lifecycle, recovery, email, n8n, or Make gateway and
  performs no commit, lock, mutation, or external call.
- `report_key` is stable for one logical date; only `generated_at` is expected to vary on repeated
  reads.
- The reporting export reads the Make destination only from protected runtime environment and
  contains no hard-coded Make capability URL or credential reference.
- Malformed backend success cannot reach the Make node. Non-2xx, timeout, network failure, and
  missing status become visible workflow failures.
- Make 2xx is called webhook acceptance only; destination success required separate Make-run and
  Sheet-inspection evidence and is now documented independently.
- No schedule exists, so importing the workflow cannot consume Make operations silently.
- Existing six workflow exports are unmodified and contain no Make reference.
- Retained executions and Phase 3 fault-control state remain preserved.
- Live reporting failure execution `1662` used a per-process unreachable loopback override, failed
  visibly, and left Lead, Appointment, FollowUp, CRMWriteJob, CRMWriteAttempt, and
  RecoveryIncident counts unchanged.

## Residual limitations

- Make scenario/Data Store mappings and Google Sheets OAuth configuration are external account
  state, so the repository can test its payload contract but cannot provision or version those
  mappings.
- The demonstrated Data Store plus Search/Update design is upsert-like for a stable report key; it
  is not a claim of transactional exactly-once delivery across Make and Google Sheets.
- Manual Sheet inspection remains necessary evidence of destination business effect. Execution
  `1627` proved that green module status alone can conceal stale mappings.
- The report is an aggregate snapshot for a synthetic reference demo. It does not provide revenue,
  conversion, technician, diagnosis, pricing, SLA, or production-client claims.
