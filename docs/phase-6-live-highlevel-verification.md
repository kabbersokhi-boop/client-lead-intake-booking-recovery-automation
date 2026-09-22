# Phase 6 live HighLevel verification

## Status

`highlevel_live` is implemented as an optional external CRM projection. PostgreSQL remains the
application and reliability truth. Phase 3 continues to provide at-least-once delivery/retry with
idempotent business effects and explicit reconciliation.

The live adapter uses a sub-account Private Integration Token only from
`HIGHLEVEL_LIVE_TOKEN`, pins the API target to `https://services.leadconnectorhq.com`, and never
logs authorization headers. It does not use `/contacts/lookup`: HighLevel documents that endpoint
as OAuth-only. Instead it uses the PIT-supported bounded location contact list plus exact local
email/phone comparison and the application identity custom fields. A foreign, split, or ambiguous
identity fails closed before a write.

## Provisioned scope

The idempotent `scripts/setup_highlevel_live.py` command provisions or validates only:

- `HVAC Service Pipeline`, with `New Lead`, `Contacted`, and `Appointment Booked` in that order;
- Contact `HVAC Integration Submission ID` and `HVAC Integration Correlation ID` fields;
- Opportunity `HVAC Integration Opportunity Submission ID` field.

It refuses ambiguous duplicate resource names and refuses destructive replacement of an existing
pipeline whose stages do not exactly match the contract. It prints only non-secret resource IDs;
it never writes `.env` files or prints the token.

`scripts/reconcile_highlevel_live_synthetics.py` is a separate guarded recovery utility for an
interrupted verification run. Its default is read-only; `--apply` is required to create a missing
Opportunity. The selector requires both Contact identity fields and the dedicated
`synthetic-hvac-…@example.com` namespace, so it cannot select an unrelated sample Contact.

## Current evidence and boundary

Live API inspection confirmed the above pipeline and field provisioning against the configured
sub-account and exposed real response details that the adapter now validates: contact list uses
the `2021-07-28` endpoint version and an empty `meta.nextPage` terminator; opportunity search may
omit `aggregations`; opportunity custom-field values are returned as `fieldValueString`.

After an interrupted synthetic verification was repaired with the guarded utility, a read-only
audit found six eligible synthetic Contacts and six complete matching Opportunity effects. Every
submission identity had exactly one correctly linked Opportunity; duplicate-identity conflicts
were zero. The account Contact count was 11 both immediately before repair and after verification,
so no Contact was added. A replay audit locally prohibited all non-GET methods and reconciled all
six effects with zero upstream writes. The repair utility can only call the Opportunity create
path after its Contact/identity checks; it does not update Contacts, delete records, or target
unrelated sample data.

The deterministic suite passes with no live token. Local simulator fault tests remain the only
fault harness for 401, 429, 500, and timeout behavior. No outbound messaging, appointment sync,
calendar sync, funnel, billing, or lifecycle-stage synchronization was added.

## Controlled n8n durable-intake evidence

One fresh `synthetic-hvac-…@example.com` identity was submitted through the existing local
website webhook route, n8n, FastAPI/PostgreSQL durable boundary, and the live adapter. n8n
returned `created`; the durable trace recorded one completed CRM-write job, one attempt, no
incident, and the expected application lead ID. A direct read-only HighLevel audit then found
seven eligible synthetic Contacts and seven correctly linked Opportunities (the prior six plus
this end-to-end record), all in the configured location, HVAC Service Pipeline, and New Lead
stage, with zero duplicate submission-identity conflicts.

The exact same webhook business identity was replayed once. n8n returned `replayed`; the durable
job remained completed with `attempt_count: 1`. A post-replay HighLevel audit still found seven
complete effects, zero missing Opportunities, and zero duplicate identity conflicts. This is
evidence of at-least-once delivery/retry with idempotent business effects and explicit
reconciliation, not a claim of universal exactly-once delivery.
