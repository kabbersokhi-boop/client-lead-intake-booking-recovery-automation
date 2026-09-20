const test = require("node:test");
const assert = require("node:assert/strict");
const vm = require("node:vm");

const recovery = require("../crm-write-recovery.json");
const diagnostic = require("../crm-write-diagnostic.json");
const errorWorkflow = require("../crm-recovery-error.json");
const recoveryNodes = Object.fromEntries(recovery.nodes.map((node) => [node.name, node]));

function runCode(name, input, references = {}, executionId = "recovery-execution") {
  const code = recoveryNodes[name].parameters.jsCode;
  return vm.runInNewContext(`(() => { ${code} })()`, {
    $json: input,
    $: (nodeName) => ({ first: () => ({ json: references[nodeName] }) }),
    $execution: { id: executionId },
  });
}

const claim = {
  id: "09f70a8e-1304-42b9-a1e6-022d2daf4bd6",
  submission_id: "eeb1b11a-22c8-4a2f-a463-554246c14a16",
  correlation_id: "d678189e-db40-46d7-89a5-4bca74dded23",
  lease_token: "bd88df3b-1156-483d-a8b1-bf0b73cd66bf",
  payload_fingerprint: "a".repeat(64),
  payload_json: { ai_status: "enriched" },
};

function crmRecord(overrides = {}) {
  return {
    crm_lead_id: "108dc96e-1f23-4a56-b6af-f3e49a311459",
    submission_id: claim.submission_id,
    correlation_id: claim.correlation_id,
    submission_fingerprint: claim.payload_fingerprint,
    intake_state: "replayed",
    ai_status: "enriched",
    pipeline_stage: "new_lead",
    follow_up_status: "pending",
    follow_up_due_at: "2026-09-20T10:00:00Z",
    ...overrides,
  };
}

test("recovery workflow visibly claims, reconciles, obtains quota, writes, and resolves", () => {
  for (const name of [
    "Claim One Due CRM Job",
    "Reconcile by Submission Identity",
    "Confirm CRM Record Absent",
    "Defer or Hold Reconciliation",
    "Obtain Shared Quota Permission",
    "Defer Without API Attempt",
    "Record CRM API Attempt",
    "Write CRM Lead",
    "Complete Written Job",
    "Schedule Retry or Review",
  ]) {
    assert.ok(recoveryNodes[name], `missing ${name}`);
  }
  assert.equal(recoveryNodes["Write CRM Lead"].onError, "continueRegularOutput");
});

test("reconciliation binds the existing CRM result to the claimed identity", () => {
  const valid = runCode(
    "Validate Reconciliation",
    {
      crm_lead_id: "108dc96e-1f23-4a56-b6af-f3e49a311459",
      submission_id: claim.submission_id,
      correlation_id: claim.correlation_id,
      submission_fingerprint: claim.payload_fingerprint,
      intake_state: "replayed",
      ai_status: "enriched",
      pipeline_stage: "new_lead",
      follow_up_status: "pending",
      follow_up_due_at: "2026-09-20T10:00:00Z",
    },
    { "Claim One Due CRM Job": claim },
  )[0].json;
  const wrong = runCode(
    "Validate Reconciliation",
    { ...valid, crm_lead_id: "108dc96e-1f23-4a56-b6af-f3e49a311459", submission_id: claim.id },
    { "Claim One Due CRM Job": claim },
  )[0].json;
  assert.equal(valid.action, "matched");
  assert.equal(wrong.action, "defer_or_hold");
});

test("reconciliation accepts persisted replay AI while creation stays bound to stored payload", () => {
  const reconciled = runCode(
    "Validate Reconciliation",
    crmRecord({ ai_status: "fallback_invalid" }),
    { "Claim One Due CRM Job": claim },
  )[0].json;
  const replayedWrite = runCode(
    "Validate CRM Write Result",
    crmRecord({ ai_status: "fallback_invalid" }),
    { "Claim One Due CRM Job": claim },
  )[0].json;
  const mismatchedCreation = runCode(
    "Validate CRM Write Result",
    crmRecord({ intake_state: "created", ai_status: "fallback_invalid" }),
    { "Claim One Due CRM Job": claim },
  )[0].json;

  assert.equal(reconciled.action, "matched");
  assert.equal(replayedWrite.succeeded, true);
  assert.equal(mismatchedCreation.succeeded, false);
});

