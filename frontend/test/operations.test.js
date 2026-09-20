const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const source = fs.readFileSync(path.join(__dirname, "..", "operations.js"), "utf8");
const jobA = "11111111-1111-4111-8111-111111111111";
const jobB = "22222222-2222-4222-8222-222222222222";
const submissionA = "33333333-3333-4333-8333-333333333333";
const submissionB = "44444444-4444-4444-8444-444444444444";
const correlationA = "55555555-5555-4555-8555-555555555555";
const correlationB = "66666666-6666-4666-8666-666666666666";
const incidentId = "77777777-7777-4777-8777-777777777777";
const observed = "2026-09-20T13:43:17Z";

class Element {
  constructor(tagName = "div") {
    this.tagName = tagName.toUpperCase();
    this.children = [];
    this.listeners = new Map();
    this.className = "";
    this.disabled = false;
    this.value = "";
    this._text = "";
  }

  get childNodes() {
    return this.children;
  }

  get textContent() {
    return this._text + this.children.map((child) => child.textContent).join("");
  }

  set textContent(value) {
    this._text = String(value);
    this.children = [];
  }

  append(...nodes) {
    this.children.push(...nodes);
  }

  replaceChildren(...nodes) {
    this._text = "";
    this.children = nodes;
  }

  addEventListener(type, listener) {
    this.listeners.set(type, listener);
  }

  dispatch(type) {
    const listener = this.listeners.get(type);
    if (listener) listener({ preventDefault() {} });
  }
}

function textNode(value) {
  const node = new Element("#text");
  node.textContent = value;
  return node;
}

function response(body, status = 200) {
  return { ok: status >= 200 && status < 300, status, json: async () => body };
}

function summary(counts = {}) {
  return {
    observed_at: observed,
    job_counts: { pending: 0, processing: 0, retry_wait: 0, completed: 0, blocked: 0, needs_review: 0, ...counts },
    open_incident_count: 0,
  };
}

function job(id, state = "pending") {
  return {
    id,
    submission_id: id === jobA ? submissionA : submissionB,
    correlation_id: id === jobA ? correlationA : correlationB,
    operation_kind: "create_lead",
    state,
    created_at: observed,
    attempt_count: 0,
    next_eligible_at: null,
    last_error_class: null,
  };
}

function jobs(items = [job(jobA)], overrides = {}) {
  return { observed_at: observed, total: items.length, page: 1, page_size: 25, items, ...overrides };
}

function incidents(items = [], overrides = {}) {
  return { observed_at: observed, total: items.length, page: 1, page_size: 25, items, ...overrides };
}

function incident() {
  return {
    id: incidentId,
    job_id: jobA,
    correlation_id: correlationA,
    workflow_reference: null,
    execution_reference: null,
    execution_url: null,
    failed_node: null,
    error_class: "provider_error",
    state: "resolved",
    resolved_at: observed,
    created_at: observed,
    linked: true,
  };
}

function detail(id, state = "retry_wait", overrides = {}) {
  return {
    observed_at: observed,
    id,
    submission_id: id === jobA ? submissionA : submissionB,
    correlation_id: id === jobA ? correlationA : correlationB,
    operation_kind: "create_lead",
    state,
    created_at: observed,
    updated_at: observed,
    attempt_count: 0,
    reconciliation_failure_count: 0,
    next_eligible_at: null,
    last_error_class: null,
    last_error_message: null,
    completed_lead: null,
    lease_expired_at_observation: false,
    source_execution_reference: null,
    source_execution_url: null,
    attempts: [],
    incidents: [],
    ...overrides,
  };
}

function findAll(root, predicate, results = []) {
  if (predicate(root)) results.push(root);
  root.children.forEach((child) => findAll(child, predicate, results));
  return results;
}

