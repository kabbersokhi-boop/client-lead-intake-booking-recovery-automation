const test = require("node:test");
const assert = require("node:assert/strict");

const {
  acceptIntakeResult,
  beginIntakeAttempt,
  bookingPendingFor,
  bookingView,
  confirmationIsSettled,
  labelFor,
  pendingFor,
  queuedView,
  successView,
  serviceLabel,
  traceView,
  verifiedBooking,
  verifiedSuccess,
  verifiedQueued,
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
    email: "maya.verma@example.com",
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
    title: "Request saved",
    intakeState: "created",
    submissionId: payload.submission_id,
    correlationId: payload.correlation_id,
    crmLeadId: valid.crm_lead_id,
    aiStatus: "enriched",
    aiStatusLabel: "Enriched",
    aiStatusTone: "success",
    pipelineStage: "New request",
    rawPipelineStage: "new_lead",
    followUpStatus: "Scheduled",
    rawFollowUpStatus: "pending",
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
    email: "maya.verma@example.com",
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

  assert.equal(view.title, "Request saved");
  assert.equal(view.aiStatusTone, "warning");
});

test("queued intake preserves identity without fabricating a CRM lead or enabling booking", () => {
  const payload = {
    submission_id: "09f70a8e-1304-42b9-a1e6-022d2daf4bd6",
    correlation_id: "eeb1b11a-22c8-4a2f-a463-554246c14a16",
  };
  const queued = {
    state: "received",
    intake_state: "queued",
    recovery_job_id: "d678189e-db40-46d7-89a5-4bca74dded23",
    recovery_state: "pending",
    ...payload,
  };
  assert.equal(verifiedQueued(queued, payload), true);
  assert.equal(queuedView(queued, payload).title, "Enquiry received for processing");
  assert.equal(verifiedSuccess(queued, payload), false);
  assert.equal(verifiedQueued({ ...queued, crm_lead_id: queued.recovery_job_id }, payload), false);
  assert.equal(beginIntakeAttempt().bookingPanelVisible, false);
});

test("pending trace is distinct from an old successful CRM card", () => {
  const view = traceView({
    lead: null,
    recovery_jobs: [{ id: "job-id", state: "retry_wait" }],
    audit_events: [],
  });
  assert.equal(view.pending, true);
  assert.equal(view.pipelineStage, "Waiting to be saved");
  assert.equal(view.rawPipelineStage, "not_created");
  assert.equal(view.recoveryState, "Waiting to retry");
  assert.equal(view.rawRecoveryState, "retry_wait");
  assert.equal(traceView({ lead: null, recovery_jobs: [] }), null);
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
  assert.equal(view.serviceType, "Furnace service");
  assert.equal(view.rawServiceType, "furnace_service");
  assert.equal(view.needsReview, false);
  assert.equal(view.audits.length, 1);
  assert.equal(view.followUpStatus, "Scheduled");
  assert.equal(view.rawFollowUpStatus, "pending");
  assert.equal(view.bookingStatus, "Not booked");
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
    business_timezone: "America/Vancouver",
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
  assert.equal(bookingView(body, payload).followUpStatus, "Cancelled after booking");
  assert.equal(bookingView(body, payload).confirmationStateLabel, "Sent to the development inbox");
  assert.equal(verifiedBooking({ ...body, pipeline_stage: "new_lead" }, payload), false);
  assert.equal(verifiedBooking({ ...body, appointment_at: undefined }, payload), false);
  assert.equal(verifiedBooking({ ...body, appointment_at: "2026-10-20Z" }, payload), false);
  assert.equal(verifiedBooking({ ...body, business_timezone: "Asia/Kolkata" }, payload), false);
});

test("intake replay accepts truthful contacted, booked, and changed AI state", () => {
  const payload = {
    submission_id: "09f70a8e-1304-42b9-a1e6-022d2daf4bd6",
    correlation_id: "eeb1b11a-22c8-4a2f-a463-554246c14a16",
    email: "maya.verma@example.com",
  };
  const base = {
    state: "accepted",
    intake_state: "replayed",
    crm_lead_id: "d678189e-db40-46d7-89a5-4bca74dded23",
    ai_status: "fallback_invalid",
    follow_up_due_at: "2026-09-19T00:02:00Z",
    ...payload,
  };

  assert.equal(
    verifiedSuccess(
      { ...base, pipeline_stage: "contacted", follow_up_status: "sent" },
      payload,
    ),
    true,
  );
  assert.equal(
    verifiedSuccess(
      { ...base, pipeline_stage: "appointment_booked", follow_up_status: "cancelled" },
      payload,
    ),
    true,
  );
  assert.equal(
    verifiedSuccess(
      {
        ...base,
        pipeline_stage: "new_lead",
        follow_up_status: null,
        follow_up_due_at: null,
      },
      payload,
    ),
    true,
  );
});

test("known booking with unconfirmed notification remains a verified booking", () => {
  const payload = {
    booking_request_id: "09f70a8e-1304-42b9-a1e6-022d2daf4bd6",
    correlation_id: "eeb1b11a-22c8-4a2f-a463-554246c14a16",
    business_timezone: "America/Vancouver",
  };
  const body = {
    state: "booked",
    booking_state: "created",
    appointment_id: "d678189e-db40-46d7-89a5-4bca74dded23",
    appointment_at: "2026-10-20T17:30:00Z",
    business_timezone: "America/Vancouver",
    pipeline_stage: "appointment_booked",
    follow_up_status: "cancelled",
    confirmation_state: "unconfirmed",
    notification_message: "The appointment is saved, but email is unconfirmed.",
    ...payload,
  };

  assert.equal(verifiedBooking(body, payload), true);
  assert.match(bookingView(body, payload).notificationMessage, /saved/i);
  assert.equal(confirmationIsSettled("unconfirmed"), false);
  assert.equal(confirmationIsSettled("already_sent"), true);
});

test("new intake attempts cannot silently retain a previous booking customer", () => {
  const leadA = {
    correlationId: "eeb1b11a-22c8-4a2f-a463-554246c14a16",
    crmLeadId: "d678189e-db40-46d7-89a5-4bca74dded23",
    fullName: "Lead A",
  };
  const leadB = {
    correlationId: "bd88df3b-1156-483d-a8b1-bf0b73cd66bf",
    crmLeadId: "108dc96e-1f23-4a56-b6af-f3e49a311459",
    fullName: "Lead B",
  };
  const acceptedA = acceptIntakeResult(leadA);
  const attemptingB = beginIntakeAttempt(acceptedA);
  const acceptedB = acceptIntakeResult(leadB);

  assert.equal(attemptingB.acceptedLead, null);
  assert.equal(attemptingB.bookingPanelVisible, false);
  assert.equal(attemptingB.bookingResultVisible, false);
  assert.equal(acceptedB.acceptedLead.correlationId, leadB.correlationId);
  assert.equal(acceptedB.bookingResultVisible, false);
});

test("trace view clearly marks fallback records needing review", () => {
  const view = traceView({
    lead: { full_name: "Maya Verma", ai_status: "fallback_invalid", needs_review: true },
    audit_events: [],
  });

  assert.equal(view.needsReview, true);
});

test("presentation labels make raw states readable without discarding them", () => {
  assert.equal(labelFor("pipeline", "appointment_booked"), "Appointment saved");
  assert.equal(labelFor("recovery", "retry_wait"), "Waiting to retry");
  assert.equal(labelFor("recovery", "future_state"), "Future state");
  assert.equal(serviceLabel("air_conditioning_service"), "Air conditioning service");
});