test("reconciliation distinguishes absence, credentials, throttling, and malformed success", () => {
  const cases = [
    [{ statusCode: 404, headers: {}, body: { detail: "Lead not found" } }, "absent", 404],
    [{ error: { status: 404 } }, "absent", 404],
    [{ error: { status: 401 } }, "defer_or_hold", 401],
    [{ error: { status: 403 } }, "defer_or_hold", 403],
    [{ error: { status: 429, headers: { "Retry-After": "120" } } }, "defer_or_hold", 429],
    [{ error: { status: 503 } }, "defer_or_hold", 503],
    [{ crm_lead_id: "108dc96e-1f23-4a56-b6af-f3e49a311459" }, "defer_or_hold", null],
  ];
  for (const [input, action, statusCode] of cases) {
    const result = runCode(
      "Validate Reconciliation",
      input,
      { "Claim One Due CRM Job": claim },
    )[0].json;
    assert.equal(result.action, action);
    assert.equal(result.status_code, statusCode);
  }
});

test("CRM write validation uses each claimed job identity and preserves Retry-After", () => {
  const success = runCode(
    "Validate CRM Write Result",
    {
      crm_lead_id: "108dc96e-1f23-4a56-b6af-f3e49a311459",
      submission_id: claim.submission_id,
      correlation_id: claim.correlation_id,
      submission_fingerprint: claim.payload_fingerprint,
      intake_state: "created",
      ai_status: "enriched",
      pipeline_stage: "new_lead",
      follow_up_status: "pending",
      follow_up_due_at: "2026-09-20T10:00:00Z",
    },
    { "Claim One Due CRM Job": claim },
  )[0].json;
  const limited = runCode(
    "Validate CRM Write Result",
    {
      statusCode: 429,
      headers: { "retry-after": "17" },
      body: { detail: "Controlled local CRM write quota exceeded." },
    },
    { "Claim One Due CRM Job": claim },
  )[0].json;
  assert.equal(success.succeeded, true);
  assert.equal(limited.succeeded, false);
  assert.equal(limited.status_code, 429);
  assert.equal(limited.retry_after, "17");
});

test("full-response write boundary validates success body and retained headers", () => {
  const response = runCode(
    "Validate CRM Write Result",
    { statusCode: 201, headers: { "content-type": "application/json" }, body: crmRecord({ intake_state: "created" }) },
    { "Claim One Due CRM Job": claim },
  )[0].json;
  assert.equal(response.succeeded, true);
  assert.equal(response.status_code, 201);
});

test("explicit non-2xx status cannot be disguised by a success-shaped body", () => {
  const written = runCode(
    "Validate CRM Write Result",
    { statusCode: 503, headers: {}, body: crmRecord({ intake_state: "created" }) },
    { "Claim One Due CRM Job": claim },
  )[0].json;
  const reconciled = runCode(
    "Validate Reconciliation",
    { statusCode: 503, headers: {}, body: crmRecord() },
    { "Claim One Due CRM Job": claim },
  )[0].json;
  assert.equal(written.succeeded, false);
  assert.equal(written.status_code, 503);
  assert.equal(reconciled.action, "defer_or_hold");
  assert.equal(reconciled.status_code, 503);
});

test("write status normalization reaches exact retry and hold classifications", () => {
  for (const statusCode of [400, 401, 403, 404, 409, 422, 429, 500, 503]) {
    const result = runCode(
      "Validate CRM Write Result",
      { error: { status: statusCode, response: { headers: { "retry-after": "9" } } } },
      { "Claim One Due CRM Job": claim },
    )[0].json;
    assert.equal(result.status_code, statusCode);
    assert.equal(result.error_class, `http_${statusCode}`);
    if (statusCode === 429) assert.equal(result.retry_after, "9");
  }
});

