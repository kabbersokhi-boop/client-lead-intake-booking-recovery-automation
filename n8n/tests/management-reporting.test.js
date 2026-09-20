const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const exportDirectory = path.resolve(__dirname, "..");
const workflow = require("../management-reporting.json");
const nodes = Object.fromEntries(workflow.nodes.map((node) => [node.name, node]));

function runCode(name, input, references = {}) {
  const code = nodes[name].parameters.jsCode;
  return vm.runInNewContext(`(() => { ${code} })()`, {
    $json: input,
    $: (nodeName) => ({ first: () => ({ json: references[nodeName] }) }),
  });
}

function validReport(overrides = {}) {
  return {
    report_version: 1,
    report_type: "hvac_management_snapshot",
    report_key: "hvac-daily:2026-09-20",
    business_date: "2026-09-20",
    business_timezone: "America/Vancouver",
    window_start_utc: "2026-09-20T07:00:00Z",
    window_end_utc: "2026-09-21T07:00:00Z",
    generated_at: "2026-09-20T18:00:00Z",
    leads_received: 4,
    furnace_requests: 1,
    air_conditioning_requests: 1,
    other_or_unknown_requests: 2,
    needs_review: 1,
    appointments_booked: 2,
    follow_ups_sent: 3,
    open_recovery_incidents_at_generated_at: 1,
    ...overrides,
  };
}

