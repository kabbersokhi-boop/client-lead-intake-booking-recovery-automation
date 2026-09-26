const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const workflow = JSON.parse(fs.readFileSync(path.join(__dirname, "..", "highlevel-stage-sync.json"), "utf8"));
const nodes = Object.fromEntries(workflow.nodes.map((node) => [node.name, node]));

test("stage sync stays scheduled, protected, finite, and sanitized", () => {
  assert.equal(workflow.active, false);
  assert.equal(workflow.settings.errorWorkflow, "phase3-crm-recovery-error");
  assert.equal(nodes["Stage Sync Schedule"].type, "n8n-nodes-base.scheduleTrigger");
  assert.equal(nodes["Claim One Due Stage Sync"].parameters.url.includes("/api/stage-sync/claim"), true);
  assert.equal(nodes["Claim One Due Stage Sync"].alwaysOutputData, true);
  assert.equal(workflow.connections["Stage Sync Claimed?"].main[1][0].node, "No Due Stage Sync");
  assert.equal(nodes["Reconcile and Verify HighLevel Stage"].parameters.url.includes("/process"), true);
  assert.equal(nodes["Reconcile and Verify HighLevel Stage"].parameters.options.timeout, 160000);
  const serialized = JSON.stringify(workflow);
  assert.doesNotMatch(serialized, /Bearer [A-Za-z0-9_-]{20,}|nvapi-[A-Za-z0-9_-]+/);
  assert.equal(workflow.nodes.every((node) => !("credentials" in node)), true);
});

function validate(result, claim) {
  const code = nodes["Validate Durable Stage Result"].parameters.jsCode;
  const context = { $json: result, $: () => ({ first: () => ({ json: claim }) }) };
  return vm.runInNewContext(`(function () { ${code} })()`, context);
}

test("workflow rejects a completed result without verified forward stage", () => {
  const claim = { desired_stage: "contacted", desired_version: 1 };
  assert.throws(() => validate({ state: "completed", desired_stage: "contacted", desired_version: 1, verified_remote_stage: "new_lead" }, claim));
  assert.throws(() => validate({ state: "completed", desired_stage: "contacted", desired_version: 0, verified_remote_stage: "contacted" }, claim));
  assert.equal(validate({ state: "completed", desired_stage: "appointment_booked", desired_version: 2, verified_remote_stage: "appointment_booked" }, claim)[0].json.state, "completed");
});
