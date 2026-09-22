const test = require("node:test");
const assert = require("node:assert/strict");
const vm = require("node:vm");

const workflow = require("../lead-intake.json");
const nodes = Object.fromEntries(workflow.nodes.map((node) => [node.name, node]));

function runCode(name, input, references = {}, environment = {}) {
  const code = nodes[name].parameters.jsCode;
  return vm.runInNewContext(`(() => { ${code} })()`, {
    $json: input,
    $: (nodeName) => ({ first: () => ({ json: references[nodeName] }) }),
    $env: environment,
    $execution: { id: "execution-fixture-1" },
  });
}

function buildNvidiaRequest(environment = { NVIDIA_NIM_MODEL: "openai/gpt-oss-20b" }) {
  const expression = nodes["Extract Service Context with NVIDIA NIM"].parameters.jsonBody;
  assert.match(expression, /^=\{\{[\s\S]*\}\}$/);
  return vm.runInNewContext(`(${expression.slice(3, -2)})`, {
    $env: environment,
    $: (nodeName) => ({ first: () => ({ json: { lead: { normalized_message: lead.normalized_message } } }) }),
  });
}

test("NVIDIA request uses structured JSON and low reasoning within existing bounds", () => {
  const request = buildNvidiaRequest();
  const node = nodes["Extract Service Context with NVIDIA NIM"];
  assert.match(node.parameters.jsonBody, /model: \$env\.NVIDIA_NIM_MODEL/);
  assert.equal(request.model, "openai/gpt-oss-20b");
  assert.equal(request.temperature, 0);
  assert.equal(request.max_tokens, 180);
  assert.equal(request.reasoning_effort, "low");
  assert.equal(request.response_format.type, "json_object");
  assert.equal(node.parameters.options.timeout, "={{ Number($env.NVIDIA_NIM_TIMEOUT_MS || 18000) }}");
});

const lead = {
  submission_id: "09f70a8e-1304-42b9-a1e6-022d2daf4bd6",
  correlation_id: "eeb1b11a-22c8-4a2f-a463-554246c14a16",
  received_at: "2026-09-19T00:00:00.000Z",
  full_name: "Maya Verma",
  email: "maya.verma@example.com",
  phone: "+1 604 555 0138",
  original_message: "  Furnace not heating. ",
  normalized_message: "Furnace not heating.",
};

test("exported validation code rejects wrong types and punctuation-only phone", () => {
  const wrongType = runCode("Validate Required Fields", { body: JSON.stringify({ ...lead, message: lead.original_message, email: 123 }) })[0].json;
  const punctuationPhone = runCode("Validate Required Fields", { body: JSON.stringify({ ...lead, message: lead.original_message, email: null, phone: "+++++++" }) })[0].json;
  assert.equal(wrongType.input_valid, false);
  assert.equal(punctuationPhone.input_valid, false);
});

test("exported normalization preserves source message separately", () => {
  const result = runCode("Normalize Contact Data", { request: { ...lead, message: lead.original_message } })[0].json.lead;
  assert.equal(result.original_message, "  Furnace not heating. ");
  assert.equal(result.normalized_message, "Furnace not heating.");
});

test("exported AI parsing accepts valid structured JSON", () => {
  const content = JSON.stringify({ service_type: "furnace_service", location: "Surrey", preferred_time: "Tuesday afternoon", urgency: "medium", summary: "Older furnace is not heating." });
  const result = runCode(
    "Validate AI Extraction",
    { choices: [{ message: { content } }] },
    { "Normalize Contact Data": { lead } },
    { NVIDIA_NIM_MODEL: "example/model" },
  )[0].json.crmPayload;
  assert.equal(result.ai_status, "enriched");
  assert.deepEqual(Object.keys(result.enrichment), ["service_type", "location", "preferred_time", "urgency", "summary"]);
  assert.equal(result.enrichment.location, "Surrey");
  assert.equal(result.provider_metadata.outcome_class, "enriched");
});

test("exported AI parsing safely handles malformed JSON and missing keys", () => {
  for (const content of ["not JSON", JSON.stringify({ service_type: "furnace_service" })]) {
    const result = runCode(
      "Validate AI Extraction",
      { choices: [{ message: { content } }] },
      { "Normalize Contact Data": { lead } },
      { NVIDIA_NIM_MODEL: "example/model" },
    )[0].json.crmPayload;
    assert.equal(result.ai_status, "fallback_invalid");
    assert.equal(result.needs_review, true);
    assert.equal(result.enrichment, null);
  }
});

