# Milestone 1 review: reproducible guided demonstration

Date: 2026-09-27
Result: **complete and locally verified**

## Repository state

- Repository: `kabbersokhi-boop/client-lead-intake-booking-recovery-automation`
- Worktree: `/home/libertarian/client-lead-intake-booking-recovery-automation`
- Branch: `milestone-1-guided-demo`
- Baseline: `34dbfb7d4c7f5b1cc8c26f471adef73fbd0d679c` (`main` and `origin/main` at start)
- Implementation commit: `cac6bd51ef7459dae81e7d7058891fa86a4e6e79`
- Baseline CI: Backend CI run
  [36274004543](https://github.com/kabbersokhi-boop/client-lead-intake-booking-recovery-automation/actions/runs/36274004543),
  completed successfully for the baseline SHA
- No push, pull request, merge, or GitHub metadata mutation was performed.

## Delivered behavior

`./scripts/demo up` now creates a dedicated Compose project named `hvac-guided-demo`. It uses
separate PostgreSQL and n8n volumes, loopback-only host ports, locally generated ignored secrets,
and a pinned n8n image. On an empty volume, n8n imports all tracked workflow exports and publishes
only the six customer/reliability workflows needed by the product path. Setup waits for a top-level
readiness result covering PostgreSQL, n8n, the CRM simulator, the deterministic AI provider, and
Mailpit.

The published set is lead intake, appointment booking, follow-up dispatch, CRM write recovery,
recovery error capture, and HighLevel stage sync. Diagnostic and reporting exports are imported for
inspection but remain unpublished.

The guided page at `http://localhost:28000/demo.html` runs five synthetic scenarios through the
real local boundary chain:

`browser -> n8n webhook -> FastAPI -> PostgreSQL -> HighLevel HTTP adapter -> CRM simulator`

The UI shows a business explanation, observed timeline, verdict, submission and correlation IDs,
durable job and attempt identity, payload fingerprint, execution references, and sanitized
simulator events. A scenario is marked verified only after querying authoritative PostgreSQL and
simulator state.

The five scenarios are:

1. Normal intake: one Lead, Contact, and Opportunity.
2. Equivalent duplicate: the same submission is replayed with HTTP 200 and no duplicate effect.
3. AI unavailable: the deterministic endpoint exceeds the workflow timeout; the valid request is
   stored with `fallback_unavailable` and still reaches the CRM path.
4. CRM 429: a submission- and path-scoped one-shot 429 records `Retry-After: 2`, enters
   `retry_wait`, and completes on the same durable job through the recovery workflow.
5. Lost acknowledgement: the simulator commits an Opportunity and delays its response beyond the
   adapter timeout; recovery reconciles the committed effect and performs no second Opportunity
   POST.

The normal product configuration is unchanged unless `DEMO_MODE=true`. The production workflow's
existing NVIDIA URL remains its default; only the isolated stack supplies the local provider URL.
Fault control is key-protected and scoped to a specific submission and target path.

## Recruiter walkthrough

Prerequisites are Docker Engine with Compose v2, `curl`, and `openssl`. No HighLevel, NVIDIA, Make,
SMTP, or other paid/external credentials are needed.

```bash
# After the feature branch is shared by the repository owner:
git clone https://github.com/kabbersokhi-boop/client-lead-intake-booking-recovery-automation.git
cd client-lead-intake-booking-recovery-automation
git switch milestone-1-guided-demo
./scripts/demo up
```

Open `http://localhost:28000/demo.html`, confirm the five green readiness chips, and run the cards
in order. The concise three-minute script and deeper technical narration are in
[`docs/guided-demo.md`](../guided-demo.md).

Useful inspection and cleanup commands:

```bash
./scripts/demo status
./scripts/demo logs backend
./scripts/demo logs n8n
./scripts/demo down      # retains only the demo volumes
./scripts/demo reset     # removes only hvac-guided-demo containers/network/volumes
```

Optional real-browser verification requires Node.js 22+, npm, and installed Chrome/Chromium:

```bash
npm ci
npm run test:demo
```

## Verification evidence

### Clean-volume browser run

The final run began after `./scripts/demo reset`, so PostgreSQL and n8n started with empty demo
volumes. `./scripts/demo up` automatically ran database setup, imported eight workflow exports,
published the six required workflows, and did not report ready until every required boundary was
reachable. The real-Chrome test then passed all five cards:

```text
> npm run test:demo
ok 1 - guided demo verifies all five real browser journeys
# tests 1
# pass 1
# fail 0
```

PostgreSQL evidence from that browser run:

| Scenario | Submission ID | AI state | Final job | Attempts |
|---|---|---:|---:|---:|
| Normal | `568a8441-553f-46e5-a3e2-dcb2bb53ef88` | `enriched` | `completed` | 1 |
| Equivalent duplicate | `defe4a08-c9e7-4bfa-89d1-e6852c7d2143` | `enriched` | `completed` | 1 |
| AI unavailable | `4df7fd4c-550a-4491-955a-b3b00edb3147` | `fallback_unavailable` | `completed` | 1 |
| CRM 429 | `2f015ebe-e0f4-4149-b299-1eedc2340633` | `enriched` | `completed` | 2 |
| Lost acknowledgement | `84474b3d-9bde-430b-925a-192186bc8ea1` | `enriched` | `completed` | 1 |

The simulator snapshot contained exactly five Contacts and five Opportunities. It recorded one 429
and exactly one Opportunity POST for the lost-ack submission. The browser test independently
asserted `verified=true` plus exactly one Lead, Contact, and Opportunity for each response and
checked the rendered technical evidence.

Screenshots:

- [`guided-demo-overview.png`](../assets/demo/guided-demo-overview.png)
- [`guided-demo-lost-ack.png`](../assets/demo/guided-demo-lost-ack.png)

Runtime logs and live evidence are intentionally not committed because executions contain generated
identities and the stack is reproducible. During a run they are available through
`./scripts/demo logs [service]`, `GET /api/demo/readiness`, the Operations page, and the simulator's
`/simulator/api/state` endpoint.

### Project regression suite

Final command: `bash scripts/verify_phase3.sh`

- Python/PostgreSQL: **191 passed**
- Python lint: **passed**
- Browser/helper tests: **33 passed**
- Workflow-code tests: **47 passed**
- Simulator JavaScript syntax: **passed**
- JSON, shell, default Compose, and diff checks: **passed**
- Tracked-content secret scan: **passed**
- Additional `node --check` for `frontend/demo.js` and the Playwright test: **passed**
- `npm ci`: **0 vulnerabilities reported**

Two existing dependency deprecation warnings were emitted by Starlette/FastAPI test integration;
they did not fail the suite and were not introduced as runtime behavior by this milestone.

### Isolation and reset audit

Before reset, both the new demo project and the preserved runtime were running. After
`./scripts/demo reset`, all six `hvac-guided-demo` containers, its network, and both demo volumes
were absent, while these pre-existing containers remained up:

- `n8n` on `127.0.0.1:5678`
- `customer-ops-ai-api-1` on `127.0.0.1:8000` (healthy)
- `customer-ops-ai-postgres-1` on `127.0.0.1:5432` (healthy)

The empty-volume stack was then rebuilt and the browser suite passed. At handoff,
`./scripts/demo down` removed only the new demo containers and network; the three preserved
containers remained running. The demo volumes are retained so the user can restart quickly, and
`./scripts/demo reset` remains the documented clean-state command.

## Automated coverage and boundaries

The Playwright test uses installed headless Chrome and exercises the served page, the five demo API
requests, published n8n webhooks, actual PostgreSQL persistence, HTTP calls through the production
CRM adapter, fault injection in the separate simulator, recovery dispatch, and rendered evidence.
It does not mock those application boundaries.

It intentionally does not claim to verify production HighLevel credentials or calendars, external
SMTP delivery, NVIDIA model quality or availability, Make/Sheets delivery, internet failure modes,
or universal exactly-once semantics. Appointments remain local, email remains in Mailpit, the AI
provider is prominently labeled deterministic/demo-only, and all generated customer identities are
synthetic.

## Issues found and resolved

- The original cold-start readiness loop searched for any `"ready":true` in the JSON document.
  A healthy nested check could therefore satisfy it while n8n was still importing. A clean-volume
  Chrome run exposed the race. The loop now anchors on the top-level field, and the page polls again
  while dependencies start. A second empty-volume startup and all five browser journeys passed.
- The first scenario implementation reused a fixed phone number, which could let separate scenarios
  collide under CRM duplicate matching. Every run now generates unique synthetic email and phone
  identities while equivalent replay deliberately reuses the exact same payload.
- n8n 2.39.8 logs warnings about its missing internal Python task runner and future task-runner
  defaults. These workflows use JavaScript Code nodes; workflow execution and all browser scenarios
  passed. No Python runner is required for this demo.

## Dependency change

`playwright-core` was added as a development dependency and locked in `package-lock.json`. The core
package reuses the workstation's installed Chrome instead of downloading and caching another browser,
keeping the repository and setup smaller while still providing real-browser coverage.

## Agent usage

The user authorized at most two lower-cost subagents and specifically requested GPT-6 Luna at medium
reasoning for bounded work. Exactly two read-only agents were used; neither edited files, spawned
another agent, or made external changes:

1. `/root/demo_inventory` — GPT-6 Luna, medium reasoning. Task: inventory current Compose, n8n,
   simulator, trace, and setup behavior and identify reusable pieces and isolation gaps. Finding: the
   existing stack had no dedicated n8n service, setup was manual, and there was no coordinated
   readiness/reset path; the simulator, trace UI, workflow exports, and recovery path were reusable.
2. `/root/verification_inventory` — GPT-6 Luna, medium reasoning. Task: inventory verification and
   browser coverage and identify the smallest authoritative scenario assertions. Finding: existing
   tests were primarily helper/workflow-level rather than real-browser integration; isolated Compose,
   scoped fault identity, and one-Lead/Contact/Opportunity assertions were needed.

The primary agent performed all implementation, runtime testing, browser inspection, commits, and
the final requirement audit.

## GitHub metadata suggestions

Current GitHub metadata has no description and no topics. Suggested description:

> Reliability-first HVAC lead intake and booking automation with n8n, FastAPI, PostgreSQL,
> HighLevel, durable recovery, and a one-command local demo.

Suggested topics:

`n8n`, `fastapi`, `postgresql`, `highlevel`, `hvac`, `lead-automation`, `workflow-automation`,
`idempotency`, `reliability`, `docker-compose`, `playwright`

These are suggestions only; repository metadata was not changed.
