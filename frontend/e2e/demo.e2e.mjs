import assert from "node:assert/strict";
import { mkdir } from "node:fs/promises";
import { test } from "node:test";
import { chromium } from "playwright-core";

const baseUrl = process.env.DEMO_BASE_URL || "http://127.0.0.1:28000";
const executablePath = process.env.CHROME_PATH || "/usr/bin/google-chrome-stable";
const evidenceDir = new URL("../../docs/assets/demo/", import.meta.url);

test("guided demo verifies all five real browser journeys", { timeout: 120_000 }, async () => {
  await mkdir(evidenceDir, { recursive: true });
  const browser = await chromium.launch({ executablePath, headless: true });
  const page = await browser.newPage({ viewport: { width: 1440, height: 1100 } });
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
      const response = await responsePromise;
      assert.equal(response.status(), 200, `${scenario} scenario HTTP status`);
      const body = await response.json();
      assert.equal(body.verified, true, `${scenario} authoritative verification`);
      assert.equal(body.authoritative_evidence.lead_count, 1);
      assert.equal(body.authoritative_evidence.contact_count, 1);
      assert.equal(body.authoritative_evidence.opportunity_count, 1);
      await page.locator("#scenario-verdict").filter({ hasText: "VERIFIED" }).waitFor();
      const displayedEvidence = JSON.parse(
        await page.locator("#scenario-evidence").textContent(),
      );
      assert.equal(displayedEvidence.submission_id, body.submission_id);
      assert.equal(displayedEvidence.final_job_state, "completed");
    }

    await page.screenshot({
      path: new URL("guided-demo-lost-ack.png", evidenceDir).pathname,
      fullPage: true,
    });
  } finally {
    await browser.close();
  }
});
