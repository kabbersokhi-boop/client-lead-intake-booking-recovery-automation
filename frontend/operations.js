(function () {
  "use strict";

  const states = ["pending", "processing", "retry_wait", "completed", "blocked", "needs_review"];
  const incidentStates = ["open", "resolved"];
  const timeoutMs = 8000;
  const superseded = "operations-request-superseded";
  const timedOut = "operations-request-timed-out";
  const uuidPattern = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
  const $ = (id) => document.getElementById(id);
  let jobsPage = 1;
  let incidentsPage = 1;
  let selectedJob = null;
  let detailVersion = 0;
  let jobsController;
  let incidentsController;
  let summaryController;
  let detailController;
  let summaryObservedAt = null;
  let jobsObservedAt = null;
  let incidentsObservedAt = null;

  class ReadError extends Error {
    constructor(kind) {
      super(kind);
      this.kind = kind;
    }
  }

  function isObject(value) {
    return value !== null && typeof value === "object" && !Array.isArray(value);
  }

  function isTimestamp(value) {
    return typeof value === "string" && /(?:Z|[+-]\d{2}:\d{2})$/i.test(value) && !Number.isNaN(new Date(value).valueOf());
  }

  function isCount(value) {
    return Number.isSafeInteger(value) && value >= 0;
  }

  function isUuid(value) {
    return typeof value === "string" && uuidPattern.test(value);
  }

  function isState(value) {
    return typeof value === "string" && states.includes(value);
  }

  function validOptionalTimestamp(value) {
    return value === null || isTimestamp(value);
  }

  function validOptionalString(value) {
    return value === null || typeof value === "string";
  }

  function invalidResponse() {
    return new ReadError("invalid-response");
  }

  function validateSummary(data) {
    if (!isObject(data) || !isTimestamp(data.observed_at) || !isObject(data.job_counts) || !isCount(data.open_incident_count)) throw invalidResponse();
    for (const state of states) if (!isCount(data.job_counts[state])) throw invalidResponse();
    return data;
  }

  function validateJobListItem(job) {
    if (!isObject(job) || !isUuid(job.id) || !isUuid(job.submission_id) || !isUuid(job.correlation_id) || typeof job.operation_kind !== "string" || !isState(job.state) || !isTimestamp(job.created_at) || !isCount(job.attempt_count) || !validOptionalTimestamp(job.next_eligible_at) || !validOptionalString(job.last_error_class)) throw invalidResponse();
    return job;
  }

  function validatePage(data, expectedPage) {
    if (!isObject(data) || !isTimestamp(data.observed_at) || !isCount(data.total) || data.page !== expectedPage || data.page_size !== 25 || !Array.isArray(data.items)) throw invalidResponse();
    return data;
  }

  function validateJobs(data, expectedPage) {
    validatePage(data, expectedPage);
    data.items.forEach(validateJobListItem);
    return data;
  }

  function validateIncident(entry) {
    if (!isObject(entry) || !isUuid(entry.id) || !incidentStates.includes(entry.state) || !isTimestamp(entry.created_at) || !validOptionalTimestamp(entry.resolved_at) || typeof entry.error_class !== "string" || !validOptionalString(entry.execution_reference) || !validOptionalString(entry.execution_url) || !validOptionalString(entry.failed_node) || typeof entry.linked !== "boolean") throw invalidResponse();
    return entry;
  }

  function validateIncidents(data, expectedPage) {
    validatePage(data, expectedPage);
    data.items.forEach(validateIncident);
    return data;
  }

  function validateDetail(data, requestedId) {
    if (!isObject(data) || !isTimestamp(data.observed_at) || !isUuid(data.id) || data.id.toLowerCase() !== requestedId.toLowerCase() || !isUuid(data.submission_id) || !isUuid(data.correlation_id) || typeof data.operation_kind !== "string" || !isState(data.state) || !isTimestamp(data.created_at) || !isTimestamp(data.updated_at) || !isCount(data.attempt_count) || !isCount(data.reconciliation_failure_count) || !validOptionalTimestamp(data.next_eligible_at) || !validOptionalString(data.last_error_class) || !validOptionalString(data.last_error_message) || !validOptionalString(data.source_execution_reference) || !validOptionalString(data.source_execution_url) || typeof data.lease_expired_at_observation !== "boolean" || !Array.isArray(data.attempts) || !Array.isArray(data.incidents)) throw invalidResponse();
    if (data.completed_lead !== null && (!isObject(data.completed_lead) || !isUuid(data.completed_lead.id) || typeof data.completed_lead.full_name !== "string" || typeof data.completed_lead.pipeline_stage !== "string")) throw invalidResponse();
    data.incidents.forEach(validateIncident);
    for (const attempt of data.attempts) {
      if (!isObject(attempt) || !Number.isSafeInteger(attempt.attempt_number) || attempt.attempt_number < 1 || !isTimestamp(attempt.started_at) || !validOptionalTimestamp(attempt.finished_at) || typeof attempt.outcome !== "string" || (attempt.status_code !== null && (!Number.isSafeInteger(attempt.status_code) || attempt.status_code < 100 || attempt.status_code > 599)) || !validOptionalString(attempt.error_class) || !validOptionalString(attempt.retry_after_raw) || (attempt.retry_after_seconds !== null && !isCount(attempt.retry_after_seconds)) || !validOptionalString(attempt.execution_reference) || !validOptionalString(attempt.execution_url)) throw invalidResponse();
    }
    return data;
  }

  function formatTime(value) {
    if (!value) return "Not applicable";
    const date = new Date(value);
    return Number.isNaN(date.valueOf()) ? "Timestamp unavailable" : `${date.toLocaleString("en-CA", { timeZone: "UTC" })} UTC`;
  }

  function abort(controller, reason) {
    if (controller && !controller.signal.aborted) controller.abort(reason);
  }

  function isSuperseded(controller, error) {
    return controller.signal.aborted && controller.signal.reason === superseded && error.name === "AbortError";
  }

  async function read(url, controller) {
    const timeout = setTimeout(() => abort(controller, timedOut), timeoutMs);
    try {
      const response = await fetch(url, { headers: { Accept: "application/json" }, signal: controller.signal });
      let body;
      try {
        body = await response.json();
      } catch {
        throw new ReadError("invalid-response");
      }
      if (!response.ok) {
        if (response.status === 422) throw new ReadError("validation");
        if (response.status === 404) throw new ReadError("not-found");
        throw new ReadError("unavailable");
      }
      if (controller.signal.aborted && controller.signal.reason === timedOut) throw new ReadError("timeout");
      return body;
    } catch (error) {
      if (controller.signal.aborted && controller.signal.reason === timedOut) throw new ReadError("timeout");
      throw error;
    } finally {
      clearTimeout(timeout);
    }
  }

  function errorText(error) {
    if (error instanceof ReadError) {
      return {
        timeout: "The read timed out.",
        validation: "Enter a valid UUID and supported filter value.",
        "not-found": "The requested record was not found.",
        "invalid-response": "The operations response was incomplete or invalid.",
        unavailable: "The read is unavailable.",
      }[error.kind] || "The read is unavailable.";
    }
    return "The read is unavailable.";
  }

  function staleSuffix(observedAt, label) {
    return observedAt ? ` ${label} shown are stale from observed ${formatTime(observedAt)}.` : "";
  }

  function failure(element, prefix, error, observedAt, label) {
    element.className = "operations-status error";
    element.textContent = `${prefix} ${errorText(error)}${staleSuffix(observedAt, label)}`;
  }

  function safeExecutionUrl(reference, value) {
    if (typeof reference !== "string" || !/^[0-9]+$/.test(reference) || typeof value !== "string") return null;
    try {
      const url = new URL(value, window.location.origin);
      if (url.protocol !== "http:" || !["localhost", "127.0.0.1"].includes(url.hostname) || url.port !== "5678" || url.username || url.password || url.search || url.hash || url.pathname !== `/execution/${reference}`) return null;
      return url.href;
    } catch {
      return null;
    }
  }

  function execution(parent, reference, url) {
    if (!reference) return;
    const safeUrl = safeExecutionUrl(reference, url);
    const element = safeUrl ? document.createElement("a") : document.createElement("span");
    if (safeUrl) {
      element.href = safeUrl;
      element.target = "_blank";
      element.rel = "noopener noreferrer";
      element.textContent = `n8n execution ${reference}`;
    } else {
      element.className = "identifier";
      element.textContent = `Execution reference: ${reference}`;
    }
    parent.append(element);
  }

  async function summary() {
    abort(summaryController, superseded);
    const controller = summaryController = new AbortController();
    $("summary-status").className = "operations-status";
    $("summary-status").textContent = `Refreshing current state…${staleSuffix(summaryObservedAt, "Counts above")}`;
    try {
      const data = validateSummary(await read("/api/operations/summary", controller));
      if (summaryController !== controller) return;
      const root = $("state-counts");
      root.replaceChildren();
      states.forEach((state) => {
        const card = document.createElement("div");
        const label = document.createElement("span");
        const count = document.createElement("strong");
        label.textContent = state;
        count.textContent = String(data.job_counts[state]);
        card.append(label, count);
        root.append(card);
      });
      summaryObservedAt = data.observed_at;
      $("incident-count").textContent = `Open recovery incidents: ${data.open_incident_count}`;
      $("summary-status").className = "operations-status";
      $("summary-status").textContent = `Observed ${formatTime(data.observed_at)}. Separate requests can observe later worker progress.`;
    } catch (error) {
      if (summaryController === controller && !isSuperseded(controller, error)) failure($("summary-status"), "Current-state data is unavailable.", error, summaryObservedAt, "Counts above");
    }
  }

  function jobsUrl(page) {
    const params = new URLSearchParams({ page: String(page), page_size: "25" });
    const state = $("job-state").value;
    const lookup = $("lookup-id").value.trim();
    if (state) params.set("state", state);
    if (lookup) {
      params.set("lookup_kind", $("lookup-kind").value);
      params.set("lookup_id", lookup);
    }
    return `/api/operations/jobs?${params}`;
  }

  function jobCell(row, value, className) {
    const cell = document.createElement("td");
    cell.textContent = value || "—";
    if (className) cell.className = className;
    row.append(cell);
    return cell;
  }

  function renderJobs(data) {
    const body = $("jobs-body");
    body.replaceChildren();
    if (!data.items.length) {
      const row = document.createElement("tr");
      const cell = document.createElement("td");
      cell.colSpan = 6;
      cell.textContent = $("lookup-id").value.trim() ? "No job matches this valid identifier." : "No recorded jobs match these filters.";
      row.append(cell);
      body.append(row);
    }
    data.items.forEach((job) => {
      const row = document.createElement("tr");
      jobCell(row, job.state, `job-state job-state--${job.state}`);
      const ref = document.createElement("td");
      const select = document.createElement("button");
      select.type = "button";
      select.className = "job-select";
      select.textContent = job.id;
      select.addEventListener("click", () => detail(job.id));
      ref.className = "identifier";
      ref.append(select, document.createElement("br"), document.createTextNode(`submission: ${job.submission_id}`), document.createElement("br"), document.createTextNode(`correlation: ${job.correlation_id}`));
      row.append(ref);
      jobCell(row, formatTime(job.created_at));
      jobCell(row, String(job.attempt_count));
      jobCell(row, formatTime(job.next_eligible_at));
      jobCell(row, job.last_error_class);
      body.append(row);
    });
    jobsObservedAt = data.observed_at;
    $("jobs-status").className = "operations-status";
    $("jobs-status").textContent = `Filtered total: ${data.total}. Showing ${data.items.length} on page ${data.page}. Observed ${formatTime(data.observed_at)}.`;
    $("jobs-page").textContent = `Page ${data.page}`;
    $("jobs-previous").disabled = data.page <= 1;
    $("jobs-next").disabled = data.page * data.page_size >= data.total;
  }

  function disableJobsPager() {
    $("jobs-previous").disabled = true;
    $("jobs-next").disabled = true;
  }

  function clearDetail(message = "No job selected.") {
    selectedJob = null;
    detailVersion += 1;
    abort(detailController, superseded);
    detailController = undefined;
    const root = $("job-detail");
    root.className = "detail-empty";
    root.textContent = message;
  }

  async function jobs({ contextChanged = false } = {}) {
    if (contextChanged) clearDetail("Filter context changed. Select a matching job to inspect it.");
    abort(jobsController, superseded);
    const controller = jobsController = new AbortController();
    const requestedPage = jobsPage;
    $("jobs-status").className = "operations-status";
    $("jobs-status").textContent = `Loading filtered jobs…${staleSuffix(jobsObservedAt, "Results above")}`;
    disableJobsPager();
    try {
      const data = validateJobs(await read(jobsUrl(requestedPage), controller), requestedPage);
      if (jobsController !== controller) return;
      if (data.total > 0 && data.items.length === 0 && requestedPage > Math.ceil(data.total / data.page_size)) {
        jobsPage = 1;
        jobs();
        return;
      }
      renderJobs(data);
    } catch (error) {
      if (jobsController === controller && !isSuperseded(controller, error)) failure($("jobs-status"), "Jobs could not be read.", error, jobsObservedAt, "Results above");
    }
  }

  function field(root, label, value) {
    const item = document.createElement("div");
    const term = document.createElement("dt");
    const detail = document.createElement("dd");
    term.textContent = label;
    detail.textContent = value;
    item.append(term, detail);
    root.append(item);
  }

  function incident(entry) {
    const item = document.createElement("li");
    const title = document.createElement("strong");
    const text = document.createElement("span");
    title.textContent = `${entry.state}: ${entry.error_class || "recorded error"}`;
    text.textContent = `${entry.linked ? "linked" : "unlinked"} · recorded ${formatTime(entry.created_at)}${entry.resolved_at ? ` · resolved ${formatTime(entry.resolved_at)}` : ""}${entry.failed_node ? ` · node ${entry.failed_node}` : ""}`;
    item.append(title, text);
    execution(item, entry.execution_reference, entry.execution_url);
    return item;
  }

  function renderDetail(data) {
    const root = $("job-detail");
    root.className = "job-detail";
    root.replaceChildren();
    const observed = document.createElement("p");
    observed.className = "operations-status";
    observed.textContent = `Observed ${formatTime(data.observed_at)}.`;
    root.append(observed);
    const fields = document.createElement("dl");
    fields.className = "trace-grid";
    [["Job ID", data.id], ["Submission ID", data.submission_id], ["Correlation ID", data.correlation_id], ["Operation", data.operation_kind], ["Current state", data.state], ["Created (UTC)", formatTime(data.created_at)], ["Updated (UTC)", formatTime(data.updated_at)], ["Actual CRM write attempts", String(data.attempt_count)], ["Reconciliation failures", String(data.reconciliation_failure_count)], ["Next eligible retry (UTC)", formatTime(data.next_eligible_at)], ["Last recorded error", [data.last_error_class, data.last_error_message].filter(Boolean).join(": ") || "None"], ["CRM lead", data.completed_lead ? `${data.completed_lead.id} (${data.completed_lead.full_name}; ${data.completed_lead.pipeline_stage})` : "Pending CRM creation"], ["Lease", data.lease_expired_at_observation ? "Recorded lease was expired at observation time" : "No expired recorded lease observed"]].forEach(([label, value]) => field(fields, label, value));
    root.append(fields);
    const trace = document.createElement("a");
    trace.href = `/index.html?trace=${encodeURIComponent(data.correlation_id)}`;
    trace.textContent = "Inspect correlation lifecycle trace";
    root.append(trace);
    const source = document.createElement("p");
    execution(source, data.source_execution_reference, data.source_execution_url);
    if (source.childNodes.length) root.append(source);
    const attemptsHeading = document.createElement("h3");
    attemptsHeading.textContent = `Attempt history (${data.attempts.length})`;
    root.append(attemptsHeading);
    if (!data.attempts.length) {
      const empty = document.createElement("p");
      empty.textContent = "No actual CRM write has been attempted.";
      root.append(empty);
    }
    data.attempts.forEach((attempt) => {
      const item = document.createElement("article");
      const title = document.createElement("strong");
      const text = document.createElement("p");
      item.className = "attempt";
      title.textContent = `Attempt ${attempt.attempt_number}: ${attempt.outcome}`;
      text.textContent = `Started ${formatTime(attempt.started_at)}; finished ${formatTime(attempt.finished_at)}; HTTP ${attempt.status_code ?? "not recorded"}; error ${attempt.error_class || "none"}; Retry-After ${attempt.retry_after_raw || "not recorded"}${attempt.retry_after_seconds !== null ? ` (${attempt.retry_after_seconds}s)` : ""}.`;
      item.append(title, text);
      execution(item, attempt.execution_reference, attempt.execution_url);
      root.append(item);
    });
    const incidentsHeading = document.createElement("h3");
    incidentsHeading.textContent = `Linked incidents (${data.incidents.length})`;
    root.append(incidentsHeading);
    data.incidents.forEach((entry) => root.append(incident(entry)));
  }

  async function detail(jobId) {
    if (!isUuid(jobId)) {
      clearDetail("The selected job identifier is invalid.");
      return;
    }
    selectedJob = jobId;
    const version = ++detailVersion;
    abort(detailController, superseded);
    const controller = detailController = new AbortController();
    const root = $("job-detail");
    root.className = "detail-empty";
    root.textContent = `Loading job ${jobId}…`;
    try {
      const data = validateDetail(await read(`/api/operations/jobs/${encodeURIComponent(jobId)}`, controller), jobId);
      if (version === detailVersion && selectedJob === jobId && detailController === controller) renderDetail(data);
    } catch (error) {
      if (version === detailVersion && selectedJob === jobId && detailController === controller && !isSuperseded(controller, error)) {
        root.className = "detail-empty error";
        root.textContent = `Selected job is unavailable: ${errorText(error)}`;
      }
    }
  }

  async function incidents() {
    abort(incidentsController, superseded);
    const controller = incidentsController = new AbortController();
    const requestedPage = incidentsPage;
    $("incidents-status").className = "operations-status";
    $("incidents-status").textContent = `Loading incidents…${staleSuffix(incidentsObservedAt, "Results above")}`;
    $("incidents-previous").disabled = true;
    $("incidents-next").disabled = true;
    const params = new URLSearchParams({ state: $("incident-state").value, page: String(requestedPage), page_size: "25" });
    try {
      const data = validateIncidents(await read(`/api/operations/incidents?${params}`, controller), requestedPage);
      if (incidentsController !== controller) return;
      if (data.total > 0 && data.items.length === 0 && requestedPage > Math.ceil(data.total / data.page_size)) {
        incidentsPage = 1;
        incidents();
        return;
      }
      const list = $("incidents-list");
      list.replaceChildren();
      if (!data.items.length) {
        const empty = document.createElement("li");
        empty.textContent = "No incidents match this filter.";
        list.append(empty);
      }
      data.items.forEach((entry) => list.append(incident(entry)));
      incidentsObservedAt = data.observed_at;
      $("incidents-status").className = "operations-status";
      $("incidents-status").textContent = `Filtered total: ${data.total}. Showing ${data.items.length} on page ${data.page}. Observed ${formatTime(data.observed_at)}.`;
      $("incidents-page").textContent = `Page ${data.page}`;
      $("incidents-previous").disabled = data.page <= 1;
      $("incidents-next").disabled = data.page * data.page_size >= data.total;
    } catch (error) {
      if (incidentsController === controller && !isSuperseded(controller, error)) failure($("incidents-status"), "Incidents could not be read.", error, incidentsObservedAt, "Results above");
    }
  }

  $("refresh").addEventListener("click", () => {
    summary();
    jobs();
    incidents();
    if (selectedJob) detail(selectedJob);
  });
  $("job-filters").addEventListener("submit", (event) => {
    event.preventDefault();
    jobsPage = 1;
    jobs({ contextChanged: true });
  });
  $("incident-filters").addEventListener("submit", (event) => {
    event.preventDefault();
    incidentsPage = 1;
    incidents();
  });
  $("jobs-previous").addEventListener("click", () => {
    if (jobsPage > 1) {
      jobsPage -= 1;
      jobs();
    }
  });
  $("jobs-next").addEventListener("click", () => {
    jobsPage += 1;
    jobs();
  });
  $("incidents-previous").addEventListener("click", () => {
    if (incidentsPage > 1) {
      incidentsPage -= 1;
      incidents();
    }
  });
  $("incidents-next").addEventListener("click", () => {
    incidentsPage += 1;
    incidents();
  });
  summary();
  jobs();
  incidents();
})();