test("exported AI parsing rejects extra keys, unsupported enums, and invalid field types", () => {
  const valid = {
    service_type: "furnace_service",
    location: "Surrey",
    preferred_time: "Tuesday afternoon",
    urgency: "medium",
    summary: "Older furnace is not heating.",
  };
  const invalid = [
    { ...valid, unexpected: "extra" },
    { ...valid, service_type: "roofing_service" },
    { ...valid, urgency: "critical" },
    { ...valid, location: 42 },
    { ...valid, preferred_time: false },
    { ...valid, summary: ["not", "text"] },
  ];
  for (const extraction of invalid) {
    const result = runCode(
      "Validate AI Extraction",
      { choices: [{ message: { content: JSON.stringify(extraction) } }] },
      { "Normalize Contact Data": { lead } },
      { NVIDIA_NIM_MODEL: "example/model" },
    )[0].json.crmPayload;
    assert.equal(result.ai_status, "fallback_invalid");
    assert.equal(result.needs_review, true);
    assert.equal(result.enrichment, null);
  }
});

test("exported AI parsing records a provider error as fallback unavailable", () => {
  const result = runCode(
    "Validate AI Extraction",
    { error: { httpCode: 401, code: "unauthorized" } },
    { "Normalize Contact Data": { lead } },
    { NVIDIA_NIM_MODEL: "example/model" },
  )[0].json.crmPayload;
  assert.equal(result.ai_status, "fallback_unavailable");
  assert.equal(result.provider_metadata.outcome_class, "provider_error");
  assert.equal(result.provider_metadata.status_code, 401);
});

test("exported CRM acknowledgement code rejects an unexpected 2xx shape", () => {
  const expected = { ...lead, ai_status: "enriched" };
  const result = runCode(
    "Build Intake Result",
    { status: "ok" },
    { "Validate AI Extraction": { crmPayload: expected } },
  )[0].json;
  assert.equal(result.status_code, 502);
});

test("exported CRM acknowledgement safely rejects null, arrays, and primitives", () => {
  for (const value of [null, [], "ok", 1, true]) {
    const result = buildIntakeResult(value);
    assert.equal(result.status_code, 502);
  }
});

function buildIntakeResult(crm, expectedOverrides = {}) {
  return runCode(
    "Build Intake Result",
    crm,
    { "Validate AI Extraction": { crmPayload: { ...lead, ai_status: "enriched", ...expectedOverrides } } },
  )[0].json;
}

test("intake acknowledgement separates created and replayed lifecycle invariants", () => {
  const base = {
    crm_lead_id: "d678189e-db40-46d7-89a5-4bca74dded23",
    submission_id: lead.submission_id,
    correlation_id: lead.correlation_id,
    ai_status: "enriched",
    pipeline_stage: "new_lead",
    follow_up_status: "pending",
    follow_up_due_at: "2026-09-19T00:02:00Z",
  };
  assert.equal(buildIntakeResult({ ...base, intake_state: "created" }).status_code, 201);
  assert.equal(buildIntakeResult({ ...base, intake_state: "replayed" }).status_code, 200);

  const contacted = buildIntakeResult({
    ...base,
    intake_state: "replayed",
    pipeline_stage: "contacted",
    follow_up_status: "sent",
  });
  const booked = buildIntakeResult({
    ...base,
    intake_state: "replayed",
    pipeline_stage: "appointment_booked",
    follow_up_status: "cancelled",
  });
  assert.equal(contacted.status_code, 200);
  assert.equal(booked.status_code, 200);
});

test("intake acknowledgement accepts only identity-bound queued receipts without a CRM id", () => {
  const queued = buildIntakeResult({
    state: "received",
    intake_state: "queued",
    recovery_job_id: "d678189e-db40-46d7-89a5-4bca74dded23",
    recovery_state: "retry_wait",
    submission_id: lead.submission_id,
    correlation_id: lead.correlation_id,
  });
  assert.equal(queued.status_code, 202);
  assert.equal(queued.response_body.crm_lead_id, undefined);
  assert.equal(buildIntakeResult({ ...queued.response_body, correlation_id: "wrong" }).status_code, 502);
  assert.equal(buildIntakeResult({ ...queued.response_body, crm_lead_id: queued.response_body.recovery_job_id }).status_code, 502);
});

test("intake replay trusts persisted AI state and permits a legacy missing follow-up", () => {
  const replay = buildIntakeResult(
    {
      crm_lead_id: "d678189e-db40-46d7-89a5-4bca74dded23",
      submission_id: lead.submission_id,
      correlation_id: lead.correlation_id,
      intake_state: "replayed",
      ai_status: "fallback_invalid",
      pipeline_stage: "new_lead",
      follow_up_status: null,
      follow_up_due_at: null,
    },
    { ai_status: "enriched" },
  );
  assert.equal(replay.status_code, 200);
  assert.equal(replay.response_body.ai_status, "fallback_invalid");
});