function createHarness({ abortAware = true } = {}) {
  const elements = new Map();
  const ids = [
    "refresh", "summary-status", "state-counts", "incident-count", "job-state", "lookup-kind", "lookup-id", "jobs-status", "jobs-body", "jobs-page", "jobs-previous", "jobs-next", "job-detail", "incident-state", "incidents-status", "incidents-list", "incidents-page", "incidents-previous", "incidents-next", "job-filters", "incident-filters",
  ];
  ids.forEach((id) => elements.set(id, new Element()));
  elements.get("lookup-kind").value = "job_id";
  elements.get("incident-state").value = "all";
  const requests = [];
  const timers = [];
  const document = {
    getElementById: (id) => elements.get(id),
    createElement: (tagName) => new Element(tagName),
    createTextNode: textNode,
  };
  function fetch(url, options) {
    let resolve;
    let reject;
    const request = { url, options, resolve: (body, status) => resolve(response(body, status)), reject, settled: false };
    const promise = new Promise((resolvePromise, rejectPromise) => {
      resolve = (value) => { request.settled = true; resolvePromise(value); };
      reject = (error) => { request.settled = true; rejectPromise(error); };
    });
    if (abortAware) {
      options.signal.addEventListener("abort", () => {
        if (!request.settled) reject(Object.assign(new Error("aborted"), { name: "AbortError" }));
      });
    }
    requests.push(request);
    return promise;
  }
  const context = {
    AbortController,
    URL,
    URLSearchParams,
    Date,
    Number,
    Error,
    Promise,
    document,
    fetch,
    window: { location: { origin: "http://localhost:18000" } },
    setTimeout(callback) { const timer = { callback, cleared: false }; timers.push(timer); return timer; },
    clearTimeout(timer) { timer.cleared = true; },
  };
  vm.runInNewContext(source, context, { filename: "operations.js" });
  return {
    elements,
    requests,
    timers,
    findRequest(fragment, start = 0) { return requests.slice(start).find((entry) => entry.url.includes(fragment)); },
    async flush() { for (let index = 0; index < 8; index += 1) await Promise.resolve(); },
    firePendingTimers() { timers.filter((timer) => !timer.cleared).forEach((timer) => timer.callback()); },
  };
}

async function settleInitial(harness, initialJobs = jobs()) {
  harness.findRequest("/summary").resolve(summary({ pending: 1 }));
  harness.findRequest("/jobs?").resolve(initialJobs);
  harness.findRequest("/incidents?").resolve(incidents([incident()]));
  await harness.flush();
}

test("operations browser code uses only read projections and safe DOM rendering", () => {
  assert.match(source, /\/api\/operations\/summary/);
  assert.match(source, /\/api\/operations\/jobs/);
  assert.match(source, /\/api\/operations\/incidents/);
  assert.doesNotMatch(source, /\b(?:POST|PUT|PATCH|DELETE)\b/);
  assert.doesNotMatch(source, /innerHTML|CRM_ADAPTER_API_KEY|lease_token|payload_json/);
  assert.match(source, /textContent/);
});

test("successful refresh re-reads selected detail and labels its observation", async () => {
  const harness = createHarness();
  await settleInitial(harness);
  const select = findAll(harness.elements.get("jobs-body"), (node) => node.className === "job-select")[0];
  select.dispatch("click");
  harness.findRequest(`/jobs/${jobA}`).resolve(detail(jobA));
  await harness.flush();
  assert.match(harness.elements.get("job-detail").textContent, /retry_wait/);

  const beforeRefresh = harness.requests.length;
  harness.elements.get("refresh").dispatch("click");
  assert.match(harness.elements.get("summary-status").textContent, /Counts above shown are stale/);
  harness.findRequest("/summary", beforeRefresh).resolve(summary({ completed: 1 }));
  harness.findRequest("/jobs?", beforeRefresh).resolve(jobs([job(jobA, "completed")]));
  harness.findRequest("/incidents?", beforeRefresh).resolve(incidents());
  harness.findRequest(`/jobs/${jobA}`, beforeRefresh).resolve(detail(jobA, "completed", { observed_at: "2026-09-20T14:00:00Z" }));
  await harness.flush();
  assert.match(harness.elements.get("job-detail").textContent, /Current statecompleted/);
  assert.match(harness.elements.get("job-detail").textContent, /Observed/);
});

