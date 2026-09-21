# Interview demonstration runbook

Use this browser-first walkthrough after the local services are already running. It requires no
Codex prompt and no terminal commands during the interview. All names and records are synthetic.
Do not reactivate diagnostic fault injection. Keep the diagnostic workflow inactive.

## Before the interview

- Open the local lead form at `http://localhost:18000` and Mailpit at
  `http://localhost:18025` in separate tabs.
- Open n8n at `http://localhost:5678`, logged in. Keep the Operations tab ready at
  `http://localhost:18000/operations.html`.
- Leave the Phase 5 **Management Reporting - HVAC Snapshot** workflow inactive/manual.
  In Make, have the reporting scenario ready or listening as its existing UI configuration
  requires. Do not expose or show its private webhook URL.
- Use a fresh fictional email address and a future Vancouver business time. Do not use a
  retained evidence identity for the normal journey.

## Normal customer journey

1. **Lead form:** On the local lead form, choose **Use sample lead** or enter a fresh fictional
   furnace or air-conditioning request, then select **Submit synthetic request**. Point out that
   the page calls this a local demonstration and that AI enrichment has a safe fallback.
2. **Matching n8n intake execution:** Open the newest execution for **Lead Intake - Validation,
   AI Enrichment and CRM Persistence** in n8n. Show validation, optional NVIDIA
   enrichment/fallback, the development CRM boundary, and the acknowledgement. A fallback is
   still a successful lead-preserving intake; do not describe it as a lost lead.
3. **Persisted trace:** Return to the form and select **Inspect persisted trace**. Explain that
   the submission ID protects a browser retry, while the correlation ID joins the saved lifecycle
   trace. Show the saved request, follow-up status, and concise audit events.
4. **Booking:** Before the follow-up becomes due, enter a future `America/Vancouver` time and
   select **Save demonstration appointment**. The result records one synthetic appointment and
   cancels a still-pending follow-up. A repeat of the same booking request is safe; a different
   booking for the same lead is a controlled conflict.
5. **Appointment workflow:** In n8n, open the matching **Lifecycle - Appointment Booking and
   Confirmation** execution. Show the saved appointment transition followed by the local email
   boundary. It is not external capacity or technician dispatch.
6. **Mailpit confirmation:** In Mailpit, open the new appointment message. Show its saved
   appointment details and explicit local-development notice. Mailpit captures development SMTP;
   it is not production delivery.
7. **Operations View:** Return to Automation Operations, select **Refresh**, then find the
   fresh record by its exact correlation ID or job ID. The page is read-only: it cannot retry,
   resolve, requeue, send, or change records. Explain that job state, attempt history, incident
   history, and trace are independently observed durable projections.

## Retained failure and recovery evidence

Use historical executions after the normal journey. They are separate stories, not one chain.

1. In Operations, leave the incident filter at **All incidents** and open the linked resolved
   incident for execution `283`, or use its safe n8n link.
2. In n8n, show execution `283` in **Controlled CRM Rate-Limit Diagnostic**. It is the canonical
   controlled local rate-limit failure at **Diagnostic CRM Write Without Recovery**, not a real
   vendor outage or customer incident.
3. Open automatic Error Workflow execution `284` in **CRM Recovery Failure Recorder**. Explain
   that Error Workflow settings connect the diagnostic failure to this recorder; the recovery
   workflow is connected through shared durable jobs and API state, not a direct canvas wire.
4. Back in Operations, show the linked resolved incident and its completed job. Then identify
   recovery execution `292` as a later successful write; it remains text in Operations because
   attempt/job data does not durably store its workflow identity. Do not invent a link.
5. Optionally mention recovery execution `294` as another retained reconciliation result. The
   canonical batch reconciled to 12/12 unique leads without rewriting the failed execution.

### Meaning of the three diagnostic executions

- `272` is a validation/precondition rejection at **Validate Prepared Backlog**: the supplied
  value was not the bounded jobs array the diagnostic requires. It created no durable
  CRM-write job, attempt, or correlation link, so its open/unlinked incident has no truthful
  verified-completion resolution path.
- `276` is an earlier controlled rate-limit diagnostic at **Diagnostic CRM Write Without
  Recovery**. It likewise has no durable job, failed attempt, or correlation link, so it remains
  open/unlinked rather than being cosmetically dismissed.
- `283` is the canonical controlled failed execution used in the interview. Its failed durable
  attempt linked it to a job and correlation; verified completion in recovery execution `292`
  resolved the incident. `284` is its preserved automatic error-workflow record.

For additional technical depth, keep these distinct: `146` is NVIDIA timeout/fallback with a
preserved lead; `720` then `722` proves retained `Retry-After` recovery; `728` proves
lost-acknowledgement reconciliation without a duplicate CRM create.

## Optional Make reporting demonstration

This is a UI-only optional segment. Do not use Codex or a terminal during the interview.

1. In n8n, manually run **Management Reporting - HVAC Snapshot**. It reads the authenticated,
   aggregate-only reporting projection and submits a sanitized report to Make. It does not run
   as part of intake, booking, follow-up, recovery, or incident recording.
2. In Make, show the scenario execution and whether **New Report** or **Existing Report** was
   selected for the deterministic `report_key`. A successful webhook receipt alone is not proof
   of a Google Sheets write.
3. Open the configured Google Sheet and confirm the observed business effect. The retained story
   is: `1614` created the first row; `1627` showed green modules but a stale **Generated At**
   value because Update Row was mapped from Search Rows; `1654` kept the search row number but
   mapped all 16 fresh values from Webhooks, proving a same-row refresh with no duplicate.

## Honest scope statement

`DevelopmentCRMProvider` remains the authoritative local persistence implementation. Optional
simulator mode adds a separate HighLevel-specific contact/opportunity HTTP projection; live
HighLevel integration, automatic lifecycle-stage synchronization, and appointment synchronization
are not claimed. The synthetic appointment calendar does not reserve external service capacity,
and Mailpit does not prove production email delivery.
