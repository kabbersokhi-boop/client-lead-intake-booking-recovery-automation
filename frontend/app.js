const form = document.querySelector("#enquiry-form");
const status = document.querySelector("#form-status");
const submitButton = form.querySelector("button[type=submit]");
const sampleLeadButton = document.querySelector("#sample-lead");
const intakeResult = document.querySelector("#intake-result");
const resultTitle = document.querySelector("#result-title");
const resultIntakeState = document.querySelector("#result-intake-state");
const resultCorrelationId = document.querySelector("#result-correlation-id");
const resultCrmLeadId = document.querySelector("#result-crm-lead-id");
const resultAiStatus = document.querySelector("#result-ai-status");
const resultPipelineStage = document.querySelector("#result-pipeline-stage");
const resultFollowUpStatus = document.querySelector("#result-follow-up-status");
const resultFollowUpDue = document.querySelector("#result-follow-up-due");
const inspectTraceButton = document.querySelector("#inspect-trace");
const bookingPanel = document.querySelector("#booking-panel");
const bookingCustomerReference = document.querySelector("#booking-customer-reference");
const bookingForm = document.querySelector("#booking-form");
const bookingSubmitButton = bookingForm.querySelector("button[type=submit]");
const bookingStatus = document.querySelector("#booking-status");
const bookingResult = document.querySelector("#booking-result");
const bookingResultTitle = document.querySelector("#booking-result-title");
const bookingAppointmentId = document.querySelector("#booking-appointment-id");
const bookingAppointmentTime = document.querySelector("#booking-appointment-time");
const bookingPipelineStage = document.querySelector("#booking-pipeline-stage");
const bookingFollowUpStatus = document.querySelector("#booking-follow-up-status");
const bookingConfirmationState = document.querySelector("#booking-confirmation-state");
const traceForm = document.querySelector("#trace-form");
const traceId = document.querySelector("#trace-id");
const traceSummary = document.querySelector("#trace-summary");
const technicalDetails = document.querySelector("#technical-details");
const traceRaw = document.querySelector("#trace-raw");
const pendingStorageKey = "lead-intake-pending-v1";
const pendingBookingStorageKey = "lead-booking-pending-v1";
let acceptedLead = null;
let lifecycleUiState = window.LeadIntake.beginIntakeAttempt();

const sampleLead = {
  full_name: "Maya Verma",
  email: "maya.verma@example.com",
  phone: "+1 604 555 0138",
  message:
    "Our furnace has stopped heating properly and it is around 15 years old. We are in Surrey and would prefer someone to visit Tuesday afternoon.",
};

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

function readPendingBooking() {
  try {
    return JSON.parse(sessionStorage.getItem(pendingBookingStorageKey) || "null");
  } catch {
    sessionStorage.removeItem(pendingBookingStorageKey);
    return null;
  }
}

function formatBusinessTime(value, timezone = "America/Vancouver") {
  if (!value || value === "Not applicable" || value === "Not booked") return value;
  const parsed = new Date(value);
  if (Number.isNaN(parsed.valueOf())) return value;
  return `${new Intl.DateTimeFormat("en-CA", {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone: timezone,
  }).format(parsed)} (${timezone})`;
}

function requestError(body, fallback) {
  return body && typeof body.message === "string" ? body.message : fallback;
}

function beginNewIntakeAttempt() {
  lifecycleUiState = window.LeadIntake.beginIntakeAttempt(lifecycleUiState);
  acceptedLead = null;
  intakeResult.hidden = true;
  bookingPanel.hidden = true;
  bookingResult.hidden = true;
  bookingStatus.className = "";
  bookingStatus.textContent = "";
  bookingCustomerReference.textContent = "";
  traceSummary.replaceChildren();
  technicalDetails.hidden = true;
  traceRaw.textContent = "";
  traceId.value = "";
}

