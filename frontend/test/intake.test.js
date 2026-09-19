const test = require("node:test");
const assert = require("node:assert/strict");

const { pendingFor, verifiedSuccess } = require("../intake.js");

const values = {
  full_name: "Maya Verma",
  email: "maya.verma@example.com",
  phone: "+1 604 555 0138",
  message: "The furnace is not heating.",
};

test("unchanged retry reuses its submission and correlation identifiers", () => {
  let sequence = 0;
  const identifier = () => `id-${++sequence}`;
  const first = pendingFor(values, null, identifier, () => "2026-09-19T00:00:00Z").pending;
  const retry = pendingFor({ ...values }, first, identifier, () => "different");

  assert.equal(retry.reused, true);
  assert.equal(retry.pending.payload.submission_id, first.payload.submission_id);
  assert.equal(retry.pending.payload.correlation_id, first.payload.correlation_id);
  assert.equal(retry.pending.payload.received_at, first.payload.received_at);
});

test("edited data intentionally creates a new submission identity", () => {
  const identifiers = ["submission-one", "correlation-one", "submission-two", "correlation-two"];
  const first = pendingFor(values, null, () => identifiers.shift(), () => "first").pending;
  const edited = pendingFor(
    { ...values, message: "The furnace is still not heating." },
    first,
    () => identifiers.shift(),
    () => "second",
  );

  assert.equal(edited.reused, false);
  assert.equal(edited.pending.payload.submission_id, "submission-two");
  assert.equal(edited.pending.payload.correlation_id, "correlation-two");
});

test("only the documented intake contract confirms browser success", () => {
  const payload = {
    submission_id: "09f70a8e-1304-42b9-a1e6-022d2daf4bd6",
    correlation_id: "eeb1b11a-22c8-4a2f-a463-554246c14a16",
  };
  const valid = {
    state: "accepted",
    intake_state: "created",
    crm_lead_id: "d678189e-db40-46d7-89a5-4bca74dded23",
    ai_status: "enriched",
    ...payload,
  };
  assert.equal(verifiedSuccess(valid, payload), true);
  assert.equal(verifiedSuccess({}, payload), false);
  assert.equal(verifiedSuccess({ state: "accepted", ...payload }, payload), false);
});
