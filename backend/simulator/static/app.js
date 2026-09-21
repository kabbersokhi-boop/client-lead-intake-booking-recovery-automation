let snapshot = null;

const escapeText = (value) => String(value ?? "").replace(/[&<>"']/g, (character) => ({
  "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
}[character]));

const fieldValue = (record, fieldId) => {
  const field = (record.customFields || []).find((candidate) => candidate.id === fieldId);
  return field?.value ?? field?.fieldValue ?? "—";
};

const eventAction = (event) => {
  if (event.method === "GET" && event.path === "/contacts/lookup") return "Contact lookup";
  if (event.method === "POST" && event.path === "/contacts/upsert") return "Contact upsert";
  if (event.method === "GET" && /^\/contacts\/sim_contact_/.test(event.path)) return "Contact verification";
  if (event.method === "GET" && event.path === "/opportunities/search") return "Opportunity search";
  if (event.method === "POST" && event.path === "/opportunities/") return "Opportunity create";
  if (event.method === "PUT" && /^\/opportunities\/sim_opportunity_/.test(event.path)) return "Opportunity update";
  return "Contract request";
};

const eventMarkup = (event) => {
  const statusClass = event.status >= 200 && event.status < 300 ? "status-ok" : "status-error";
  const detail = JSON.stringify({
    action: eventAction(event),
    simulator_request_id: event.requestId,
    submission_reference: event.submissionReference,
    retry_after: event.retryAfter,
    query: event.query,
    request: event.requestBody,
    response: event.responseBody,
  }, null, 2);
  return `<details class="event"><summary><span class="method">${escapeText(event.method)}</span><span class="action">${escapeText(eventAction(event))}</span><span class="path">${escapeText(event.path)}</span><strong class="${statusClass}">${escapeText(event.status)}</strong><time>${escapeText(new Date(event.timestamp).toLocaleTimeString())}</time></summary><pre>${escapeText(detail)}</pre></details>`;
};

function render() {
  document.querySelector("#contact-count").textContent = snapshot.contacts.length;
  document.querySelector("#opportunity-count").textContent = snapshot.opportunities.length;
  document.querySelector("#appointment-count").textContent = snapshot.appointments.length;
  const faultLabel = snapshot.fault.mode === "normal" ? "Normal" : snapshot.fault.mode.replaceAll("_", " ");
  document.querySelector("#fault-summary").textContent = faultLabel;
  document.querySelector("#fault-current").textContent = faultLabel;
  document.querySelector("#contract-profile").innerHTML = `
    <dt>API version</dt><dd>${escapeText(snapshot.contractVersion)}</dd>
    <dt>Docs reviewed</dt><dd>${escapeText(snapshot.documentationReviewDate)}</dd>
    <dt>Location</dt><dd>${escapeText(snapshot.locationId)}</dd>
    <dt>Pipeline</dt><dd>${escapeText(snapshot.pipelineId)}</dd>`;

  const recent = snapshot.events.slice(0, 5);
  document.querySelector("#recent-events").innerHTML = recent.length ? recent.map(eventMarkup).join("") : "No adapter calls observed yet.";
  document.querySelector("#recent-events").classList.toggle("empty", !recent.length);
  document.querySelector("#event-timeline").innerHTML = snapshot.events.length ? snapshot.events.map(eventMarkup).join("") : "No adapter calls observed yet.";
  document.querySelector("#event-timeline").classList.toggle("empty", !snapshot.events.length);

  const contacts = snapshot.contacts;
  document.querySelector("#contacts-table").innerHTML = contacts.length ? `<table class="table"><thead><tr><th>Name</th><th>Email / phone</th><th>Local simulator ID</th><th>Submission identity</th><th>Updated</th></tr></thead><tbody>${contacts.map((contact) => `<tr data-contact="${escapeText(contact.id)}"><td>${escapeText(contact.name)}</td><td>${escapeText(contact.email || contact.phone)}</td><td>${escapeText(contact.id)}</td><td>${escapeText(fieldValue(contact, "sim_cf_submission_id"))}</td><td>${escapeText(new Date(contact.dateUpdated).toLocaleString())}</td></tr>`).join("")}</tbody></table>` : "No contacts have been created.";
  document.querySelector("#contacts-table").classList.toggle("empty", !contacts.length);
  document.querySelectorAll("[data-contact]").forEach((row) => row.addEventListener("click", () => showContact(row.dataset.contact)));

  document.querySelector("#pipeline").innerHTML = Object.entries(snapshot.stages).map(([stageId, label]) => {
    const opportunities = snapshot.opportunities.filter((opportunity) => opportunity.pipelineStageId === stageId);
    return `<article class="stage"><h3>${escapeText(label)} <span>${opportunities.length}</span></h3>${opportunities.map((opportunity) => `<div class="opportunity-card"><strong>${escapeText(opportunity.name)}</strong><small>${escapeText(opportunity.id)}</small><small>Contact: ${escapeText(opportunity.contactId)}</small><small>Submission: ${escapeText(fieldValue(opportunity, "sim_of_submission_id"))}</small></div>`).join("")}</article>`;
  }).join("");
}

function showContact(contactId) {
  const contact = snapshot.contacts.find((candidate) => candidate.id === contactId);
  const opportunities = snapshot.opportunities.filter((candidate) => candidate.contactId === contactId);
  const detail = document.querySelector("#contact-detail");
  detail.classList.remove("hidden");
  detail.innerHTML = `<h3>${escapeText(contact.name)}</h3><dl><dt>Contact ID</dt><dd>${escapeText(contact.id)}</dd><dt>Submission</dt><dd>${escapeText(fieldValue(contact, "sim_cf_submission_id"))}</dd><dt>Correlation</dt><dd>${escapeText(fieldValue(contact, "sim_cf_correlation_id"))}</dd><dt>Linked opportunities</dt><dd>${opportunities.length}</dd><dt>Linked appointments</dt><dd>0 — sync not implemented</dd></dl>`;
}

async function refresh() {
  const response = await fetch("/simulator/api/state");
  snapshot = await response.json();
  render();
}

if (typeof document !== "undefined") {
  document.querySelectorAll(".nav-item").forEach((button) => button.addEventListener("click", () => {
    document.querySelectorAll(".nav-item, .view").forEach((element) => element.classList.remove("active"));
    button.classList.add("active");
    document.querySelector(`#${button.dataset.view}`).classList.add("active");
  }));
  document.querySelector("#refresh").addEventListener("click", refresh);
  document.querySelectorAll("[data-fault]").forEach((button) => button.addEventListener("click", async () => {
    await fetch("/simulator/api/fault", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ mode: button.dataset.fault, retry_after: Number(document.querySelector("#retry-after").value) }) });
    await refresh();
  }));
  document.querySelector("#reset").addEventListener("click", async () => {
    if (!window.confirm("Reset only the isolated simulator data?")) return;
    await fetch("/simulator/api/reset", { method: "POST" });
    document.querySelector("#contact-detail").classList.add("hidden");
    await refresh();
  });

  refresh();
  setInterval(refresh, 4000);
}

if (typeof module !== "undefined") module.exports = { eventAction, eventMarkup };
