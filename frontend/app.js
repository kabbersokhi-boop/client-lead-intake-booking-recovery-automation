const form = document.querySelector("#enquiry-form");
const status = document.querySelector("#form-status");
const submitButton = form.querySelector("button");

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
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const body = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(body.message || "We could not accept your enquiry. Please try again.");
    status.className = "success";
    status.textContent = `Enquiry received. Reference: ${body.correlation_id || payload.correlation_id}`;
    form.reset();
  } catch (error) {
    status.className = "error";
    status.textContent = error.message || "We could not accept your enquiry. Please try again.";
  } finally {
    submitButton.disabled = false;
  }
});
