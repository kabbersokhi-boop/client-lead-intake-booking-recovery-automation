# Guided isolated demonstration

## What this proves

This demo is a recruiter-facing path through the repository's real local application boundaries.
The browser invokes published n8n webhooks. n8n invokes FastAPI. PostgreSQL owns the durable job
and Lead state. The HighLevel adapter uses HTTP against the separate contract simulator. Result
cards are built from observed PostgreSQL and simulator state. Same-origin browser sessions protect
scenario writes; the internal simulator-control key never enters browser responses.

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
stub, simulator, Mailpit, and both scenario-critical webhook registrations. On a retained n8n
volume, a source digest triggers reimport only when tracked exports change; required workflows are
republished on every start. The file is ignored by Git and secret values are not printed.

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

1. Show the LOCAL / SYNTHETIC / NO EXTERNAL ACCOUNTS boundary and all green readiness checks,
   including lead-intake and recovery webhook registration.
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
   compares a digest of the tracked exports on every retained-volume start, reimports changed
   exports, and publishes only customer/reliability workflows; diagnostic and reporting exports
   remain unpublished.
2. The deterministic provider returns the same five-field extraction contract used by the normal
   intake workflow. A message marker makes only the selected synthetic AI call exceed n8n's
   configured timeout.
3. The browser first obtains a same-origin session backed by an HttpOnly, SameSite cookie. Scenario
   POSTs require the matching CSRF header and an explicitly allowed Origin. This is local anti-CSRF
   protection, not production user authentication; a process already controlling the workstation
   can impersonate a local browser. The backend alone holds the internal simulator-control key.
4. Simulator faults are stored and atomically consumed by submission identity and target path, so
   overlapping tabs retain independent faults. A tab disables all of its scenario buttons while a
   run is active as a usability guard; server-side isolation is authoritative across tabs.
5. The 429 case fails before the Contact write, persists the provider Retry-After and due time on
   attempt 1, and proves attempt 2 did not start before either minimum.
6. The lost-ack case commits the Opportunity and then delays the reply beyond the adapter timeout.
   Recovery searches by application identity, verifies the existing Contact and Opportunity, and
   completes without a second Opportunity POST.
7. The browser E2E test independently asserts retry timestamps, persisted `needs_review`, duplicate
   operation identity, one Lead/Contact/Opportunity, and a same-context overlapping 429/lost-ACK
   run. It captures screenshots in `docs/assets/demo/`.

Run deterministic and browser checks:

```bash
./scripts/verify_phase3.sh
npm ci
npm run test:demo
```
