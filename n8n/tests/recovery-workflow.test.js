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
};

test("recovery workflow visibly claims, reconciles, obtains quota, writes, and resolves", () => {
  for (const name of [
    "Claim One Due CRM Job",
    "Reconcile by Submission Identity",
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
    },
    { "Claim One Due CRM Job": claim },
  )[0].json;
  const wrong = runCode(
    "Validate Reconciliation",
    { ...valid, crm_lead_id: "108dc96e-1f23-4a56-b6af-f3e49a311459", submission_id: claim.id },
    { "Claim One Due CRM Job": claim },
  )[0].json;
  assert.equal(valid.reconciled, true);
  assert.equal(wrong.reconciled, false);
});

test("CRM write validation uses each claimed job identity and preserves Retry-After", () => {
  const success = runCode(
    "Validate CRM Write Result",
    {
      crm_lead_id: "108dc96e-1f23-4a56-b6af-f3e49a311459",
      submission_id: claim.submission_id,
      correlation_id: claim.correlation_id,
    },
    { "Claim One Due CRM Job": claim },
  )[0].json;
  const limited = runCode(
    "Validate CRM Write Result",
    { error: { httpCode: 429, headers: { "retry-after": "17" } } },
    { "Claim One Due CRM Job": claim },
  )[0].json;
  assert.equal(success.succeeded, true);
  assert.equal(limited.succeeded, false);
  assert.equal(limited.status_code, 429);
  assert.equal(limited.retry_after, "17");
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