test("filtering clears an old selection and delayed detail cannot overwrite unknown lookup", async () => {
  const harness = createHarness({ abortAware: false });
  await settleInitial(harness);
  const select = findAll(harness.elements.get("jobs-body"), (node) => node.className === "job-select")[0];
  select.dispatch("click");
  const oldDetail = harness.findRequest(`/jobs/${jobA}`);
  harness.elements.get("lookup-id").value = "88888888-8888-4888-8888-888888888888";
  const oldRequestCount = harness.requests.length;
  harness.elements.get("job-filters").dispatch("submit");
  assert.match(harness.elements.get("job-detail").textContent, /Filter context changed/);
  harness.findRequest("/jobs?", oldRequestCount).resolve(jobs([]));
  oldDetail.resolve(detail(jobA));
  await harness.flush();
  assert.match(harness.elements.get("jobs-body").textContent, /No job matches this valid identifier/);
  assert.doesNotMatch(harness.elements.get("job-detail").textContent, /retry_wait/);
});

test("draft job and incident controls do not affect Refresh or the selected detail", async () => {
  const harness = createHarness();
  await settleInitial(harness);
  const select = findAll(harness.elements.get("jobs-body"), (node) => node.className === "job-select")[0];
  select.dispatch("click");
  harness.findRequest(`/jobs/${jobA}`).resolve(detail(jobA));
  await harness.flush();

  harness.elements.get("job-state").value = "blocked";
  harness.elements.get("lookup-kind").value = "correlation_id";
  harness.elements.get("lookup-id").value = "88888888-8888-4888-8888-888888888888";
  harness.elements.get("incident-state").value = "open";
  const refreshStart = harness.requests.length;
  harness.elements.get("refresh").dispatch("click");
  const refreshRequests = harness.requests.slice(refreshStart);
  const jobsRequest = refreshRequests.find((request) => request.url.includes("/jobs?"));
  const incidentsRequest = refreshRequests.find((request) => request.url.includes("/incidents?"));
  assert.doesNotMatch(jobsRequest.url, /blocked|lookup_id|correlation_id/);
  assert.match(incidentsRequest.url, /state=all/);
  refreshRequests.find((request) => request.url.includes("/summary")).resolve(summary());
  jobsRequest.resolve(jobs([job(jobA)]));
  incidentsRequest.resolve(incidents());
  refreshRequests.find((request) => request.url.includes(`/jobs/${jobA}`)).resolve(detail(jobA, "completed"));
  await harness.flush();
  assert.match(harness.elements.get("job-detail").textContent, /Current statecompleted/);
});

test("applying a query removes stale rows and stale row clicks cannot recreate selection", async () => {
  const harness = createHarness({ abortAware: false });
  await settleInitial(harness);
  const staleSelect = findAll(harness.elements.get("jobs-body"), (node) => node.className === "job-select")[0];
  harness.elements.get("lookup-id").value = "88888888-8888-4888-8888-888888888888";
  const applyStart = harness.requests.length;
  harness.elements.get("job-filters").dispatch("submit");
  assert.equal(harness.elements.get("jobs-body").children.length, 0);
  assert.match(harness.elements.get("job-detail").textContent, /Filter context changed/);
  staleSelect.dispatch("click");
  assert.equal(harness.requests.length, applyStart + 1);
  harness.findRequest("/jobs?", applyStart).resolve(jobs([]));
  await harness.flush();
  assert.match(harness.elements.get("jobs-body").textContent, /No job matches this valid identifier/);
  assert.doesNotMatch(harness.elements.get("job-detail").textContent, /Loading job/);
});

