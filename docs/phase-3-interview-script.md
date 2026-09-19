# Phase 3 interview script

“This was a controlled local fault-injection test, not a claimed vendor outage. I prepared twelve synthetic enquiries through the real intake webhook, including live NVIDIA enrichment or explicit fallback, while holding only that registered batch before CRM delivery.

I configured the development CRM for five POST writes per fixed ten-second window. The deliberately unsafe diagnostic workflow sent the backlog without pacing. n8n execution 283 genuinely failed on HTTP 429, execution 284 automatically recorded the incident, and the database showed ten leads present and two missing—partial completion, not duplicates.

The fix persists pending work before attempting the CRM. Each job keeps stable submission and correlation IDs, validated payload, attempt budget, due time, and safe failure history. A worker claims with a lease, reconciles by submission ID, obtains shared quota permission, and only then writes. `Retry-After` sets the earliest next time. Idempotency makes the same operation safe to replay; reconciliation proves whether it exists.

After restarting the worker, recovery completed the same IDs to twelve unique leads. I had booked Skyler before recovery, and replay preserved the appointment and cancelled follow-up. Replaying the whole batch created no new leads, follow-ups, or appointments. A fresh six-item run crossed the quota window: five writes occurred in the first window and the sixth was durably deferred.

The configured five-per-ten number is only the local simulator. Correlation IDs, durable pending work, bounded leases, `Retry-After`, idempotency, and reconciliation are transferable concepts, but this does not claim a real vendor limit or exactly-once email.”
