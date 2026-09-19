const form = document.querySelector("#enquiry-form");
const status = document.querySelector("#form-status");
const submitButton = form.querySelector("button");
const traceForm = document.querySelector("#trace-form");
const traceId = document.querySelector("#trace-id");
const traceResult = document.querySelector("#trace-result");
const pendingStorageKey = "lead-intake-pending-v1";

function identifier() {
  return crypto.randomUUID();
}

function readPending() {
  try {
    return JSON.parse(sessionStorage.getItem(pendingStorageKey) || "null");
  } catch {
    sessionStorage.removeItem(pendingStorageKey);
    return null;
  }
}

function savePending(pending) {
  sessionStorage.setItem(pendingStorageKey, JSON.stringify(pending));
}

function clearPending() {
  sessionStorage.removeItem(pendingStorageKey);
}

function requestError(body, fallback) {
  return body && typeof body.message === "string" ? body.message : fallback;
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  status.className = "";
  status.textContent = "";
  submitButton.disabled = true;

  const values = Object.fromEntries(new FormData(form));
  const selection = window.LeadIntake.pendingFor(
    values,
    readPending(),
    identifier,
    () => new Date().toISOString(),
  );
  const pending = selection.pending;
  savePending(pending);
  if (!selection.reused) {
    status.textContent = "A new submission reference was created for these details.";
  }

  try {
    const configResponse = await window.LeadIntake.fetchWithTimeout(
      "/api/config",
      { headers: { Accept: "application/json" } },
      5_000,
    );
    const config = await configResponse.json().catch(() => ({}));
    if (!configResponse.ok || typeof config.n8n_webhook_url !== "string") {
      throw new Error("The enquiry service is not configured. Please try again later.");
    }
    const timeoutMs = Number.isInteger(config.n8n_request_timeout_ms)
      ? config.n8n_request_timeout_ms
      : 15_000;
    const response = await window.LeadIntake.fetchWithTimeout(
      config.n8n_webhook_url,
      {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify(pending.payload),
      },
      timeoutMs,
    );
    const body = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(requestError(body, "We could not accept your enquiry. Please try again."));
    }
    if (!window.LeadIntake.verifiedSuccess(body, pending.payload)) {
      throw new Error(
        "We could not confirm that your enquiry was saved. Please retry using the same details.",
      );
    }
    status.className = "success";
    status.textContent = `Enquiry received. Reference: ${body.correlation_id}`;
    traceId.value = body.correlation_id;
    clearPending();
    form.reset();
  } catch (error) {
    status.className = "error";
    if (error.name === "AbortError") {
      status.textContent =
        "We could not confirm the result in time. Retry with the same details; the same reference will be used.";
    } else {
      status.textContent = error.message || "We could not accept your enquiry. Please try again.";
    }
  } finally {
    submitButton.disabled = false;
  }
});

traceForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  traceResult.className = "";
  traceResult.textContent = "Loading persisted trace…";

  try {
    const response = await window.LeadIntake.fetchWithTimeout(
      `/api/traces/${encodeURIComponent(traceId.value.trim())}`,
      { headers: { Accept: "application/json" } },
      5_000,
    );
    const body = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error("No trace was found for that correlation ID.");
    if (!body.lead) throw new Error("The enquiry has not been persisted yet. Try again shortly.");
    traceResult.className = "success";
    traceResult.textContent = JSON.stringify(
      {
        correlation_id: body.correlation_id,
        lead: body.lead,
        audit_events: body.audit_events,
      },
      null,
      2,
    );
  } catch (error) {
    traceResult.className = "error";
    traceResult.textContent = error.message || "The trace could not be retrieved.";
  }
});
