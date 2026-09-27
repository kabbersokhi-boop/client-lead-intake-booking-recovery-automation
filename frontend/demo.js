const readinessTitle = document.querySelector("#readiness-title");
const readinessChecks = document.querySelector("#readiness-checks");
const result = document.querySelector("#scenario-result");
const resultTitle = document.querySelector("#scenario-result-title");
const verdict = document.querySelector("#scenario-verdict");
const explanation = document.querySelector("#scenario-explanation");
const timeline = document.querySelector("#scenario-timeline");
const evidence = document.querySelector("#scenario-evidence");

async function loadReadiness() {
  try {
    const response = await fetch("/api/demo/readiness");
    const body = await response.json();
    if (!response.ok) throw new Error(body.detail || "Readiness check failed");
    readinessTitle.textContent = body.ready ? "All demo boundaries are ready" : "The demo stack is not ready";
    readinessChecks.replaceChildren(...Object.entries(body.checks).map(([name, check]) => {
      const item = document.createElement("span");
      item.className = check.ready ? "ready" : "";
      item.textContent = `${check.ready ? "✓" : "×"} ${name}`;
      return item;
    }));
    document.querySelectorAll(".scenario button").forEach((button) => { button.disabled = !body.ready; });
    if (!body.ready) window.setTimeout(loadReadiness, 2000);
  } catch (error) {
    readinessTitle.textContent = error.message;
    document.querySelectorAll(".scenario button").forEach((button) => { button.disabled = true; });
    window.setTimeout(loadReadiness, 2000);
  }
}

function renderScenario(body, card) {
  result.hidden = false;
  resultTitle.textContent = body.scenario.replaceAll("_", " ").replace(/^./, (value) => value.toUpperCase());
  verdict.textContent = body.verified ? "VERIFIED" : "CHECK FAILED";
  verdict.className = `status-chip status-chip--${body.verified ? "success" : "warning"}`;
  explanation.textContent = body.business_explanation;
  timeline.replaceChildren(...body.timeline.map((entry) => {
    const item = document.createElement("li");
    const dot = document.createElement("span"); dot.className = "dot";
    const label = document.createElement("span"); label.textContent = entry.step;
    const observed = document.createElement("code"); observed.textContent = String(entry.observed);
    item.append(dot, label, observed);
    return item;
  }));
  evidence.textContent = JSON.stringify({
    submission_id: body.submission_id,
    correlation_id: body.correlation_id,
    ...body.authoritative_evidence,
  }, null, 2);
  card.classList.add(body.verified ? "passed" : "failed");
  result.scrollIntoView({ behavior: "smooth", block: "start" });
}

document.querySelectorAll(".scenario").forEach((card) => {
  const button = card.querySelector("button");
  button.addEventListener("click", async () => {
    document.querySelectorAll(".scenario").forEach((item) => item.classList.remove("running", "passed", "failed"));
    card.classList.add("running");
    button.disabled = true;
    result.hidden = true;
    try {
      const response = await fetch(`/api/demo/scenarios/${card.dataset.scenario}`, { method: "POST" });
      const body = await response.json();
      if (!response.ok) throw new Error(body.detail || "Scenario failed to execute");
      renderScenario(body, card);
    } catch (error) {
      card.classList.add("failed");
      result.hidden = false;
      resultTitle.textContent = "Scenario could not complete";
      verdict.textContent = "ERROR";
      verdict.className = "status-chip status-chip--warning";
      explanation.textContent = error.message;
      timeline.replaceChildren(); evidence.textContent = "";
    } finally {
      card.classList.remove("running"); button.disabled = false;
    }
  });
});

loadReadiness();
