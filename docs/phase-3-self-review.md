# Phase 3 self-review

## Scope and relationship

I reviewed the complete diff against `c11a6c13ab1885901aea81e93a748b19984e987c`; Git confirmed that commit is an ancestor and the initial worktree was clean at that exact SHA. This is a self-review, not an independent reviewer or second-model audit. Phase 4, Make, and vendor CRM work were not started.

## Findings and corrections

1. The original manifest used reserved `.test` domains rejected by the real backend. No job or lead had been created. I changed fictional addresses to `example.com` and added schema/uniqueness regression coverage for all twelve entries.
2. New n8n webhook exports lacked stable `webhookId` values. n8n published composite internal paths, so production URLs returned 404. I added stable IDs and a workflow regression assertion, reimported, restarted only n8n, and verified production webhooks.
3. The first diagnostic produced a real 429 but did not link it to durable attempt history. I added a safe execution-reference header; the rate boundary records the actual 429 and `Retry-After` before rejecting; incident creation resolves its job through that attempt. Execution `283`/`284` proves the corrected link.
4. The first booked example had already sent its follow-up and could only truthfully preserve `sent`. I selected Skyler while still pending and reran booking; execution `287` cancelled that follow-up and later replay preserved it.
5. Manual requeue retained history but initially could not pass the exhausted automatic budget. Forward migration `20260920_05` adds one-shot manual authorization; a regression proves exactly one fifth operator attempt is permitted and another failure returns to review.
6. Trace response list defaults were literal lists. Pydantic copied them, but `default_factory` removes mutable-default ambiguity.

## Adversarial evidence

Tests cover null/array/primitive acknowledgements, invalid replay lifecycle combinations, identity conflicts, duplicate admission, exact exhaustion, seconds/date/malformed/missing/long `Retry-After`, overlapping PostgreSQL workers, expired leases, stale tokens, committed-write/lost-ack reconciliation, incident deduplication, false resolution prevention, queued UI/booking exclusion, per-item workflow identity, and sanitized exports.

Live checks covered partial success, real 429 failure, automatic Error Trigger, same-ID recovery, already-booked preservation, replay without new business effects, new work over a quota window, worker restart with pending jobs, ordinary NVIDIA-enriched intake, booking confirmation, follow-up delivery, and scoped Mailpit inspection.

## Remaining limitations

The deterministic verifier does not call n8n, NVIDIA, or Mailpit and says so explicitly; live evidence is separately recorded. The simulator is not a real vendor quota. SMTP uncertainty remains operator-reviewed. Public trace routes are acceptable only because Compose binds the backend to loopback. Recovery handles lead writes only and deliberately does not become a general job platform.
