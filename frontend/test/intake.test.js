const test = require("node:test");
const assert = require("node:assert/strict");

const {
  bookingPendingFor,
  bookingView,
  pendingFor,
  successView,
  traceView,
  verifiedBooking,
  verifiedSuccess,
} = require("../intake.js");

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
    pipeline_stage: "new_lead",
    follow_up_status: "pending",
    follow_up_due_at: "2026-09-19T00:02:00Z",
    ...payload,
  };
  assert.equal(verifiedSuccess(valid, payload), true);
  assert.deepEqual(successView(valid, payload), {
    title: "Lead accepted",
    intakeState: "created",
    correlationId: payload.correlation_id,
    crmLeadId: valid.crm_lead_id,
    aiStatus: "enriched",
    aiStatusTone: "success",
    pipelineStage: "new_lead",
    followUpStatus: "pending",
    followUpDueAt: "2026-09-19T00:02:00Z",
  });
  assert.equal(verifiedSuccess({}, payload), false);
  assert.equal(successView({}, payload), null);
  assert.equal(verifiedSuccess({ state: "accepted", ...payload }, payload), false);
});

test("fallback AI outcomes keep verified intake success but use warning presentation", () => {
  const payload = {
    submission_id: "09f70a8e-1304-42b9-a1e6-022d2daf4bd6",
    correlation_id: "eeb1b11a-22c8-4a2f-a463-554246c14a16",
  };
  const view = successView(
    {
      state: "accepted",
      intake_state: "created",
      crm_lead_id: "d678189e-db40-46d7-89a5-4bca74dded23",
      ai_status: "fallback_unavailable",
      pipeline_stage: "new_lead",
      follow_up_status: "pending",
      follow_up_due_at: "2026-09-19T00:02:00Z",
      ...payload,
    },
    payload,
  );

  assert.equal(view.title, "Lead accepted");
  assert.equal(view.aiStatusTone, "warning");
});

test("trace view prioritizes useful persisted lead fields", () => {
  const view = traceView({
    lead: {
      full_name: "Maya Verma",
      email: "maya.verma@example.com",
      phone: "+1 604 555 0138",
      pipeline_stage: "new_lead",
      service_type: "furnace_service",
      urgency: "medium",
      preferred_time: "Tuesday afternoon",
      ai_status: "enriched",
      needs_review: false,
      client_received_at: "2026-09-19T00:00:00Z",
      created_at: "2026-09-19T00:00:01Z",
    },
    audit_events: [{ event_type: "crm.lead_created", status: "success" }],
    follow_ups: [{ status: "pending", due_at: "2026-09-19T00:02:00Z" }],
    appointments: [],
  });

  assert.equal(view.customer, "Maya Verma");
  assert.equal(view.serviceType, "furnace_service");
  assert.equal(view.needsReview, false);
  assert.equal(view.audits.length, 1);
  assert.equal(view.followUpStatus, "pending");
  assert.equal(view.bookingStatus, "not booked");
  assert.equal(traceView({ lead: null }), null);
});

test("unchanged booking retry reuses its booking request identifier", () => {
  const values = {
    correlation_id: "eeb1b11a-22c8-4a2f-a463-554246c14a16",
    appointment_local: "2026-10-20T10:30",
    business_timezone: "America/Vancouver",
  };
  const first = bookingPendingFor(values, null, () => "booking-one").pending;
  const replay = bookingPendingFor({ ...values }, first, () => "booking-two");
  const changed = bookingPendingFor(
    { ...values, appointment_local: "2026-10-20T11:30" },
    first,
    () => "booking-two",
  );

  assert.equal(replay.reused, true);
  assert.equal(replay.pending.payload.booking_request_id, "booking-one");
  assert.equal(changed.reused, false);
  assert.equal(changed.pending.payload.booking_request_id, "booking-two");
});

test("booking success requires the verified lifecycle response", () => {
  const payload = {
    booking_request_id: "09f70a8e-1304-42b9-a1e6-022d2daf4bd6",
    correlation_id: "eeb1b11a-22c8-4a2f-a463-554246c14a16",
  };
  const body = {
    state: "booked",
    booking_state: "created",
    appointment_id: "d678189e-db40-46d7-89a5-4bca74dded23",
    appointment_at: "2026-10-20T17:30:00Z",
    business_timezone: "America/Vancouver",
    pipeline_stage: "appointment_booked",
    follow_up_status: "cancelled",
    confirmation_state: "sent",
    ...payload,
  };

  assert.equal(verifiedBooking(body, payload), true);
  assert.equal(bookingView(body, payload).followUpStatus, "cancelled");
  assert.equal(verifiedBooking({ ...body, pipeline_stage: "new_lead" }, payload), false);
});

test("trace view clearly marks fallback records needing review", () => {
  const view = traceView({
    lead: { full_name: "Maya Verma", ai_status: "fallback_invalid", needs_review: true },
    audit_events: [],
  });

  assert.equal(view.needsReview, true);
});
