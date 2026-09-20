const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const source = fs.readFileSync(path.join(__dirname, "..", "operations.js"), "utf8");

test("operations browser code uses only read projections and safe DOM rendering", () => {
  assert.match(source, /\/api\/operations\/summary/);
  assert.match(source, /\/api\/operations\/jobs/);
  assert.match(source, /\/api\/operations\/incidents/);
  assert.doesNotMatch(source, /\b(?:POST|PUT|PATCH|DELETE)\b/);
  assert.doesNotMatch(source, /innerHTML|CRM_ADAPTER_API_KEY|lease_token|payload_json/);
  assert.match(source, /textContent/);
});

test("operations browser code protects selected-job reads from stale responses", () => {
  assert.match(source, /detailController\?\.abort\(\)/);
  assert.match(source, /version === detailVersion && selectedJob === jobId/);
  assert.match(source, /new AbortController\(\)/);
  assert.match(source, /setTimeout\(\(\) => controller\.abort\(\), 8000\)/);
});