function renderVerifiedResult(body, payload) {
  const view = window.LeadIntake.successView(body, payload);
  if (!view) return false;
  resultTitle.textContent = view.title;
  resultIntakeState.textContent = view.intakeState;
  resultCorrelationId.textContent = view.correlationId;
  resultCrmLeadId.textContent = view.crmLeadId;
  resultPipelineStage.textContent = view.pipelineStage;
  resultFollowUpStatus.textContent = view.followUpStatus;
  resultFollowUpDue.textContent = formatBusinessTime(view.followUpDueAt);
  resultAiStatus.textContent = `AI: ${view.aiStatus}`;
  resultAiStatus.className = `status-chip status-chip--${view.aiStatusTone}`;
  lifecycleUiState = window.LeadIntake.acceptIntakeResult({
    correlationId: view.correlationId,
    crmLeadId: view.crmLeadId,
    fullName: payload.full_name,
  });
  acceptedLead = lifecycleUiState.acceptedLead;
  intakeResult.hidden = !lifecycleUiState.intakeResultVisible;
  bookingPanel.hidden = !lifecycleUiState.bookingPanelVisible;
  bookingResult.hidden = true;
  bookingForm.reset();
  bookingStatus.className = "";
  bookingStatus.textContent = "";
  bookingCustomerReference.textContent = `Booking for ${acceptedLead.fullName} · ${acceptedLead.correlationId}`;
  return true;
}

function renderQueuedResult(body, payload) {
  const view = window.LeadIntake.queuedView(body, payload);
  if (!view) return false;
  resultTitle.textContent = view.title;
  resultIntakeState.textContent = view.intakeState;
  resultCorrelationId.textContent = view.correlationId;
  resultCrmLeadId.textContent = "Pending — no CRM lead exists yet";
  resultPipelineStage.textContent = "not created";
  resultFollowUpStatus.textContent = "not scheduled";
  resultFollowUpDue.textContent = "Not applicable";
  resultAiStatus.textContent = `Recovery: ${view.recoveryState}`;
  resultAiStatus.className = "status-chip status-chip--warning";
  intakeResult.hidden = false;
  bookingPanel.hidden = true;
  acceptedLead = null;
  return true;
}

function appendTraceField(container, label, value) {
  const item = document.createElement("div");
  const term = document.createElement("dt");
  const detail = document.createElement("dd");
  term.textContent = label;
  detail.textContent = value;
  item.append(term, detail);
  container.append(item);
}

function renderTrace(trace) {
  const view = window.LeadIntake.traceView(trace);
  traceSummary.replaceChildren();
  technicalDetails.hidden = true;
  traceRaw.textContent = "";
  if (!view) throw new Error("The enquiry has not been persisted yet. Try again shortly.");

  const overview = document.createElement("article");
  overview.className = "trace-overview";
  const heading = document.createElement("h3");
  heading.textContent = view.customer;
  const subtitle = document.createElement("p");
  subtitle.textContent = "Persisted development CRM adapter record";
  const fields = document.createElement("dl");
  fields.className = "trace-grid";
  [
    ["Contact", view.contact],
    ["Pipeline stage", view.pipelineStage],
    ["Service type", view.serviceType],
    ["Urgency", view.urgency],
    ["Preferred time", view.preferredTime],
    ["AI status", view.aiStatus],
    ["Needs review", view.needsReview ? "Yes — review required" : "No"],
    ["Client received", view.clientReceivedAt],
    ["Persisted", view.persistedAt],
    ["Follow-up status", view.followUpStatus],
    ["Follow-up due", formatBusinessTime(view.followUpDueAt)],
    ["Follow-up completed", formatBusinessTime(view.followUpCompletedAt)],
    ["Booking state", view.bookingStatus],
    ["Appointment ID", view.appointmentId],
    ["Appointment time", formatBusinessTime(view.appointmentAt, view.appointmentTimezone)],
    ["Confirmation sent", formatBusinessTime(view.confirmationSentAt)],
    ["Recovery state", view.recoveryState],
    ["Recovery job", view.recoveryJobId],
  ].forEach(([label, value]) => appendTraceField(fields, label, value));
  overview.append(heading, subtitle, fields);

  const auditHeading = document.createElement("h4");
  auditHeading.className = "audit-heading";
  auditHeading.textContent = `Audit events (${view.audits.length})`;
  const audits = document.createElement("ul");
  audits.className = "audit-list";
  view.audits.forEach((event) => {
    const item = document.createElement("li");
    const label = document.createElement("strong");
    const timestamp = document.createElement("span");
    label.textContent = `${event.event_type || "event"} · ${event.status || "unknown"}`;
    timestamp.textContent = event.created_at || "Timestamp unavailable";
    item.append(label, timestamp);
    audits.append(item);
  });
  overview.append(auditHeading, audits);
  traceSummary.append(overview);
  traceRaw.textContent = JSON.stringify(trace, null, 2);
  technicalDetails.hidden = false;
}