test("verified write status preserves created versus replayed HTTP meaning", () => {
  const created = runCode(
    "Validate CRM Write Result",
    crmRecord({ intake_state: "created" }),
    { "Claim One Due CRM Job": claim },
  )[0].json;
  const replayed = runCode(
    "Validate CRM Write Result",
    crmRecord({ intake_state: "replayed" }),
    { "Claim One Due CRM Job": claim },
  )[0].json;
  assert.equal(created.status_code, 201);
  assert.equal(replayed.status_code, 200);
  assert.match(recoveryNodes["Complete Written Job"].parameters.jsonBody, /\$json\.status_code/);
});

test("workflow binds permits and settlements to the exact lease and attempt", () => {
  const writeHeaders = Object.fromEntries(
    recoveryNodes["Write CRM Lead"].parameters.headerParameters.parameters.map((header) => [header.name, header.value]),
  );
  assert.match(writeHeaders["X-Recovery-Lease-Token"], /lease_token/);
  assert.match(recoveryNodes["Complete Written Job"].parameters.jsonBody, /attempt_id/);
  assert.match(recoveryNodes["Schedule Retry or Review"].parameters.jsonBody, /attempt_id/);
  assert.match(
    diagnostic.nodes.find((node) => node.name === "Diagnostic CRM Write Without Recovery")
      .parameters.headerParameters.parameters.find((header) => header.name === "X-CRM-Diagnostic").value,
    /controlled-local-fault/,
  );
});

test("recovery control calls use finite timeouts within the lease budget", () => {
  const controlNodes = [
    "Claim One Due CRM Job",
    "Reconcile by Submission Identity",
    "Confirm CRM Record Absent",
    "Defer or Hold Reconciliation",
    "Complete Reconciled Job",
    "Obtain Shared Quota Permission",
    "Defer Without API Attempt",
    "Record CRM API Attempt",
    "Complete Written Job",
    "Schedule Retry or Review",
  ];
  for (const name of controlNodes) {
    assert.match(recoveryNodes[name].parameters.options.timeout, /3000/);
  }
  assert.match(recoveryNodes["Write CRM Lead"].parameters.options.timeout, /6000/);
  for (const name of ["Reconcile by Submission Identity", "Write CRM Lead"]) {
    const responseOptions = recoveryNodes[name].parameters.options.response.response;
    assert.equal(responseOptions.fullResponse, true);
    assert.equal(responseOptions.neverError, true);
    assert.equal(responseOptions.responseFormat, "json");
  }
  assert.doesNotMatch(JSON.stringify(recovery), /nvidia/i);
});

test("diagnostic workflow fails naturally at the real CRM HTTP node", () => {
  const write = diagnostic.nodes.find((node) => node.name === "Diagnostic CRM Write Without Recovery");
  assert.equal(write.onError, undefined);
  assert.match(write.parameters.url, /api\/crm\/leads/);
  assert.ok(diagnostic.nodes.some((node) => node.type === "n8n-nodes-base.webhook"));
  assert.ok(diagnostic.nodes.find((node) => node.type === "n8n-nodes-base.webhook").webhookId);
});

test("error workflow uses a real Error Trigger and records without retrying", () => {
  assert.ok(errorWorkflow.nodes.some((node) => node.type === "n8n-nodes-base.errorTrigger"));
  assert.ok(errorWorkflow.nodes.some((node) => node.name === "Persist Recovery Incident"));
  assert.equal(errorWorkflow.nodes.some((node) => /retry/i.test(node.name)), false);
});

test("public workflow exports contain no embedded adapter or NVIDIA secrets", () => {
  for (const workflow of [recovery, diagnostic, errorWorkflow, require("../lead-intake.json")]) {
    const serialized = JSON.stringify(workflow);
    assert.doesNotMatch(serialized, /Bearer [A-Za-z0-9_-]{10,}/);
    assert.doesNotMatch(serialized, /X-CRM-Adapter-Key\"\s*:\s*\"(?!\=)/);
    assert.doesNotMatch(serialized, /credentialId|apiKey\"\s*:/i);
  }
});