test("old detail completing before a new empty query cannot restore the selection", async () => {
  const harness = createHarness({ abortAware: false });
  await settleInitial(harness);
  findAll(harness.elements.get("jobs-body"), (node) => node.className === "job-select")[0].dispatch("click");
  const oldDetail = harness.findRequest(`/jobs/${jobA}`);
  harness.elements.get("lookup-id").value = "88888888-8888-4888-8888-888888888888";
  const applyStart = harness.requests.length;
  harness.elements.get("job-filters").dispatch("submit");
  oldDetail.resolve(detail(jobA));
  await harness.flush();
  assert.match(harness.elements.get("job-detail").textContent, /Filter context changed/);
  harness.findRequest("/jobs?", applyStart).resolve(jobs([]));
  await harness.flush();
  assert.match(harness.elements.get("jobs-body").textContent, /No job matches/);
  assert.match(harness.elements.get("job-detail").textContent, /Filter context changed/);
});

test("pagination uses the applied query and safely restarts after a result set shrinks", async () => {
  const harness = createHarness();
  await settleInitial(harness, jobs([job(jobA)], { total: 26 }));
  harness.elements.get("job-state").value = "blocked";
  harness.elements.get("lookup-id").value = "88888888-8888-4888-8888-888888888888";
  const nextStart = harness.requests.length;
  harness.elements.get("jobs-next").dispatch("click");
  const pageTwo = harness.findRequest("/jobs?", nextStart);
  assert.match(pageTwo.url, /page=2/);
  assert.doesNotMatch(pageTwo.url, /blocked|lookup_id/);
  pageTwo.resolve(jobs([], { total: 0, page: 2 }));
  await harness.flush();
  const reset = harness.findRequest("/jobs?", nextStart + 1);
  assert.match(reset.url, /page=1/);
  reset.resolve(jobs([]));
  await harness.flush();
  assert.equal(harness.elements.get("jobs-page").textContent, "Page 1");
});

test("rapid Apply leaves only the newest query generation visible", async () => {
  const harness = createHarness({ abortAware: false });
  await settleInitial(harness);
  const start = harness.requests.length;
  harness.elements.get("lookup-id").value = jobA;
  harness.elements.get("job-filters").dispatch("submit");
  harness.elements.get("lookup-id").value = jobB;
  harness.elements.get("job-filters").dispatch("submit");
  const first = harness.requests[start];
  const second = harness.requests[start + 1];
  assert.match(first.url, new RegExp(jobA));
  assert.match(second.url, new RegExp(jobB));
  second.resolve(jobs([job(jobB)], { observed_at: "2026-09-20T15:00:00Z" }));
  first.resolve(jobs([job(jobA)], { observed_at: "2026-09-20T14:00:00Z" }));
  await harness.flush();
  assert.match(harness.elements.get("jobs-body").textContent, new RegExp(jobB));
  assert.doesNotMatch(harness.elements.get("jobs-body").textContent, new RegExp(jobA));
});

test("Previous uses the applied query after draft controls change", async () => {
  const harness = createHarness();
  await settleInitial(harness, jobs([job(jobA)], { total: 26 }));
  const nextStart = harness.requests.length;
  harness.elements.get("jobs-next").dispatch("click");
  harness.findRequest("/jobs?", nextStart).resolve(jobs([job(jobB)], { total: 26, page: 2 }));
  await harness.flush();
  harness.elements.get("job-state").value = "needs_review";
  harness.elements.get("lookup-id").value = "88888888-8888-4888-8888-888888888888";
  const previousStart = harness.requests.length;
  harness.elements.get("jobs-previous").dispatch("click");
  const previous = harness.findRequest("/jobs?", previousStart);
  assert.match(previous.url, /page=1/);
  assert.doesNotMatch(previous.url, /needs_review|lookup_id/);
  previous.resolve(jobs([job(jobA)], { total: 26 }));
  await harness.flush();
  assert.equal(harness.elements.get("jobs-page").textContent, "Page 1");
});

