(function () {
  "use strict";
  const list = document.getElementById("stage-sync-list");
  const status = document.getElementById("stage-sync-status");
  const input = document.getElementById("stage-sync-submission");
  const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
  let generation = 0;
  async function refresh() {
    const current = ++generation;
    const value = input.value.trim();
    if (value && !uuid.test(value)) {
      status.textContent = "Enter an exact submission UUID.";
      return;
    }
    status.textContent = "Reading lifecycle sync state…";
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 8000);
    try {
      const response = await fetch(`/api/operations/stage-sync${value ? `?submission_id=${encodeURIComponent(value)}` : ""}`, {signal: controller.signal});
      if (!response.ok) throw new Error("read failed");
      const data = await response.json();
      if (current !== generation) return;
      if (!data || !Array.isArray(data.items) || data.items.length > 25) throw new Error("invalid data");
      list.replaceChildren();
      for (const item of data.items) {
        if (!uuid.test(item.submission_id || "") || !uuid.test(item.correlation_id || "") || !Array.isArray(item.attempts)) throw new Error("invalid data");
        const block = document.createElement("div");
        block.className = "operations-context-note";
        const headline = document.createElement("p");
        headline.textContent = `${item.submission_id} · ${item.state} · desired ${item.desired_stage} (v${item.desired_version}) · verified ${item.verified_remote_stage || "none"}`;
        const detail = document.createElement("p");
        detail.textContent = `Correlation ${item.correlation_id} · attempts ${item.attempt_count} · due ${item.due_at} · error ${item.last_error_class || "none"}`;
        block.append(headline, detail);
        for (const attempt of item.attempts) {
          const row = document.createElement("p");
          row.textContent = `Attempt ${attempt.attempt_number}: v${attempt.desired_version} ${attempt.desired_stage} · ${attempt.outcome} · remote ${attempt.verified_remote_stage || "unverified"} · ${attempt.error_class || "no error"}`;
          block.append(row);
        }
        list.append(block);
      }
      status.textContent = `${data.items.length} stage sync record(s), observed ${data.observed_at}.`;
    } catch (_error) {
      if (current === generation) status.textContent = "Lifecycle sync could not be read. Refresh to try again.";
    } finally {
      clearTimeout(timer);
    }
  }
  document.getElementById("stage-sync-refresh").addEventListener("click", refresh);
  input.addEventListener("change", refresh);
  refresh();
})();