sampleLeadButton.addEventListener("click", () => {
  Object.entries(sampleLead).forEach(([field, value]) => {
    form.elements[field].value = value;
  });
  status.className = "";
  status.textContent = "Sample synthetic lead loaded. You can edit any field before submitting.";
  form.elements.full_name.focus();
});

bookingForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!acceptedLead) {
    bookingStatus.className = "error";
    bookingStatus.textContent = "Submit and verify a lead before booking.";
    return;
  }
  bookingStatus.className = "";
  bookingStatus.textContent = "";
  bookingSubmitButton.disabled = true;

  try {
    const configResponse = await window.LeadIntake.fetchWithTimeout(
      "/api/config",
      { headers: { Accept: "application/json" } },
      5_000,
    );
    const config = await configResponse.json().catch(() => ({}));
    if (
      !configResponse.ok ||
      typeof config.n8n_booking_webhook_url !== "string" ||
      typeof config.business_timezone !== "string"
    ) {
      throw new Error("The booking workflow is not configured.");
    }
    const selection = window.LeadIntake.bookingPendingFor(
      {
        correlation_id: acceptedLead.correlationId,
        appointment_local: bookingForm.elements.appointment_local.value,
        business_timezone: config.business_timezone,
      },
      readPendingBooking(),
      identifier,
    );
    sessionStorage.setItem(pendingBookingStorageKey, JSON.stringify(selection.pending));
    if (!selection.reused) {
      bookingStatus.textContent = "A new booking request reference was created.";
    }
    const response = await window.LeadIntake.fetchWithTimeout(
      config.n8n_booking_webhook_url,
      {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify(selection.pending.payload),
      },
      Number.isInteger(config.n8n_request_timeout_ms) ? config.n8n_request_timeout_ms : 15_000,
    );
    const body = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(requestError(body, "The appointment could not be booked."));
    const view = window.LeadIntake.bookingView(body, selection.pending.payload);
    if (!view) throw new Error("The saved appointment response could not be verified.");
    bookingResultTitle.textContent = view.title;
    bookingAppointmentId.textContent = view.appointmentId;
    bookingAppointmentTime.textContent = formatBusinessTime(
      view.appointmentAt,
      view.businessTimezone,
    );
    bookingPipelineStage.textContent = view.pipelineStage;
    bookingFollowUpStatus.textContent = view.followUpStatus;
    bookingConfirmationState.textContent = view.confirmationState;
    bookingResult.hidden = false;
    bookingStatus.className = view.confirmationState === "unconfirmed" ? "" : "success";
    bookingStatus.textContent =
      view.notificationMessage || "The booking and confirmation response were verified.";
    if (window.LeadIntake.confirmationIsSettled(view.confirmationState)) {
      sessionStorage.removeItem(pendingBookingStorageKey);
    }
    traceId.value = body.correlation_id;
  } catch (error) {
    bookingStatus.className = "error";
    bookingStatus.textContent =
      error.name === "AbortError"
        ? "The result was ambiguous. Retry unchanged to reuse the same booking request."
        : error.message || "The appointment could not be booked.";
  } finally {
    bookingSubmitButton.disabled = false;
  }
});

inspectTraceButton.addEventListener("click", () => {
  traceForm.scrollIntoView({ behavior: "smooth", block: "start" });
  traceId.focus();
});

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  beginNewIntakeAttempt();
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
    const created = renderVerifiedResult(body, pending.payload);
    const queued = !created && renderQueuedResult(body, pending.payload);
    if (!created && !queued) {
      throw new Error(
        "We could not confirm that your enquiry was saved. Please retry using the same details.",
      );
    }
    status.className = created ? "success" : "";
    status.textContent = created
      ? "The CRM response contract was verified."
      : "Your enquiry is durably queued. Refresh its trace before booking.";
    traceId.value = body.correlation_id;
    if (created) {
      clearPending();
      form.reset();
    }
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
  traceSummary.className = "";
  traceSummary.textContent = "Loading persisted trace…";

  try {
    const response = await window.LeadIntake.fetchWithTimeout(
      `/api/traces/${encodeURIComponent(traceId.value.trim())}`,
      { headers: { Accept: "application/json" } },
      5_000,
    );
    const body = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error("No trace was found for that correlation ID.");
    renderTrace(body);
  } catch (error) {
    traceSummary.className = "error";
    traceSummary.textContent = error.message || "The trace could not be retrieved.";
    technicalDetails.hidden = true;
  }
});
