# Phase 4 verification

## Scope

Phase 4 adds `http://localhost:18000/operations.html` plus `GET /api/operations/summary`, paged `GET /api/operations/jobs`, `GET /api/operations/jobs/{job_id}`, and paged `GET /api/operations/incidents`. The page reads the same durable records used by automation: an operator can locate an enquiry, inspect recorded attempts/retry timing, see a verified CRM lead where present, and follow correlation/execution references. Viewing it does not retry or change anything.

## Semantics and boundary

- Job and incident controls are drafts until their Apply button is pressed. Refresh and pagination use the immutable applied snapshot; applying resets to page one and removes old rows before the new context loads. Job selection belongs to the applied query generation, and list/detail successes outside the applied predicate fail closed.
- Summary has all six current job states (including zero) and a separate open-incident count, at a server-generated observation time. Completed is not labelled recovered.
- Lists filter and paginate server-side (25 default, maximum 100); jobs order by `created_at DESC, id DESC`.
- No completed Lead renders as `Pending CRM creation`; retry eligibility appears only for `retry_wait`; reconciliation failures and actual write attempts remain separate.
- This local synthetic-demo surface is not production authentication or health monitoring. It excludes adapter keys, payloads, leases, quota permits, provider bodies, and arbitrary metadata. An n8n link requires both an allowlisted workflow reference and numeric execution reference plus the configured loopback editor base; a reference without truthful workflow identity remains text.

## n8n execution deep-link correction

- Manual browser verification after the prior review exposed that `http://localhost:5678/execution/283` reached n8n's `Oops, couldn’t find that` 404 view. The original projection knew only the execution reference and generated a route that the installed editor does not use.
- The running container reports n8n `2.39.8`. Inspection of its installed editor bundle independently confirmed that execution navigation constructs `/workflow/{workflow-id}/executions/{execution-id}`. Read-only inspection of the retained n8n database matched execution `283` to workflow `phase3-crm-write-diagnostic` (`Controlled CRM Rate-Limit Diagnostic`).
- The durable application model already stores both `RecoveryIncident.workflow_reference` and `RecoveryIncident.execution_reference`, so incident projections can truthfully generate `http://localhost:5678/workflow/phase3-crm-write-diagnostic/executions/283`. `CRMWriteAttempt` and `CRMWriteJob` store execution references but not workflow identity; those references remain visible non-clickable text. No column, migration, backfill, execution-number mapping, or guessed workflow identity was added.
- Backend generation and frontend revalidation require `http`, `localhost` or `127.0.0.1`, port `5678`, no credentials/query/fragment, an alphanumeric/underscore/hyphen workflow identifier of at most 160 characters, a numeric execution identifier, and the exact workflow-scoped path. Redacted or unsafe workflow/reference text is evaluated before URL construction, so it cannot reappear inside a generated URL.
- In an isolated authenticated Chrome 148 session, the corrected retained route opened the n8n execution canvas with title `Controlled CRM Rate-Limit Diagnostic - n8n`, `ID#283`, error state, and the recorded `Diagnostic CRM Write Without Recovery` rate-limit failure. This is actual editor rendering, not an HTTP-shell status inference.
- A direct authenticated Chrome check of retained execution `292` rendered `CRM Lead Write Recovery Dispatch`, `ID#292`, and its successful recovery canvas at the same workflow-scoped route shape. The application attempt/job rows do not durably carry that workflow identity, so Operations deliberately shows execution `292` as text rather than fabricating a second link.

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
- The final corrective `./scripts/verify_phase3.sh` run passed 93 Python/SQLite/PostgreSQL tests, 28 browser/helper tests (including fifteen executable operations DOM/fetch tests), and 36 workflow tests. Ruff, JavaScript syntax, JSON/shell syntax, Compose validation, `git diff --check`, and the tracked-content secret scan passed. The verifier intentionally skipped live n8n/NVIDIA/Mailpit fault scenarios.
- The corrected local runtime returned HTTP 200 for `/operations.html`, summary, retained job detail, incidents, and the correlation trace. At `2026-09-20T15:26Z`, summary showed 36 completed jobs and 2 open incidents. Detail for job `e3f7d48d-64c3-4bd0-8d44-6d9d2d2c4e69` and correlation `236169e3-7c3e-4243-8a94-251ac4f9869a` showed completed/contacted Lead `ea6fb4d9-c966-4ac2-be26-30c3bb13d366`, failed `429` attempt/execution `283`, later completed attempt/execution `292`, and a linked resolved incident. A `BEGIN READ ONLY` PostgreSQL comparison returned the same counts and completed/2-attempt/resolved sequence. Durable aggregates before and after all four operations GETs were identical: 36 jobs with 38 total attempts, 3 incidents with 2 open, 38 attempt rows, and 47 Leads. This evidence originally exposed the invalid `/execution/{id}` links; the correction above replaces them only where workflow identity is durable.
- Final fault-control inspection found zero active scopes, zero delivery holds, and zero matching temporary Phase 3/fault/permit triggers. No fault endpoint, recovery worker, n8n import, NVIDIA call, SMTP send, or retained evidence mutation was used.

## Historical implementation and runtime evidence

- Before this corrective review, `./scripts/verify_phase3.sh` passed on implementation worktree `5fc70c6f41643de5620b0974dfcc226e2665c87d`: 92 Python/SQLite/PostgreSQL tests, 15 browser-helper/static frontend tests, and 36 workflow-code/structure tests; lint, Compose config, JSON/shell syntax, diff check, and tracked-content secret scan also passed.
- GitHub Actions `Backend CI` run `35514393356` passed for implementation SHA `5fc70c6f41643de5620b0974dfcc226e2665c87d`; its job completed lint, Python tests, browser tests, and workflow tests. The runner emitted only upstream Node 20 and future Ubuntu image deprecation notices.
- Rebuilt only the existing Compose backend, then received HTTP 200 from `/operations.html`, `/api/operations/summary`, and a retained job detail. The summary observed 36 completed jobs and 2 open incidents at `2026-09-20T13:43:17Z`.
- API job `e3f7d48d-64c3-4bd0-8d44-6d9d2d2c4e69`, correlation `236169e3-7c3e-4243-8a94-251ac4f9869a`, showed a retained failed HTTP 429 attempt in n8n execution `283`, then completed attempt `292`, a resolved linked incident, and a verified contacted Lead. Read-only PostgreSQL queries independently returned the same completed/2-attempt/resolved chain.
- No Phase 3 fault scope, recovery worker, n8n workflow, NVIDIA request, SMTP send, or Mailpit message was triggered for this phase.

The earlier review incorrectly recorded Chrome as unavailable. Google Chrome 148 is installed and was used for the authenticated execution-283 verification described above. Desktop and 390-pixel viewport renders kept the Operations layout readable and produced the same corrected execution-283 href. The established executable DOM/fetch harness remains the interaction regression layer for query state, races, failure rendering, and link validation.
