const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

function element() {
  return {
    value: "",
    children: [],
    textContent: "",
    addEventListener() {},
    replaceChildren() { this.children = []; },
    append(...children) { this.children.push(...children); },
    set innerHTML(_value) { throw new Error("unsafe HTML insertion"); },
  };
}

test("stage Operations reads only safe projection and renders recorded text as text", async () => {
  const elements = new Map();
  const requests = [];
  const document = {
    getElementById(id) {
      if (!elements.has(id)) elements.set(id, element());
      return elements.get(id);
    },
    createElement() { return element(); },
  };
  const source = fs.readFileSync(path.join(__dirname, "..", "stage-sync-operations.js"), "utf8");
  vm.runInNewContext(source, {
    document,
    fetch: async (url, options) => {
      requests.push({ url, options });
      return {
        ok: true,
        json: async () => ({
          observed_at: "2026-09-27T00:00:00Z",
          items: [{
            submission_id: "4de0f2cf-309b-4a29-85dc-6cb7b1457e40",
            correlation_id: "b9741654-dbd2-4de2-8331-06ba23fdd28e",
            desired_stage: "appointment_booked", desired_version: 2,
            state: "completed", verified_remote_stage: "appointment_booked",
            attempt_count: 2, due_at: "2026-09-27T00:00:00Z",
            last_error_class: "<script>unsafe</script>", attempts: [],
          }],
        }),
      };
    },
    setTimeout: () => 1,
    clearTimeout() {},
    AbortController,
    encodeURIComponent,
  });
  await new Promise((resolve) => setImmediate(resolve));
  assert.equal(requests.length, 1);
  assert.equal(requests[0].url, "/api/operations/stage-sync");
  assert.equal(requests[0].options.method, undefined);
  const block = elements.get("stage-sync-list").children[0];
  assert.match(block.children[1].textContent, /<script>unsafe<\/script>/);
});
