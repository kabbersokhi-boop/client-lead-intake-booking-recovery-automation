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