test("intake creation acknowledges the canonical stored AI payload", () => {
  const created = buildIntakeResult(
    {
      crm_lead_id: "d678189e-db40-46d7-89a5-4bca74dded23",
      submission_id: lead.submission_id,
      correlation_id: lead.correlation_id,
      intake_state: "created",
      ai_status: "enriched",
      pipeline_stage: "new_lead",
      follow_up_status: "pending",
      follow_up_due_at: "2026-09-19T00:02:00Z",
    },
    { ai_status: "fallback_invalid" },
  );
  assert.equal(created.status_code, 201);
  assert.equal(created.response_body.ai_status, "enriched");
});

test("intake replay rejects lifecycle combinations the browser rejects", () => {
  const base = {
    crm_lead_id: "d678189e-db40-46d7-89a5-4bca74dded23",
    submission_id: lead.submission_id,
    correlation_id: lead.correlation_id,
    intake_state: "replayed",
    ai_status: "enriched",
    follow_up_due_at: "2026-09-19T00:02:00Z",
  };
  assert.equal(buildIntakeResult({ ...base, pipeline_stage: "new_lead", follow_up_status: "sent" }).status_code, 502);
  assert.equal(buildIntakeResult({ ...base, pipeline_stage: "new_lead", follow_up_status: "cancelled" }).status_code, 502);
});

const bookingWorkflow = require("../appointment-booking.json");
const bookingNodes = Object.fromEntries(bookingWorkflow.nodes.map((node) => [node.name, node]));

function runBookingCode(name, input, references = {}) {
  const code = bookingNodes[name].parameters.jsCode;
  return vm.runInNewContext(`(() => { ${code} })()`, {
    $json: input,
    $: (nodeName) => ({ first: () => ({ json: references[nodeName] }) }),
  });
}

test("booking validation enforces ids, local time shape, and business timezone", () => {
  const valid = runBookingCode("Validate Booking Request", {
    body: {
      booking_request_id: "09f70a8e-1304-42b9-a1e6-022d2daf4bd6",
      correlation_id: "eeb1b11a-22c8-4a2f-a463-554246c14a16",
      appointment_local: "2026-10-20T10:30",
      business_timezone: "America/Vancouver",
    },
  })[0].json;
  const wrongTimezone = runBookingCode("Validate Booking Request", {
    body: { ...valid.request, business_timezone: "Asia/Kolkata" },
  })[0].json;

  assert.equal(valid.input_valid, true);
  assert.equal(wrongTimezone.input_valid, false);
});

test("booking result accepts created and replayed confirmations without weakening identity", () => {
  const request = {
    booking_request_id: "09f70a8e-1304-42b9-a1e6-022d2daf4bd6",
    correlation_id: "eeb1b11a-22c8-4a2f-a463-554246c14a16",
  };
  const booking = {
    appointment_id: "d678189e-db40-46d7-89a5-4bca74dded23",
    appointment_status: "booked",
    booking_state: "created",
    pipeline_stage: "appointment_booked",
    follow_up_status: "cancelled",
    appointment_at: "2026-10-20T17:30:00Z",
    business_timezone: "America/Vancouver",
    confirmation_state: "pending",
    ...request,
  };
  const result = runBookingCode(
    "Build Booking Result",
    {
      appointment_id: booking.appointment_id,
      correlation_id: booking.correlation_id,
      state: "sent",
      pipeline_stage: "appointment_booked",
      sent_at: "2026-09-19T19:10:21Z",
    },
    {
      "Route Appointment Result": { ...booking, proceed: true },
    },
  )[0].json;

  assert.equal(result.status_code, 201);
  assert.equal(result.response_body.follow_up_status, "cancelled");
});

test("booking routing preserves a controlled backend conflict and stops confirmation", () => {
  const result = routeBooking({
    error: { status: 409, message: "conflict" },
  });

  assert.equal(result.proceed, false);
  assert.equal(result.status_code, 409);
  assert.match(result.response_body.message, /different active appointment/i);
});

function routeBooking(booking, requestOverrides = {}) {
  const request = {
    booking_request_id: "09f70a8e-1304-42b9-a1e6-022d2daf4bd6",
    correlation_id: "eeb1b11a-22c8-4a2f-a463-554246c14a16",
    appointment_local: "2026-10-20T10:30",
    business_timezone: "America/Vancouver",
    ...requestOverrides,
  };
  return runBookingCode(
    "Route Appointment Result",
    booking,
    { "Validate Booking Request": { request } },
  )[0].json;
}

