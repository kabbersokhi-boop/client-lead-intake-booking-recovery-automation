# Guided isolated demonstration

## What this proves

This demo is a recruiter-facing path through the repository's real local application boundaries.
The browser invokes published n8n webhooks. n8n invokes FastAPI. PostgreSQL owns the durable job
and Lead state. The HighLevel adapter uses HTTP against the separate contract simulator. Result
cards are built from observed PostgreSQL and simulator state.

It does not prove production traffic, external email delivery, model quality, HighLevel Calendar
capacity, or universal exactly-once delivery. All identities and effects are synthetic.

## Fresh setup

Prerequisites:

- Docker Engine with Docker Compose v2
- `curl` and `openssl`
- for automated browser verification only: Node.js 22+, npm, and Chrome/Chromium

Run:

```bash
git clone https://github.com/kabbersokhi-boop/client-lead-intake-booking-recovery-automation.git
cd client-lead-intake-booking-recovery-automation
./scripts/demo up
```

The command creates `.demo/runtime.env` with locally generated secrets at mode 0600, builds the
stack, imports and publishes the required workflows, and waits for database, n8n, backend, model
stub, and simulator readiness. The file is ignored by Git and secret values are not printed.

Open:

- Guided demo: http://localhost:28000/demo.html
- Read-only Operations view: http://localhost:28000/operations.html
- HighLevel contract simulator: http://localhost:28080
- Mailpit local inbox: http://localhost:28025
- Dedicated n8n editor: http://localhost:25678 (optional; first visit may ask for a local owner)

Useful commands:

```bash
./scripts/demo status
./scripts/demo logs backend
./scripts/demo down
./scripts/demo reset
```

`down` stops only this demo and retains its volumes. `reset` removes only the Compose project
named `hvac-guided-demo` and its two named volumes. It does not address unrelated containers or
volumes.

## Three-minute walkthrough

1. Show the LOCAL / SYNTHETIC / NO EXTERNAL ACCOUNTS boundary and five green readiness checks.
2. Run **Normal intake**. Point out HTTP 201 and the one Lead, Contact, and Opportunity counts.
3. Run **Equivalent duplicate**. Point out the replayed HTTP 200 and unchanged one/one/one counts.
4. Run **AI unavailable**. Point out `fallback_unavailable`: the valid enquiry was preserved and
   marked for review despite the deterministic provider timeout.
5. Run **CRM rate limiting**. Point out `retry_wait`, the recorded 429 and Retry-After, then the
   same job completing through the recovery worker.
6. Run **Lost acknowledgement**. Point out the timeout after the remote Opportunity committed,
   completed reconciliation, and exactly one simulated Contact and Opportunity.
7. Expand **Technical evidence** or open Operations and the simulator to inspect the identifiers,
   attempt history, and sanitized HTTP events.

## Deeper technical walkthrough

Use a fresh run and narrate the boundaries rather than only the UI:

1. `compose.demo.yml` uses dedicated volumes and loopback mappings. `scripts/demo_n8n_entrypoint.sh`
   imports the tracked exports and publishes only customer/reliability workflows; diagnostic and
   reporting exports remain unpublished.
2. The deterministic provider returns the same five-field extraction contract used by the normal
   intake workflow. A message marker makes only the selected synthetic AI call exceed n8n's
   configured timeout.
3. Simulator fault control requires an internal key and is reachable by the guided backend only.
   A fault includes the submission identity and target path, so another concurrent contract call
   cannot accidentally consume it.
4. The 429 case fails before the Contact write, persists the provider Retry-After on attempt 1,
   and later completes on attempt 2.
5. The lost-ack case commits the Opportunity and then delays the reply beyond the adapter timeout.
   Recovery searches by application identity, verifies the existing Contact and Opportunity, and
   completes without a second Opportunity POST.
6. The browser E2E test observes each scenario response, asserts one Lead/Contact/Opportunity in
   authoritative state, checks the rendered evidence, and captures the screenshots in
   `docs/assets/demo/`.

Run deterministic and browser checks:

```bash
./scripts/verify_phase3.sh
npm ci
npm run test:demo
```