test("selected detail is cleared if worker progress makes it fail the applied state", async () => {
  const harness = createHarness();
  await settleInitial(harness);
  harness.elements.get("job-state").value = "pending";
  const applyStart = harness.requests.length;
  harness.elements.get("job-filters").dispatch("submit");
  harness.findRequest("/jobs?", applyStart).resolve(jobs([job(jobA)]));
  await harness.flush();
  findAll(harness.elements.get("jobs-body"), (node) => node.className === "job-select")[0].dispatch("click");
  harness.findRequest(`/jobs/${jobA}`, applyStart).resolve(detail(jobA, "pending"));
  await harness.flush();
  const refreshStart = harness.requests.length;
  harness.elements.get("refresh").dispatch("click");
  harness.findRequest("/summary", refreshStart).resolve(summary({ completed: 1 }));
  harness.findRequest("/jobs?", refreshStart).resolve(jobs([]));
  harness.findRequest("/incidents?", refreshStart).resolve(incidents());
  harness.findRequest(`/jobs/${jobA}`, refreshStart).resolve(detail(jobA, "completed"));
  await harness.flush();
  assert.match(harness.elements.get("job-detail").textContent, /no longer matches/);
});

test("a late mismatching detail cannot clear the newer selected job", async () => {
  const harness = createHarness({ abortAware: false });
  await settleInitial(harness, jobs([job(jobA), job(jobB)]));
  harness.elements.get("job-state").value = "pending";
  const applyStart = harness.requests.length;
  harness.elements.get("job-filters").dispatch("submit");
  harness.findRequest("/jobs?", applyStart).resolve(jobs([job(jobA), job(jobB)]));
  await harness.flush();
  const selects = findAll(harness.elements.get("jobs-body"), (node) => node.className === "job-select");
  const detailStart = harness.requests.length;
  selects[0].dispatch("click");
  selects[1].dispatch("click");
  const oldDetail = harness.findRequest(`/jobs/${jobA}`, detailStart);
  const currentDetail = harness.findRequest(`/jobs/${jobB}`, detailStart);
  currentDetail.resolve(detail(jobB, "pending"));
  oldDetail.resolve(detail(jobA, "completed"));
  await harness.flush();
  assert.match(harness.elements.get("job-detail").textContent, new RegExp(jobB));
  assert.doesNotMatch(harness.elements.get("job-detail").textContent, /no longer matches/);
});

test("a valid-shaped success cannot return jobs outside the applied lookup", async () => {
  const harness = createHarness();
  await settleInitial(harness);
  harness.elements.get("lookup-id").value = "88888888-8888-4888-8888-888888888888";
  const applyStart = harness.requests.length;
  harness.elements.get("job-filters").dispatch("submit");
  harness.findRequest("/jobs?", applyStart).resolve(jobs([job(jobA)]));
  await harness.flush();
  assert.match(harness.elements.get("jobs-status").textContent, /incomplete or invalid/);
  assert.equal(harness.elements.get("jobs-body").children.length, 0);
});

test("timeouts are visible for the active request while superseded reads remain quiet", async () => {
  const harness = createHarness();
  await settleInitial(harness);
  const start = harness.requests.length;
  harness.elements.get("refresh").dispatch("click");
  harness.firePendingTimers();
  await harness.flush();
  assert.match(harness.elements.get("jobs-status").textContent, /read timed out/);
  assert.match(harness.elements.get("jobs-status").textContent, /Results above shown are stale/);
  assert.equal(harness.elements.get("jobs-next").disabled, true);

  const afterTimeout = harness.requests.length;
  harness.elements.get("refresh").dispatch("click");
  harness.elements.get("refresh").dispatch("click");
  const newestSummary = harness.findRequest("/summary", afterTimeout + 3);
  newestSummary.resolve(summary({ pending: 2 }));
  harness.findRequest("/jobs?", afterTimeout + 3).resolve(jobs());
  harness.findRequest("/incidents?", afterTimeout + 3).resolve(incidents());
  await harness.flush();
  assert.doesNotMatch(harness.elements.get("summary-status").textContent, /timed out/);

  const lateHarness = createHarness({ abortAware: false });
  await settleInitial(lateHarness);
  const lateStart = lateHarness.requests.length;
  lateHarness.elements.get("refresh").dispatch("click");
  const lateSummary = lateHarness.findRequest("/summary", lateStart);
  lateHarness.firePendingTimers();
  lateSummary.resolve(summary({ completed: 9 }));
  await lateHarness.flush();
  assert.match(lateHarness.elements.get("summary-status").textContent, /read timed out/);
  assert.match(lateHarness.elements.get("state-counts").textContent, /pending1/);
});

