# Milestone 1 review: reproducible guided demonstration

Date: 2026-09-27
Result: **correction pass complete; ready for another GO/NO-GO review**

## Repository state

- Repository: `kabbersokhi-boop/client-lead-intake-booking-recovery-automation`
- Worktree: `/home/libertarian/client-lead-intake-booking-recovery-automation`
- Branch: `milestone-1-guided-demo`
- Baseline: `34dbfb7d4c7f5b1cc8c26f471adef73fbd0d679c` (`main` and `origin/main` at start)
- Implementation commit: `cac6bd51ef7459dae81e7d7058891fa86a4e6e79`
- Original report commit: `8fc59132ddb76cff2ac45b781ccac55316cd912b`
- Correction implementation commit: `11e7bd03ea184bcf370158607453b06b1a337923`
- Baseline CI: Backend CI run
  [36274004543](https://github.com/kabbersokhi-boop/client-lead-intake-booking-recovery-automation/actions/runs/36274004543),
  completed successfully for the baseline SHA
- No push, pull request, merge, or GitHub metadata mutation was performed.

## Independent-review correction pass

The independent review correctly held Milestone 1 at NO-GO. This pass did not begin Milestone 2 or
redesign the recovery path. It addressed each reported defect and the two maintenance concerns:

1. **Overlapping faults:** the simulator now stores one-shot faults by submission and target path
   under its existing lock. Consuming or clearing one scenario cannot remove another scenario's
   fault. The page disables all cards while its current tab is running; server isolation remains
   authoritative across tabs. A simulator regression reproduces rate limiting for submission A,
   then lost acknowledgement for B, proves an unrelated request is unaffected, and consumes A and
   B independently. The real-browser test also runs rate limiting and lost acknowledgement
   concurrently from two tabs in one browser context; both verify.
2. **Public privileged control path:** the browser first bootstraps a short-lived local demo
   session from an exact configured Origin. The backend sets an HttpOnly, SameSite=Strict cookie and
   returns an HMAC-derived CSRF token; scenario POSTs require the same exact Origin, fresh cookie,
   and token before route or database work begins. The backend alone retains the simulator control
   key. Unit tests reject untrusted bootstrap, missing session, missing Origin, untrusted Origin,
   and missing CSRF before fault arming or intake mutation. A runtime probe likewise returned 403,
   left Lead/Job counts at `27/27`, and left zero armed faults.
3. **Scenario evidence:** rate limiting now proves the persisted due time is at least two seconds
   after the failed attempt and the next authoritative attempt timestamp is not before that due
   time. AI unavailability proves the persisted Lead has both `fallback_unavailable` and
   `needs_review=true`. Duplicate replay compares the original and replayed Lead, submission,
   correlation, and submission-fingerprint identities. The browser asserts these scenario-specific
   fields directly instead of trusting only `verified`; negative tests demonstrate that early
   retry, false review state, changed Lead identity, or changed fingerprint cannot pass.
4. **Retained n8n volumes and readiness:** the permanent import marker is replaced by a versioned
   digest of all workflow exports. A changed digest reimports the exports; required workflows are
   republished on every startup. Readiness now requires both n8n process health and recognition of
   the two required POST webhooks, in addition to the other boundaries. A retained-volume restart
   after changing `lead-intake.json` imported all eight exports and republished all six required
   workflows; the subsequent real-browser run passed. An unchanged retained restart had already
   been verified not to reimport unnecessarily, while still republishing and reaching readiness.

The local session mechanism is deliberately not presented as production user authentication. A
process already controlling the workstation can imitate a local browser request. The stack remains
loopback-bound, uses ignored generated secrets, and exposes no internal control key to browser
responses or tracked files. Webhook readiness also depends on the documented response shape of the
pinned n8n `2.39.8` image; changing that image requires rerunning the readiness tests.

## Delivered behavior

`./scripts/demo up` now creates a dedicated Compose project named `hvac-guided-demo`. It uses
separate PostgreSQL and n8n volumes, loopback-only host ports, locally generated ignored secrets,
and a pinned n8n image. On an empty volume, n8n imports all tracked workflow exports and publishes
only the six customer/reliability workflows needed by the product path. On retained volumes it
reimports when the tracked workflow digest changes and republishes the required workflows on every
startup. Setup waits for a top-level readiness result covering PostgreSQL, n8n process health, both
required n8n webhooks, the CRM simulator, the deterministic AI provider, and Mailpit.

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

Before a scenario can run, the same-origin page obtains a local session cookie and derived CSRF
token. Scenario requests must present the configured Origin, fresh HttpOnly cookie, and matching
token. Only the backend uses the internal fault-control key. Faults are isolated by submission and
path, so different tabs can run independent fault scenarios without overwriting one another.

The five scenarios are:

1. Normal intake: one Lead, Contact, and Opportunity.
2. Equivalent duplicate: the same submission is replayed with HTTP 200 and no duplicate effect.
3. AI unavailable: the deterministic endpoint exceeds the workflow timeout; the valid request is
   stored with `fallback_unavailable`, persists `needs_review=true`, and still reaches the CRM path.
4. CRM 429: a submission- and path-scoped one-shot 429 records `Retry-After: 2`, enters
   `retry_wait`, and completes on the same durable job through the recovery workflow.
5. Lost acknowledgement: the simulator commits an Opportunity and delays its response beyond the
   adapter timeout; recovery reconciles the committed effect and performs no second Opportunity
   POST.

The normal product configuration is unchanged unless `DEMO_MODE=true`. The production workflow's
existing NVIDIA URL remains its default; only the isolated stack supplies the local provider URL.
Fault control is key-protected and scoped to a specific submission and target path. The browser
receives neither the fault-control key nor any other internal service secret.

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

Open `http://localhost:28000/demo.html`, confirm the seven green readiness chips, and run the cards
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

### Corrected clean-volume browser run

The final run began after `./scripts/demo reset`, so PostgreSQL and n8n started with empty demo
volumes. `./scripts/demo up` automatically ran database setup, imported eight workflow exports,
published the six required workflows, and did not report ready until every required boundary and
both required webhooks were available. The real-Chrome test then passed all five cards and the
overlapping two-tab pair:

```text
> npm run test:demo
ok 1 - guided demo verifies all five real browser journeys
# tests 1
# pass 1
# fail 0
```

PostgreSQL evidence from that browser run:

| Scenario | Submission ID | AI state | Review | Final job | Attempts |
|---|---|---:|---:|---:|---:|
| Normal | `80154789-5bd8-46d6-9aee-55b81e1df386` | `enriched` | false | `completed` | 1 |
| Equivalent duplicate | `3953ec62-4953-4db8-b3ec-6673261d5446` | `enriched` | false | `completed` | 1 |
| AI unavailable | `42c37fa9-f4e8-435b-9058-5f08b35f4f7f` | `fallback_unavailable` | **true** | `completed` | 1 |
| CRM 429 | `f3dea6ee-eed8-4565-afd9-aadb480fc2ca` | `enriched` | false | `completed` | 2 |
| Lost acknowledgement | `a768a7d0-c9cf-47b7-84b8-3ae40090364f` | `enriched` | false | `completed` | 1 |
| Overlap: lost acknowledgement | `e9848a55-e2a7-40e4-8851-be415bfebffc` | `enriched` | false | `completed` | 1 |
| Overlap: CRM 429 | `3f4b596a-5990-453b-9330-ea21c69f17ac` | `enriched` | false | `completed` | 2 |

The sequential rate-limit attempt failed at `18:02:14.634445Z`, was due at
`18:02:16.634445Z`, and attempt 2 began at `18:02:16.946832Z`. The overlapping rate-limit
attempt failed at `18:02:22.253239Z`, was due at `18:02:24.253239Z`, and attempt 2 began at
`18:02:24.522079Z`. Thus both authoritative observed delays exceeded two seconds and neither retry
began before its persisted due time.

The simulator snapshot contained exactly seven Contacts and seven Opportunities and no armed
faults. It recorded two 429s and exactly one Opportunity POST for each lost-ack submission. The
browser test independently asserted the scenario-specific persisted fields, operation identities,
timestamps, counts, and rendered technical evidence.

Screenshots:

- [`guided-demo-overview.png`](../assets/demo/guided-demo-overview.png)
- [`guided-demo-lost-ack.png`](../assets/demo/guided-demo-lost-ack.png)
- [`guided-demo-overlap-rate-limit.png`](../assets/demo/guided-demo-overlap-rate-limit.png)

The original five-scenario run and its generated IDs remain preserved in report commit
`8fc59132ddb76cff2ac45b781ccac55316cd912b`; the table above is the later clean run against the
correction commit.

Runtime logs and live evidence are intentionally not committed because executions contain generated
identities and the stack is reproducible. During a run they are available through
`./scripts/demo logs [service]`, `GET /api/demo/readiness`, the Operations page, and the simulator's
`/simulator/api/state` endpoint.

### Project regression suite

Final command: `bash scripts/verify_phase3.sh`

- Python/PostgreSQL: **197 passed**
- Python lint: **passed**
- Browser/helper tests: **33 passed**
- Workflow-code tests: **48 passed**
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

The Playwright test uses installed headless Chrome and exercises the served page, local session and
CSRF flow, five sequential demo API requests, two concurrent requests from separate tabs, published
n8n webhooks, actual PostgreSQL persistence, HTTP calls through the production CRM adapter, fault
injection in the separate simulator, recovery dispatch, and rendered evidence. It does not mock
those application boundaries.

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

For the original implementation, the user authorized at most two lower-cost subagents and
specifically requested GPT-6 Luna at medium reasoning for bounded work. Exactly two read-only agents
were used; neither edited files, spawned another agent, or made external changes:

1. `/root/demo_inventory` — GPT-6 Luna, medium reasoning. Task: inventory current Compose, n8n,
   simulator, trace, and setup behavior and identify reusable pieces and isolation gaps. Finding: the
   existing stack had no dedicated n8n service, setup was manual, and there was no coordinated
   readiness/reset path; the simulator, trace UI, workflow exports, and recovery path were reusable.
2. `/root/verification_inventory` — GPT-6 Luna, medium reasoning. Task: inventory verification and
   browser coverage and identify the smallest authoritative scenario assertions. Finding: existing
   tests were primarily helper/workflow-level rather than real-browser integration; isolated Compose,
   scoped fault identity, and one-Lead/Contact/Opportunity assertions were needed.

For the requested correction pass, exactly two additional read-only GPT-6 Luna agents at medium
reasoning were used, again without file edits, recursion, or external changes:

1. `/root/correction_concurrency_security` — inspected fault concurrency and the privileged demo
   endpoint, then adversarially reviewed the implemented isolation/session changes. It recommended
   submission/path fault storage and exact-origin session/CSRF enforcement; its final review was
   `CLEAR`.
2. `/root/correction_evidence_lifecycle` — inspected authoritative evidence, retained-volume import,
   and readiness. It recommended persisted timestamps/review/identity assertions, digest-based
   refresh, and webhook availability checks. Its final low-severity observation that replay identity
   omitted the submission fingerprint was resolved before commit by carrying and comparing that
   fingerprint and adding negative coverage.

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