function validBookingResponse(overrides = {}) {
  return {
    appointment_id: "d678189e-db40-46d7-89a5-4bca74dded23",
    booking_request_id: "09f70a8e-1304-42b9-a1e6-022d2daf4bd6",
    correlation_id: "eeb1b11a-22c8-4a2f-a463-554246c14a16",
    booking_state: "created",
    appointment_status: "booked",
    appointment_at: "2026-10-20T17:30:00Z",
    business_timezone: "America/Vancouver",
    pipeline_stage: "appointment_booked",
    follow_up_status: "cancelled",
    confirmation_state: "pending",
    ...overrides,
  };
}

test("booking routing rejects malformed successful responses before confirmation", () => {
  for (const response of [
    {},
    validBookingResponse({ appointment_at: undefined }),
    validBookingResponse({ appointment_at: "not-a-date" }),
    validBookingResponse({ appointment_at: "2026-10-20Z" }),
    validBookingResponse({ business_timezone: "Asia/Kolkata" }),
    validBookingResponse({ correlation_id: "bd88df3b-1156-483d-a8b1-bf0b73cd66bf" }),
    validBookingResponse({ booking_request_id: "bd88df3b-1156-483d-a8b1-bf0b73cd66bf" }),
  ]) {
    const routed = routeBooking(response);
    assert.equal(routed.proceed, false);
    assert.equal(routed.status_code, 502);
  }
});

test("booking routing preserves installed n8n error-envelope business statuses", () => {
  for (const [status, pattern] of [
    [404, /could not be found/i],
    [409, /different active appointment/i],
    [422, /valid future appointment/i],
  ]) {
    const routed = routeBooking({ error: { status, message: `${status} - safe fixture` } });
    assert.equal(routed.proceed, false);
    assert.equal(routed.status_code, status);
    assert.match(routed.response_body.message, pattern);
  }
});

test("only the verified booking branch can call confirmation", () => {
  const outputs = bookingWorkflow.connections["Appointment Created?"].main;
  assert.equal(outputs[0][0].node, "Send Booking Confirmation Test Email");
  assert.equal(outputs[1][0].node, "Return Booking Result");
  assert.equal(routeBooking({}).proceed, false);
});

test("known booking remains successful when confirmation is unverified", () => {
  const booking = { ...validBookingResponse(), proceed: true };
  for (const confirmation of [
    { error: { status: 503, message: "transport unavailable" } },
    { state: "sent" },
    {
      appointment_id: "bd88df3b-1156-483d-a8b1-bf0b73cd66bf",
      correlation_id: booking.correlation_id,
      state: "sent",
      pipeline_stage: "appointment_booked",
      sent_at: "2026-09-19T19:10:21Z",
    },
  ]) {
    const result = runBookingCode(
      "Build Booking Result",
      confirmation,
      { "Route Appointment Result": booking },
    )[0].json;
    assert.equal(result.status_code, 202);
    assert.equal(result.response_body.state, "booked");
    assert.equal(result.response_body.appointment_id, booking.appointment_id);
    assert.equal(result.response_body.appointment_at, booking.appointment_at);
    assert.equal(result.response_body.confirmation_state, "unconfirmed");
  }
});

test("confirmation success, skip, and replay bind to the verified appointment", () => {
  const booking = { ...validBookingResponse(), proceed: true };
  for (const state of ["sent", "already_sent", "skipped_no_email"]) {
    const result = runBookingCode(
      "Build Booking Result",
      {
        appointment_id: booking.appointment_id,
        correlation_id: booking.correlation_id,
        state,
        pipeline_stage: "appointment_booked",
        sent_at: state === "skipped_no_email" ? null : "2026-09-19T19:10:21Z",
      },
      { "Route Appointment Result": booking },
    )[0].json;
    assert.equal(result.status_code, 201);
    assert.equal(result.response_body.confirmation_state, state);
  }
});

const followUpWorkflow = require("../follow-up-dispatch.json");
const followUpNodes = Object.fromEntries(followUpWorkflow.nodes.map((node) => [node.name, node]));

test("follow-up selector emits only pending records", () => {
  const code = followUpNodes["Select Due Pending Follow-ups"].parameters.jsCode;
  const result = vm.runInNewContext(`(() => { ${code} })()`, {
    $input: {
      all: () => [
        { json: [{ id: "due", status: "pending" }, { id: "done", status: "sent" }] },
      ],
    },
  });
  assert.equal(result.length, 1);
  assert.equal(result[0].json.id, "due");
});
