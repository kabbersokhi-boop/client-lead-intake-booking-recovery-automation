const test = require("node:test");
const assert = require("node:assert/strict");

const { eventAction, eventMarkup } = require("../../backend/simulator/static/app.js");

test("simulator API events explain the documented adapter sequence", () => {
  assert.equal(eventAction({ method: "GET", path: "/contacts/lookup" }), "Contact lookup");
  assert.equal(eventAction({ method: "POST", path: "/contacts/upsert" }), "Contact upsert");
  assert.equal(
    eventAction({ method: "GET", path: "/contacts/sim_contact_123" }),
    "Contact verification",
  );
  assert.equal(
    eventAction({ method: "GET", path: "/opportunities/search" }),
    "Opportunity search",
  );
  assert.equal(eventAction({ method: "POST", path: "/opportunities/" }), "Opportunity create");
});

test("simulator event detail includes safe trace references and escapes content", () => {
  const markup = eventMarkup({
    method: "POST",
    path: "/contacts/upsert",
    status: 200,
    timestamp: "2026-09-22T00:00:00Z",
    requestId: "sim_req_123",
    submissionReference: "submission-123",
    retryAfter: null,
    query: {},
    requestBody: { name: "<synthetic>" },
    responseBody: { ok: true },
  });

  assert.match(markup, /Contact upsert/);
  assert.match(markup, /simulator_request_id/);
  assert.match(markup, /submission_reference/);
  assert.doesNotMatch(markup, /<synthetic>/);
  assert.match(markup, /&lt;synthetic&gt;/);
});
