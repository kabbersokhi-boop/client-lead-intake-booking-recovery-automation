# Project handover

Updated: 2026-09-28. Working branch: `milestone-2a-ai-evaluation`.

## Scope from here

This provider-recovery pass is the final feature implementation for now. **Only recruiter-facing presentation and end-to-end acceptance remain in scope.** Do not automatically start another feature milestone or resume paid inference experiments. Existing API access is not permission to alter live integrations or send customer messages.

The project is a working, fallback-capable automation foundation, not a demonstrated production-grade autonomous AI decision-maker. Its strongest evidence is durable state, idempotency, recovery, explicit failure handling and reproducible tests. AI extraction is optional and its current quality limitations must stay visible.

## What has been built

### Existing automation foundation

- Browser intake, n8n orchestration, FastAPI and PostgreSQL persistence.
- HighLevel Contact/Opportunity integration plus local contract simulator.
- Durable CRM jobs, identity checks, controlled retries, reconciliation after uncertain writes and replay protection.
- Local booking and notification/follow-up flows; Mailpit is a development mail sink, not production email delivery.
- Operational views and Make/Google Sheets reporting integration. Local booking is not real-calendar availability or reservation proof.

### Milestone 1 — guided demo, completed

An isolated, credential-free demo runs five synthetic journeys: normal intake, duplicate replay, unavailable AI, CRM rate limit and a lost acknowledgement after a remote commit. Evidence comes from persisted state and simulator events. Corrections added per-submission fault isolation, session/CSRF controls, authoritative retry/review/identity evidence, negative tests, digest-based workflow refresh and webhook readiness.

The prior pass recorded real Chrome and cross-tab coverage, plus clean/retained-volume startup. See [Milestone 1 report](docs/reviews/milestone-1-report.md) and [guided walkthrough](docs/guided-demo.md). Milestone 1 baseline is `6473e37131cb9cc948b859b35dc6689e3a65d796`.

### Milestone 2A — evaluation infrastructure and provider recovery

- 60 synthetic cases: 40 development and 20 held out; versioned rubric, frozen identities, schema validation and offline evaluation tests.
- Durable request reservations, uncertainty accounting, no automatic retries of reserved cases, global lock/cap and circuit breaker.
- Preserved original v1 observations and corrected v2 methodology without rewriting history.
- Fixed circuit-reset ordering in the preceding correction pass.
- Diagnosed repeated `openai/gpt-oss-20b` inference timeouts and added a separately evaluated NVIDIA Lightning profile.
- Generated an opt-in deployable workflow matching that profile; canonical baseline and existing live workflow remain unchanged.

The original model's baseline remains partial (6/40 development, no held-out). The alternative profile completed 40/40 development and 20/20 held-out requests. Across 60 attempts: 56 schema-valid outputs, two invalid outputs, two timeouts. Strict all-field agreement was 9/40 development and 6/20 held out. Schema validity is not semantic accuracy; all summaries require review. Total charged requests: 85/150, including historical calls and diagnostics.

Read [provider recovery](docs/reviews/provider-recovery.md) first, then [Lightning measurements](docs/reviews/milestone-2a-results-lightning.md). The [older Milestone 2A report](docs/reviews/milestone-2a-report.md) preserves prior partial-baseline history.

## Verification at this handoff

- 197 Python/PostgreSQL tests passed.
- 33 browser-helper tests passed.
- 48 workflow tests passed.
- 33 offline evaluation tests passed.
- Lint, syntax, JSON, shell, Compose, diff and secret checks passed.
- Candidate evaluation made 60 actual NVIDIA requests inside the credential-owning n8n container.
- Existing runtime was not restarted or switched to Lightning. No push, merge or deployment was performed in this recovery pass.
- Chrome demo verification and integrated Lightning workflow execution were **not rerun in this pass**. These are remaining acceptance checks, not implied successes.

## Start locally

```bash
./scripts/demo up
# Open http://localhost:28000/demo.html
npm run test:evaluation
./scripts/verify_phase3.sh
# When finished with the isolated demo:
./scripts/demo down
```

The demo uses simulated external boundaries; it is intentionally independent of real-provider availability. See the walkthrough for prerequisites, reset and browser checks. `demo down` leaves reusable demo volumes. Never remove unrelated containers or volumes.

## Remaining task 1: end-to-end acceptance

1. Inspect branch/worktree and preserve existing work. Do not push or merge without an explicit go-ahead.
2. Start the isolated guided demo; verify fresh/retained startup and all five Chrome journeys, including overlapping fault scenarios. Retain readable, sanitized evidence.
3. Generate the Lightning workflow with `node scripts/export-lightning-workflow.mjs`; inspect it. It retains the original workflow ID and can replace it on import. Stage in an isolated credential-protected runtime with simulated CRM/email and a rollback export. Do not change the existing live workflow silently.
4. Exercise one synthetic intake through actual NVIDIA, workflow validation, API, persistence and simulated CRM. Verify the chosen model/settings and persisted identity; replay the identical operation without duplication.
5. Exercise AI failure fallback, invalid output, CRM retry/uncertain acknowledgement, and local booking/confirmation boundaries. Confirm no false booking/availability/sent-message claims. Account for additional provider calls before making them.
6. Produce a clear pass/fail matrix separating real-provider evidence, simulated dependencies and untested live integrations. A blocked external provider is reported honestly, not bypassed by claiming stub success.

No requirement to contact real customers, reserve real calendar slots, enable paid infrastructure or exercise live HighLevel/Make writes is implied by this checklist.

## Remaining task 2: presentation

- Make README tell a concise business/problem/architecture/reliability story, with a clear demo entry point.
- Add/update a compact architecture diagram, sanitized screenshots and a short walkthrough/video script showing a normal run and a recovery case.
- Link tests, raw evidence and limitations without making recruiters navigate every historical report.
- Describe engineering outcomes, not invented ROI, customer deployments, uptime or production accuracy. Explicitly distinguish local booking, Mailpit, simulated CRM and real-provider evaluation.
- End with a reproducible runbook and a short interview narrative explaining trade-offs and the diagnosed provider failure.

## Other discussed milestones — deferred, not required now

Only Milestone 2B has a concrete recommendation in the retained evaluation report; the other items below are prospective directions, not completed or newly authorized commitments.

| Direction | Purpose | Current status |
|---|---|---|
| Milestone 2B: audited operator review | Preserve original extraction; record correction, reviewer, time and reason | Deferred; review flags are not this full feature |
| Returning-customer identity | Explicit repeat-customer matching and safe merge policy | Deferred |
| Real calendar integration | Availability, reservation conflicts, timezone and cancellation handling | Deferred; local booking is not equivalent |
| Production deployment hardening | Operator authentication/authorization, deployment controls and observability | Deferred; demo session protection is not production auth |
| Production notification delivery | Durable delivery/reconciliation and real provider integration | Deferred; Mailpit is not delivery proof |
| Operational outcome measurement | Independently grounded conversion/recovery/ROI evidence | Deferred; synthetic tests do not establish business impact |

Do not expand into these features during the presentation/acceptance pass. Fix only defects necessary to make the existing demonstrated paths truthful and reproducible, then report remaining limitations.