test("malformed success, validation bodies, wrong identity, and unsafe URLs never become trusted state", async () => {
  const harness = createHarness();
  await settleInitial(harness);
  const refreshStart = harness.requests.length;
  harness.elements.get("refresh").dispatch("click");
  harness.findRequest("/summary", refreshStart).resolve({ observed_at: observed, job_counts: {}, open_incident_count: 0 });
  harness.findRequest("/jobs?", refreshStart).resolve(jobs());
  harness.findRequest("/incidents?", refreshStart).resolve(incidents());
  await harness.flush();
  assert.match(harness.elements.get("summary-status").textContent, /incomplete or invalid/);
  assert.match(harness.elements.get("state-counts").textContent, /pending1/);

  const oversizedStart = harness.requests.length;
  harness.elements.get("refresh").dispatch("click");
  harness.findRequest("/summary", oversizedStart).resolve(summary());
  harness.findRequest("/jobs?", oversizedStart).resolve(jobs(Array.from({ length: 26 }, () => job(jobA)), { total: 0 }));
  harness.findRequest("/incidents?", oversizedStart).resolve(incidents());
  await harness.flush();
  assert.match(harness.elements.get("jobs-status").textContent, /incomplete or invalid/);

  harness.elements.get("lookup-id").value = "not-a-uuid";
  const validationStart = harness.requests.length;
  harness.elements.get("job-filters").dispatch("submit");
  harness.findRequest("/jobs?", validationStart).resolve({ detail: [{ msg: "not a UUID" }] }, 422);
  await harness.flush();
  assert.match(harness.elements.get("jobs-status").textContent, /Enter a valid UUID/);
  assert.doesNotMatch(harness.elements.get("jobs-status").textContent, /\[object Object\]/);

  harness.elements.get("lookup-id").value = "";
  const listStart = harness.requests.length;
  harness.elements.get("job-filters").dispatch("submit");
  harness.findRequest("/jobs?", listStart).resolve(jobs([job(jobA)]));
  await harness.flush();
  findAll(harness.elements.get("jobs-body"), (node) => node.className === "job-select")[0].dispatch("click");
  harness.findRequest(`/jobs/${jobA}`, listStart).resolve(detail(jobB));
  await harness.flush();
  assert.match(harness.elements.get("job-detail").textContent, /incomplete or invalid/);

  const incompleteAttemptStart = harness.requests.length;
  findAll(harness.elements.get("jobs-body"), (node) => node.className === "job-select")[0].dispatch("click");
  const incompleteAttempt = detail(jobA, "completed", {
    attempts: [{ attempt_number: 1, started_at: observed, finished_at: null, outcome: "failed", status_code: 500, error_class: null, retry_after_raw: null, execution_reference: null, execution_url: null }],
  });
  harness.findRequest(`/jobs/${jobA}`, incompleteAttemptStart).resolve(incompleteAttempt);
  await harness.flush();
  assert.match(harness.elements.get("job-detail").textContent, /incomplete or invalid/);

  const nextStart = harness.requests.length;
  findAll(harness.elements.get("jobs-body"), (node) => node.className === "job-select")[0].dispatch("click");
  harness.findRequest(`/jobs/${jobA}`, nextStart).resolve(detail(jobA, "completed", {
    last_error_message: "<img src=x onerror=alert(1)>",
    attempts: [{ attempt_number: 1, started_at: observed, finished_at: null, outcome: "failed", status_code: 500, error_class: "<script>", retry_after_raw: null, retry_after_seconds: null, execution_reference: "283", execution_url: "http://example.test/execution/283" }],
  }));
  await harness.flush();
  const executionNode = findAll(harness.elements.get("job-detail"), (node) => node.textContent === "Execution reference: 283")[0];
  assert.equal(executionNode.tagName, "SPAN");
  assert.match(harness.elements.get("job-detail").textContent, /<img src=x onerror=alert\(1\)>/);
  assert.ok(harness.requests.every((request) => request.options.method === undefined));
});