test("reporting export is separate, manual-only, protected, and sanitized", () => {
  const serialized = JSON.stringify(workflow);
  assert.equal(workflow.id, "phase5-management-reporting");
  assert.equal(workflow.name, "Management Reporting - HVAC Snapshot");
  assert.equal(workflow.active, false);
  assert.equal(nodes["Run Management Report Manually"].type, "n8n-nodes-base.manualTrigger");
  assert.equal(workflow.nodes.some((node) => node.type.includes("scheduleTrigger")), false);

  const fetch = nodes["Fetch Management Summary"].parameters;
  assert.match(fetch.url, /\/api\/reporting\/management-summary/);
  assert.match(fetch.url, /\$env\.CRM_ADAPTER_URL/);
  assert.equal(fetch.headerParameters.parameters[0].value, "={{ $env.CRM_ADAPTER_API_KEY }}");
  assert.equal(fetch.options.timeout, "={{ Number($env.CRM_CONTROL_TIMEOUT_MS || 3000) }}");

  const send = nodes["Send Sanitized Report to Make"];
  assert.equal(send.parameters.url, "={{ $env.MAKE_REPORTING_WEBHOOK_URL }}");
  assert.equal(send.parameters.jsonBody, "={{ $json }}");
  assert.equal(send.parameters.options.timeout, "={{ Number($env.MAKE_REPORTING_TIMEOUT_MS || 10000) }}");
  assert.equal(send.parameters.options.response.response.fullResponse, true);
  assert.equal(send.parameters.options.response.response.neverError, true);
  assert.equal(send.parameters.options.response.response.responseFormat, "text");
  assert.equal(send.onError, "continueRegularOutput");

  assert.doesNotMatch(serialized, /https?:\/\/[^" ]*make\.com/i);
  assert.doesNotMatch(serialized, /https?:\/\/hook\.[^" ]+/i);
  assert.doesNotMatch(serialized, /customer@example|full_name|original_message|normalized_message/);
  assert.equal(workflow.nodes.every((node) => !("credentials" in node)), true);
});

test("existing customer-critical workflow exports do not reference Make reporting", () => {
  const existingExports = fs
    .readdirSync(exportDirectory)
    .filter((name) => name.endsWith(".json") && name !== "management-reporting.json");
  assert.deepEqual(existingExports.sort(), [
    "appointment-booking.json",
    "crm-recovery-error.json",
    "crm-write-diagnostic.json",
    "crm-write-recovery.json",
    "follow-up-dispatch.json",
    "lead-intake.json",
  ]);
  for (const fileName of existingExports) {
    const serialized = fs.readFileSync(path.join(exportDirectory, fileName), "utf8");
    assert.doesNotMatch(serialized, /MAKE_REPORTING_WEBHOOK_URL|Management Reporting|make\.com/i);
  }
});

test("report validation accepts only the exact minimized contract", () => {
  const report = validReport();
  const result = runCode("Validate Management Report Contract", report);
  assert.equal(result[0].json.report_key, report.report_key);
  assert.deepEqual(Object.keys(result[0].json).sort(), Object.keys(report).sort());
});

test("malformed backend reports stop before the Make node", () => {
  const invalidReports = [
    null,
    [],
    validReport({ full_name: "PII must not pass" }),
    validReport({ business_date: "2026-02-30", report_key: "hvac-daily:2026-02-30" }),
    validReport({ report_key: "random-id" }),
    validReport({ business_timezone: "UTC" }),
    validReport({ generated_at: "2026-09-20T18:00:00" }),
    validReport({
      window_start_utc: "2026-09-21T07:00:00Z",
      window_end_utc: "2026-09-22T07:00:00Z",
    }),
    validReport({ window_end_utc: "2026-09-22T07:00:00Z" }),
    validReport({ leads_received: -1 }),
    validReport({ leads_received: 1.5 }),
    validReport({ leads_received: Number.MAX_SAFE_INTEGER + 1 }),
    validReport({ other_or_unknown_requests: 1 }),
    validReport({ needs_review: { count: 1 } }),
  ];
  for (const report of invalidReports) {
    assert.throws(() => runCode("Validate Management Report Contract", report));
  }
  assert.equal(
    workflow.connections["Validate Management Report Contract"].main[0][0].node,
    "Send Sanitized Report to Make",
  );
});

test("Make 2xx is recorded only as webhook acceptance", () => {
  const report = validReport();
  const result = runCode(
    "Validate Make Webhook Result",
    { statusCode: 200, body: "Accepted", headers: {} },
    { "Validate Management Report Contract": report },
  )[0].json;
  assert.equal(result.report_key, report.report_key);
  assert.equal(result.make_webhook_accepted, true);
  assert.equal(result.make_http_status, 200);
  assert.equal("destination_updated" in result, false);
  assert.equal("google_sheets_updated" in result, false);
});

test("Make non-2xx, timeout, and network failures fail visibly", () => {
  const reportReference = { "Validate Management Report Contract": validReport() };
  assert.throws(
    () => runCode("Validate Make Webhook Result", { statusCode: 429 }, reportReference),
    /HTTP 429/,
  );
  assert.throws(
    () => runCode(
      "Validate Make Webhook Result",
      { error: { code: "ETIMEDOUT", message: "request timed out" } },
      reportReference,
    ),
    /timed out/,
  );
  assert.throws(
    () => runCode(
      "Validate Make Webhook Result",
      { error: { code: "ECONNREFUSED", message: "connection refused" } },
      reportReference,
    ),
    /network request failed/,
  );
  assert.throws(
    () => runCode(
      "Validate Make Webhook Result",
      { error: "socket disconnected" },
      reportReference,
    ),
    /network request failed/,
  );
  assert.throws(
    () => runCode("Validate Make Webhook Result", { body: "Accepted" }, reportReference),
    /no verifiable HTTP status/,
  );
});

test("reporting workflow has no customer-critical write boundary", () => {
  const serialized = JSON.stringify(workflow);
  for (const forbiddenPath of [
    "/api/crm/leads",
    "/api/lifecycle",
    "/api/recovery",
    "/api/follow-ups",
    "/api/appointments",
  ]) {
    assert.equal(serialized.includes(forbiddenPath), false);
  }
  assert.deepEqual(
    workflow.nodes.filter((node) => node.type === "n8n-nodes-base.httpRequest").map((node) => node.name),
    ["Fetch Management Summary", "Send Sanitized Report to Make"],
  );
});
