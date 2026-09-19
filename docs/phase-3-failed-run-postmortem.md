# Phase 3 failed-run postmortem

## Symptom

During a controlled local fault-injection test, n8n execution `283` failed at `Diagnostic CRM Write Without Recovery` after the scoped development CRM returned HTTP 429. Ten of twelve synthetic submissions existed in CRM; two remained missing. Existing records were valid and were not removed.

## Evidence

The fixed-window simulator was configured for five scoped POST writes per ten seconds. It was disabled by default and affected only registered manifest IDs. n8n retained execution `283` with `error` status and `NodeApiError`. Durable attempt rows linked to execution `283` record status 429, the actual `Retry-After` interpretation of 10 seconds, and timestamps. Error Trigger execution `284` created a deduplicated incident linked through that attempt.

## Cause and impact

The diagnostic path deliberately sent a prepared backlog without shared pacing or recovery. Successful writes before rejection remained committed; unfinished work had no automatic progress on that unsafe path. The synthetic business impact was incomplete CRM intake, not duplicate creation or customer-state reset.

## Changes

Validated CRM payloads are stored before delivery in unique recovery jobs. Atomic leases prevent overlapping ownership; stable-identity lookup reconciles uncertain outcomes; a shared database quota reservation paces workers; attempts and incidents remain durable; bounded classification honors `Retry-After`; exhaustion retains work for review. Browser `202 queued` is distinct from CRM creation.

## Verification

Recovery executions `289`–`297`, including write attempts `292`/`294`, reconciled the same manifest to 12/12 unique leads. Same-batch replay left lead, follow-up, and appointment counts unchanged. Skyler's booked pipeline, cancelled follow-up, appointment, and confirmation remained intact. Fresh six-item work crossed the same fixed window and completed 6/6.

## Residual risks

SMTP acceptance and the later database commit remain separate effects; this queue does not replay uncertain mail. The simulator represents one local fixed-window quota, not a real CRM vendor contract. Operator review remains required for business failures, credentials, malformed acknowledgements that reconciliation cannot resolve, and exhausted work.
