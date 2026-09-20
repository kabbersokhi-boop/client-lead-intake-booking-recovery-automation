# Phase 4 verification

## Scope

Phase 4 adds `http://localhost:18000/operations.html` plus `GET /api/operations/summary`, paged `GET /api/operations/jobs`, `GET /api/operations/jobs/{job_id}`, and paged `GET /api/operations/incidents`. The page reads the same durable records used by automation: an operator can locate an enquiry, inspect recorded attempts/retry timing, see a verified CRM lead where present, and follow correlation/execution references. Viewing it does not retry or change anything.

## Semantics and boundary

- Job and incident controls are drafts until their Apply button is pressed. Refresh and pagination use the immutable applied snapshot; applying resets to page one and removes old rows before the new context loads. Job selection belongs to the applied query generation, and list/detail successes outside the applied predicate fail closed.
- Summary has all six current job states (including zero) and a separate open-incident count, at a server-generated observation time. Completed is not labelled recovered.
- Lists filter and paginate server-side (25 default, maximum 100); jobs order by `created_at DESC, id DESC`.
- No completed Lead renders as `Pending CRM creation`; retry eligibility appears only for `retry_wait`; reconciliation failures and actual write attempts remain separate.
- This local synthetic-demo surface is not production authentication or health monitoring. It excludes adapter keys, payloads, leases, quota permits, provider bodies, and arbitrary metadata. n8n links require numeric references and a configured loopback editor base.

## Initial focused checks

```bash
.venv/bin/python -m pytest -q backend/tests/test_operations.py
.venv/bin/ruff check backend/app backend/tests/test_operations.py
node --check frontend/operations.js
npm run test:browser
```

The disposable-fixture suite covers zero-state aggregates, multiple attempts per job, filtering, stable pagination, invalid/unknown IDs, pending and completed jobs, reconciled attempts, resolved/unlinked incidents, numeric/unsafe execution references, redaction canaries, and GET read purity. The PostgreSQL integration test exercises the same projection directly against the disposable migrated database.

## Adversarial correction evidence

- The final independent review reproduced both remaining query-context hypotheses. Editing an unapplied lookup followed by Refresh previously mixed the draft list query with the old selection, and an old row could be clicked after Apply while a delayed replacement list was loading. The executable harness now covers draft edits followed by Refresh, Next, and Previous; both empty-list/detail completion orders; captured stale-row clicks; rapid Apply; rapid Refresh; selection state changes; predicate-violating success; malformed page shape; timeout; supersession; and unsafe text/links.
- Page responses allow legitimate temporal count/item differences but reject more items than `page_size`, invalid page metadata, negative counts, invalid elements, and elements outside the applied filter. An empty page beyond the now-valid last page restarts once at page one, including when total shrinks to zero.
- The independent review reproduced stale selected detail on Refresh/filter context changes, suppressed active timeouts, confusing `422` body rendering, and missing client-side success-shape/identity checks in the reviewed implementation.
- `frontend/test/operations.test.js` is now an executable Node DOM/fetch harness, not only a source scan. It drives the production script through controlled refresh/filter clicks and deferred fetches, checks screen text and request methods, and tests timeout versus supersession, late responses, malformed success, wrong job identity, safe URLs, and text escaping.
- Browser-safe response canaries run in disposable SQLite and PostgreSQL fixtures. They prove payload, lease/quota, adapter-key, authorization-header, provider-body, arbitrary reference, attempt, and incident values remain absent from summary/list/detail/incident responses; error paths do not read fixture values.
- The operations route remains ordinary read-only SQLAlchemy access. Its focused purity fixtures compare job/attempt/incident/Lead counts and persisted job state/timestamps before and after GETs; no external/write gateway is involved.
- The page has no polling. A failed current read is explicitly unavailable; a previously rendered summary/list/incident result is labelled stale with its old timestamp and pager controls are disabled. Selected detail is either freshly observed after Refresh or replaced by an unavailable state.
- The final corrective `./scripts/verify_phase3.sh` run passed 93 Python/SQLite/PostgreSQL tests, 27 browser/helper tests (including fourteen executable operations DOM/fetch tests), and 36 workflow tests. Ruff, JavaScript syntax, JSON/shell syntax, Compose validation, `git diff --check`, and the tracked-content secret scan passed. The verifier intentionally skipped live n8n/NVIDIA/Mailpit fault scenarios.
- The corrected local runtime returned HTTP 200 for `/operations.html`, summary, retained job detail, incidents, and the correlation trace. At `2026-09-20T15:26Z`, summary showed 36 completed jobs and 2 open incidents. Detail for job `e3f7d48d-64c3-4bd0-8d44-6d9d2d2c4e69` and correlation `236169e3-7c3e-4243-8a94-251ac4f9869a` showed completed/contacted Lead `ea6fb4d9-c966-4ac2-be26-30c3bb13d366`, failed `429` attempt/execution `283`, later completed attempt/execution `292`, and a linked resolved incident. A `BEGIN READ ONLY` PostgreSQL comparison returned the same counts and completed/2-attempt/resolved sequence. Durable aggregates before and after all four operations GETs were identical: 36 jobs with 38 total attempts, 3 incidents with 2 open, 38 attempt rows, and 47 Leads. Numeric links were `http://localhost:5678/execution/{id}` only.
- Final fault-control inspection found zero active scopes, zero delivery holds, and zero matching temporary Phase 3/fault/permit triggers. No fault endpoint, recovery worker, n8n import, NVIDIA call, SMTP send, or retained evidence mutation was used.

## Historical implementation and runtime evidence

- Before this corrective review, `./scripts/verify_phase3.sh` passed on implementation worktree `5fc70c6f41643de5620b0974dfcc226e2665c87d`: 92 Python/SQLite/PostgreSQL tests, 15 browser-helper/static frontend tests, and 36 workflow-code/structure tests; lint, Compose config, JSON/shell syntax, diff check, and tracked-content secret scan also passed.
- GitHub Actions `Backend CI` run `35514393356` passed for implementation SHA `5fc70c6f41643de5620b0974dfcc226e2665c87d`; its job completed lint, Python tests, browser tests, and workflow tests. The runner emitted only upstream Node 20 and future Ubuntu image deprecation notices.
- Rebuilt only the existing Compose backend, then received HTTP 200 from `/operations.html`, `/api/operations/summary`, and a retained job detail. The summary observed 36 completed jobs and 2 open incidents at `2026-09-20T13:43:17Z`.
- API job `e3f7d48d-64c3-4bd0-8d44-6d9d2d2c4e69`, correlation `236169e3-7c3e-4243-8a94-251ac4f9869a`, showed a retained failed HTTP 429 attempt in n8n execution `283`, then completed attempt `292`, a resolved linked incident, and a verified contacted Lead. Read-only PostgreSQL queries independently returned the same completed/2-attempt/resolved chain.
- No Phase 3 fault scope, recovery worker, n8n workflow, NVIDIA request, SMTP send, or Mailpit message was triggered for this phase.

No Chromium/Chrome/Playwright binary was available after checking the local toolchain, so no visual-browser automation was performed. Manual visual checklist: open `/operations.html` at desktop and narrow viewport; refresh; filter each state; paste a valid/invalid/unknown UUID; select two jobs quickly; inspect escaped error text and unlinked incidents; open the trace link and confirm the existing intake booking context is not changed; confirm the numeric n8n link opens only the local editor route.
