(() => {
  const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
  const SUCCESS_STATES = new Set(["created", "replayed"]);
  const AI_STATUSES = new Set(["enriched", "fallback_invalid", "fallback_unavailable"]);

  function snapshot(values) {
    return {
      full_name: String(values.full_name || ""),
      email: String(values.email || ""),
      phone: String(values.phone || ""),
      message: String(values.message || ""),
    };
  }

  function sameSnapshot(left, right) {
    return JSON.stringify(snapshot(left)) === JSON.stringify(snapshot(right));
  }

  function createPending(values, identifier, now) {
    const saved = snapshot(values);
    return {
      values: saved,
      payload: {
        submission_id: identifier(),
        correlation_id: identifier(),
        received_at: now(),
        ...saved,
      },
    };
  }

  function pendingFor(values, existing, identifier, now) {
    if (existing && existing.values && existing.payload && sameSnapshot(values, existing.values)) {
      return { pending: existing, reused: true };
    }
    return { pending: createPending(values, identifier, now), reused: false };
  }

  function verifiedSuccess(body, payload) {
    return Boolean(
      body &&
        body.state === "accepted" &&
        SUCCESS_STATES.has(body.intake_state) &&
        AI_STATUSES.has(body.ai_status) &&
        UUID_RE.test(body.crm_lead_id || "") &&
        body.submission_id === payload.submission_id &&
        body.correlation_id === payload.correlation_id,
    );
  }

  async function fetchWithTimeout(url, options, timeoutMs) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);
    try {
      return await fetch(url, { ...options, signal: controller.signal });
    } finally {
      clearTimeout(timer);
    }
  }

  const api = { pendingFor, snapshot, sameSnapshot, verifiedSuccess, fetchWithTimeout };
  if (typeof window !== "undefined") window.LeadIntake = api;
  if (typeof module !== "undefined") module.exports = api;
})();
