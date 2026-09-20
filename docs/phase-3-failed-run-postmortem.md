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

## Correction-pass addendum

Review of commit `6359d7aea8c59dfbe9c2353820338358438baa35` found that the normal quota boundary could independently mutate attempt state after a caller had already opened an attempt. The retained historical execution `283` remains valid evidence of a real 429 and automatic error workflow `284`, but the bookkeeping ownership was unsafe for ordinary durable intake.

Attempt creation and settlement are now owned by one exact lease/attempt pair; the quota layer only accepts or rejects the HTTP call. A corrected at-write 429 created one attempt and one increment, retained `Retry-After: 69`, and recovered in execution `515` only after that minimum. The pass also corrected HTTP-envelope normalization, reconciliation failure semantics, business fingerprint verification, lock ordering, stale quota-row refresh, single-row claims, lease-bound permits, credential-wide claim pause, and manifest-level CLI assertions. Historical evidence was appended rather than rewritten.

## Canonical-payload and installed-envelope addendum

Review of `d6fe8ccb40d29e953d1a515b9f6d798a56ad4719` reproduced two further correctness gaps. Repeated immediate intake delivered the newest AI result instead of the already stored prepared payload, so a committed Lead could disagree with the durable job. Separately, n8n 2.39.8's ordinary `continueRegularOutput` error object retained status 429 but omitted response headers, causing recovery execution `703` to use the generic fallback instead of the real minimum.

Immediate creation now always validates and sends `CRMWriteJob.payload_json`; an existing persisted Lead is reconstructed as the canonical replay payload when a job is first admitted after creation. Created acknowledgements validate the canonical returned AI state, while replay/reconciliation permits a different valid persisted AI state only with matching submission, correlation, fingerprint, typed lifecycle, and follow-up invariants. The lookup and write HTTP nodes now use supported full-response/never-error options, retaining status and headers in an explicit boundary. Execution `720` received a real 429 at `Write CRM Lead`, retained `Retry-After: 20`, scheduled exactly 20 seconds later, and execution `722` created the lead under the same still-active quota window configuration.
