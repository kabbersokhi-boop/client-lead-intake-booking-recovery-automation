# Phase 4 self-review

## Independent adversarial review

- **R1 — reproduced.** Refresh reloaded summary/list/incidents but not the selected detail, and a lookup could leave an unrelated selection visible. Filter context now invalidates selection and aborts its request; Refresh re-reads the selected job; successful detail renders its own server observation timestamp; identity/version/controller guards reject late responses.
- **R2 — reproduced.** The former shared `AbortError` path suppressed an active eight-second timeout and could render FastAPI's array-shaped `422.detail` as `[object Object]`. Requests now carry explicit superseded/timeout reasons. Supersession is quiet; an active timeout is unavailable/stale; pagers disable after a failed read. Validation/not-found/transport failures map to bounded operator text.
- **R3 — reproduced with synthetic malformed responses.** Missing summary fields defaulted to believable zeros and a plausible wrong-detail body could render. Small minimum validators now require all six non-negative counts, timezone-bearing observation timestamps, bounded page shape, supported states, arrays, and exact requested detail identity. Invalid success retains only clearly labelled prior data or shows unavailable.
- **R4 — reproduced.** The previous frontend checks were source assertions, not interactions. The Node DOM/fetch harness now executes `operations.js` and covers refresh, filter/unknown lookup invalidation, delayed selection races, timeout and late-after-abort behavior, `422`, malformed success, wrong identity, text rendering, unsafe execution URLs, and GET-only requests.

## Additional findings fixed

- Persisted error/reference fields were allowlisted by schema but copied verbatim. A targeted recorded-text screen now suppresses credential-like/header/provider-body/JSON/control-character values while retaining useful bounded evidence; disposable SQLite and PostgreSQL canaries cover payload, lease, quota, adapter-key, authorization, provider-body, attempt, and incident fields across every operations response.
- Frontend execution links now independently require numeric references and the exact `http://localhost|127.0.0.1:5678/execution/{id}` route, even if a malformed backend body claims a URL.
- Timezone-less timestamps and out-of-range pages are rejected; pages beyond a changed result set restart at page one rather than presenting an impossible page.
- Backend editor-link construction now rejects non-root configured paths and invalid ports. The existing lease UTC normalization and durable incident linkage checks remain preserved.

## Read-only and scope review

- Protected `RecoveryJobResponse` remains unchanged. Operations handlers use ordinary SQLAlchemy reads only: no mutation services, `FOR UPDATE`, commits, background tasks, external gateways, or worker calls.
- Counts group jobs directly, preventing attempt/incident multiplication. Lists filter/page in SQL; resolved and genuinely unlinked incidents remain inspectable. Pending work without a Lead remains `Pending CRM creation`; completed is never called recovered.
- Dynamic text uses `textContent`. The trace link only carries correlation as a query parameter; intake still requires explicit trace loading and does not change accepted booking identity.

## Residual limits

Separate read requests can observe later worker progress, so every successful dynamic section labels its own observation time and no global atomic snapshot is claimed. Zero open incidents is not n8n/NVIDIA/SMTP health. This is loopback synthetic-demo access, not production authentication. Styled visual-browser testing remains a manual check if a real browser remains unavailable; deterministic DOM behavior is not presented as visual proof. Phase 1–3 workflows, evidence, and retained executions remain unchanged.
