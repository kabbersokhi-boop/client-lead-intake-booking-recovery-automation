const form = document.querySelector("#enquiry-form");
const status = document.querySelector("#form-status");
const submitButton = form.querySelector("button");
const traceForm = document.querySelector("#trace-form");
const traceId = document.querySelector("#trace-id");
const traceResult = document.querySelector("#trace-result");

function identifier() {
  return crypto.randomUUID();
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  status.className = "";
  status.textContent = "";
  submitButton.disabled = true;

  const values = Object.fromEntries(new FormData(form));
  const payload = {
    submission_id: identifier(),
    correlation_id: identifier(),
    received_at: new Date().toISOString(),
    ...values,
  };

  try {
    const config = await fetch("/api/config").then((response) => response.json());
    const response = await fetch(config.n8n_webhook_url, {
      method: "POST",
      headers: { "Content-Type": "text/plain;charset=UTF-8" },
      body: JSON.stringify(payload),
    });
    const body = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(body.message || "We could not accept your enquiry. Please try again.");
    status.className = "success";
    status.textContent = `Enquiry received. Reference: ${body.correlation_id || payload.correlation_id}`;
    traceId.value = body.correlation_id || payload.correlation_id;
    form.reset();
  } catch (error) {
    status.className = "error";
    status.textContent = error.message || "We could not accept your enquiry. Please try again.";
  } finally {
    submitButton.disabled = false;
  }
});

traceForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  traceResult.className = "";
  traceResult.textContent = "Loading persisted trace…";

  try {
    const response = await fetch(`/api/traces/${encodeURIComponent(traceId.value.trim())}`);
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
