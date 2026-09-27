import assert from "node:assert/strict";
import { mkdir } from "node:fs/promises";
import { test } from "node:test";
import { chromium } from "playwright-core";

const baseUrl = process.env.DEMO_BASE_URL || "http://127.0.0.1:28000";
const executablePath = process.env.CHROME_PATH || "/usr/bin/google-chrome-stable";
const evidenceDir = new URL("../../docs/assets/demo/", import.meta.url);

function assertScenarioEvidence(scenario, body) {
  const evidence = body.authoritative_evidence;
  assert.equal(Object.values(evidence.scenario_proof).every(Boolean), true);
  if (scenario === "duplicate") {
    assert.deepEqual(
      evidence.replay_operation_identity,
      evidence.initial_operation_identity,
      "replay must identify the original operation",
    );
    assert.equal(evidence.replay_http_status, 200);
    assert.equal(evidence.replay_intake_state, "replayed");
  }
  if (scenario === "ai_unavailable") {
    assert.equal(evidence.ai_status, "fallback_unavailable");
    assert.equal(evidence.needs_review, true);
  }
  if (scenario === "rate_limit") {
    const timing = evidence.retry_timing;
    const observedDelay = (
      Date.parse(timing.next_attempt_started_at)
      - Date.parse(timing.failed_attempt_finished_at)
    ) / 1000;
    const scheduledDelay = (
      Date.parse(timing.scheduled_retry_at)
      - Date.parse(timing.failed_attempt_finished_at)
    ) / 1000;
    assert.equal(evidence.attempts[0].status_code, 429);
    assert.equal(evidence.attempts[0].retry_after_seconds, 2);
    assert.ok(scheduledDelay >= 2, "persisted retry schedule must preserve Retry-After");
    assert.ok(observedDelay >= 2, "next attempt must not begin before Retry-After");
    assert.ok(
      Date.parse(timing.next_attempt_started_at) >= Date.parse(timing.scheduled_retry_at),
      "next attempt must not begin before the persisted due time",
    );
  }
  if (scenario === "lost_acknowledgement") {
    assert.equal(
      evidence.attempts.some((attempt) => attempt.error_class === "highlevel_timeout"),
      true,
    );
    assert.equal(
      evidence.simulator_events.filter(
        (event) => event.method === "POST" && event.path === "/opportunities/",
      ).length,
      1,
    );
  }
}

test("guided demo verifies all five real browser journeys", { timeout: 120_000 }, async () => {
  await mkdir(evidenceDir, { recursive: true });
  const browser = await chromium.launch({ executablePath, headless: true });
  const context = await browser.newContext({ viewport: { width: 1440, height: 1100 } });
  const page = await context.newPage();
  try {
    await page.goto(`${baseUrl}/demo.html`, { waitUntil: "networkidle" });
    await page.getByText("All demo boundaries are ready").waitFor({ timeout: 15_000 });
    await page.screenshot({
      path: new URL("guided-demo-overview.png", evidenceDir).pathname,
      fullPage: true,
    });

    const scenarios = [
      "normal",
      "duplicate",
      "ai_unavailable",
      "rate_limit",
      "lost_acknowledgement",
    ];
    for (const scenario of scenarios) {
      const responsePromise = page.waitForResponse(
        (response) => response.url().endsWith(`/api/demo/scenarios/${scenario}`),
        { timeout: 30_000 },
      );
      await page.locator(`[data-scenario="${scenario}"] button`).click();
      assert.equal(
        await page.locator(".scenario button:disabled").count(),
        5,
        "one active scenario disables every card in this tab",
      );
      const response = await responsePromise;
      assert.equal(response.status(), 200, `${scenario} scenario HTTP status`);
      const body = await response.json();
      assert.equal(body.verified, true, `${scenario} authoritative verification`);
      assert.equal(body.authoritative_evidence.lead_count, 1);
      assert.equal(body.authoritative_evidence.contact_count, 1);
      assert.equal(body.authoritative_evidence.opportunity_count, 1);
      assertScenarioEvidence(scenario, body);
      await page.locator("#scenario-verdict").filter({ hasText: "VERIFIED" }).waitFor();
      const displayedEvidence = JSON.parse(
        await page.locator("#scenario-evidence").textContent(),
      );
      assert.equal(displayedEvidence.submission_id, body.submission_id);
      assert.equal(displayedEvidence.final_job_state, "completed");
    }

    const secondPage = await page.context().newPage();
    await secondPage.setViewportSize({ width: 1200, height: 900 });
    await secondPage.goto(`${baseUrl}/demo.html`, { waitUntil: "networkidle" });
    await secondPage.getByText("All demo boundaries are ready").waitFor();
    const rateResponse = page.waitForResponse(
      (response) => response.url().endsWith("/api/demo/scenarios/rate_limit"),
    );
    const lostAckResponse = secondPage.waitForResponse(
      (response) => response.url().endsWith("/api/demo/scenarios/lost_acknowledgement"),
    );
    await Promise.all([
      page.locator('[data-scenario="rate_limit"] button').click(),
      secondPage.locator('[data-scenario="lost_acknowledgement"] button').click(),
    ]);
    const [overlappingRateLimit, overlappingLostAck] = await Promise.all([
      rateResponse,
      lostAckResponse,
    ]);
    const rateBody = await overlappingRateLimit.json();
    const lostAckBody = await overlappingLostAck.json();
    assert.equal(overlappingRateLimit.status(), 200);
    assert.equal(overlappingLostAck.status(), 200);
    assert.equal(rateBody.verified, true, "overlapping rate limit remains isolated");
    assert.equal(lostAckBody.verified, true, "overlapping lost ACK remains isolated");
    assertScenarioEvidence("rate_limit", rateBody);
    assertScenarioEvidence("lost_acknowledgement", lostAckBody);
    await secondPage.locator("#scenario-verdict").filter({ hasText: "VERIFIED" }).waitFor();
    await page.screenshot({
      path: new URL("guided-demo-overlap-rate-limit.png", evidenceDir).pathname,
      fullPage: true,
    });
    await secondPage.screenshot({
      path: new URL("guided-demo-lost-ack.png", evidenceDir).pathname,
      fullPage: true,
    });
    await secondPage.close();
  } finally {
    await context.close();
    await browser.close();
  }
});
