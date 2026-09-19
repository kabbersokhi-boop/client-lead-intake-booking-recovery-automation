(() => {
  const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
  const SUCCESS_STATES = new Set(["created", "replayed"]);
  const AI_STATUSES = new Set(["enriched", "fallback_invalid", "fallback_unavailable"]);
  const BOOKING_STATES = new Set(["created", "replayed"]);

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
    if (
      !body ||
      body.state !== "accepted" ||
      !SUCCESS_STATES.has(body.intake_state) ||
      !AI_STATUSES.has(body.ai_status) ||
      !UUID_RE.test(body.crm_lead_id || "") ||
      body.submission_id !== payload.submission_id ||
      body.correlation_id !== payload.correlation_id
    ) {
      return false;
    }
    const followUpValid =
      body.follow_up_status === null
        ? body.follow_up_due_at === null
        : ["pending", "sent", "cancelled"].includes(body.follow_up_status) &&
          typeof body.follow_up_due_at === "string" &&
          !Number.isNaN(Date.parse(body.follow_up_due_at));
    if (!followUpValid) return false;
    if (body.intake_state === "created") {
      return (
        body.pipeline_stage === "new_lead" &&
        (payload.email ? body.follow_up_status === "pending" : body.follow_up_status === null)
      );
    }
    if (!["new_lead", "contacted", "appointment_booked"].includes(body.pipeline_stage)) {
      return false;
    }
    if (body.pipeline_stage === "contacted") {
      return body.follow_up_status === "sent" || body.follow_up_status === null;
    }
    if (body.pipeline_stage === "appointment_booked") {
      return ["sent", "cancelled", null].includes(body.follow_up_status);
    }
    return ["pending", null].includes(body.follow_up_status);
  }

  function successView(body, payload) {
    if (!verifiedSuccess(body, payload)) return null;
    return {
      title: body.intake_state === "replayed" ? "Lead replayed safely" : "Lead accepted",
      intakeState: body.intake_state,
      correlationId: body.correlation_id,
      crmLeadId: body.crm_lead_id,
      aiStatus: body.ai_status,
      aiStatusTone: body.ai_status === "enriched" ? "success" : "warning",
      pipelineStage: body.pipeline_stage,
      followUpStatus: body.follow_up_status || "not scheduled",
      followUpDueAt: body.follow_up_due_at || "Not applicable",
    };
  }

  function bookingSnapshot(values) {
    return {
      correlation_id: String(values.correlation_id || ""),
      appointment_local: String(values.appointment_local || ""),
      business_timezone: String(values.business_timezone || ""),
    };
  }

  function bookingPendingFor(values, existing, identifier) {
    const saved = bookingSnapshot(values);
    if (
      existing &&
      existing.values &&
      existing.payload &&
      JSON.stringify(saved) === JSON.stringify(existing.values)
    ) {
      return { pending: existing, reused: true };
    }
    return {
      pending: {
        values: saved,
        payload: { booking_request_id: identifier(), ...saved },
      },
      reused: false,
    };
  }

  function verifiedBooking(body, payload) {
    return Boolean(
      body &&
        body.state === "booked" &&
        BOOKING_STATES.has(body.booking_state) &&
        UUID_RE.test(body.appointment_id || "") &&
        body.booking_request_id === payload.booking_request_id &&
        body.correlation_id === payload.correlation_id &&
        body.pipeline_stage === "appointment_booked" &&
        ["sent", "already_sent", "skipped_no_email", "unconfirmed"].includes(
          body.confirmation_state,
        ) &&
        ["sent", "cancelled", null].includes(body.follow_up_status) &&
        typeof body.appointment_at === "string" &&
        /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$/.test(
          body.appointment_at,
        ) &&
        !Number.isNaN(Date.parse(body.appointment_at)) &&
        body.business_timezone === payload.business_timezone,
    );
  }

  function bookingView(body, payload) {
    if (!verifiedBooking(body, payload)) return null;
    return {
      title: body.booking_state === "replayed" ? "Booking replayed safely" : "Appointment booked",
      appointmentId: body.appointment_id,
      appointmentAt: body.appointment_at,
      businessTimezone: body.business_timezone,
      pipelineStage: body.pipeline_stage,
      followUpStatus: body.follow_up_status || "not scheduled",
      confirmationState: body.confirmation_state,
      notificationMessage: body.notification_message || null,
    };
  }

  function beginIntakeAttempt() {
    return {
      acceptedLead: null,
      intakeResultVisible: false,
      bookingPanelVisible: false,
      bookingResultVisible: false,
    };
  }

  function acceptIntakeResult(lead) {
    return {
      acceptedLead: { ...lead },
      intakeResultVisible: true,
      bookingPanelVisible: true,
      bookingResultVisible: false,
    };
  }

  function confirmationIsSettled(confirmationState) {
    return ["sent", "already_sent", "skipped_no_email"].includes(confirmationState);
  }

  function traceView(trace) {
    if (!trace || !trace.lead || typeof trace.lead !== "object") return null;
    const lead = trace.lead;
    const followUp = Array.isArray(trace.follow_ups) ? trace.follow_ups[0] : null;
    const appointment = Array.isArray(trace.appointments) ? trace.appointments[0] : null;
    return {
      customer: lead.full_name || "Not available",
      contact: [lead.email, lead.phone].filter(Boolean).join(" · ") || "Not available",
      pipelineStage: lead.pipeline_stage || "Not available",
      serviceType: lead.service_type || "Not enriched",
      urgency: lead.urgency || "Not enriched",
      preferredTime: lead.preferred_time || "Not provided",
      aiStatus: lead.ai_status || "Not available",
      needsReview: lead.needs_review === true,
      clientReceivedAt: lead.client_received_at || "Not available",
      persistedAt: lead.created_at || "Not available",
      followUpStatus: followUp?.status || "not scheduled",
      followUpDueAt: followUp?.due_at || "Not applicable",
      followUpCompletedAt: followUp?.sent_at || followUp?.cancelled_at || "Not applicable",
      appointmentId: appointment?.id || "Not booked",
      appointmentAt: appointment?.appointment_at || "Not booked",
      appointmentTimezone: appointment?.business_timezone || "America/Vancouver",
      bookingStatus: appointment?.status || "not booked",
      confirmationSentAt: appointment?.confirmation_sent_at || "Not sent",
      audits: Array.isArray(trace.audit_events) ? trace.audit_events : [],
    };
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

  const api = {
    acceptIntakeResult,
    beginIntakeAttempt,
    bookingPendingFor,
    bookingView,
    confirmationIsSettled,
    fetchWithTimeout,
    pendingFor,
    sameSnapshot,
    snapshot,
    successView,
    traceView,
    verifiedBooking,
    verifiedSuccess,
  };
  if (typeof window !== "undefined") window.LeadIntake = api;
  if (typeof module !== "undefined") module.exports = api;
})();
