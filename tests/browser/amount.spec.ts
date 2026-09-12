/**
 * TEST-17: Browser amount demo and prepared manifest verification (T17).
 *
 * Acceptance criteria (from planning/tasks/T17.md):
 * 1. Renamed identical bytes produce same reading (F01 mapping-amount / F02).
 * 2. Modified bytes cannot replay old prepared result.
 * 3. Live and prepared paths label provenance correctly.
 * 4. Real source downloadable (HTTP GET returns status 200, PDF mime, and exact fixture SHA-256).
 * 5. Actual timing visible, not decorative scan animation.
 * 6. Clean counterpart renders equal under same renderer (0 pixel difference, diverging text).
 * 7. Accessibility: No critical or serious WCAG violations.
 */
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

import { checkSchema, validateReport } from "../../packages/contracts/src/index.ts";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..", "..");
const WEB = join(ROOT, "apps", "web");
const FIXTURE_PUBLIC = join(ROOT, "fixtures", "public");
const DEMO_URL = "/examples/amount/index.html";

interface Harness {
  base: string;
  close: () => Promise<void>;
}

let harness: Harness;

test.beforeAll(async () => {
  const viteEntry = pathToFileURL(
    join(WEB, "node_modules", "vite", "dist", "node", "index.js"),
  ).href;
  const { createServer } = (await import(viteEntry)) as {
    createServer: (opts: { root: string; server: { port: number }; logLevel: string }) => Promise<{
      listen: () => Promise<void>;
      resolvedUrls: { local: string[] };
      close: () => Promise<void>;
    }>;
  };
  const server = await createServer({
    root: WEB,
    server: { port: 0 },
    logLevel: "warn",
  });
  await server.listen();
  const base = server.resolvedUrls.local[0].replace(/\/$/, "");
  harness = { base, close: () => server.close() };
});

test.afterAll(async () => {
  if (harness) {
    await harness.close();
  }
});

test.beforeEach(async ({ page }) => {
  page.on("pageerror", (error) => {
    console.log(`[pageerror] ${error}`);
  });
});

test.setTimeout(60_000);

function sha256Hex(buf: Buffer | Uint8Array): string {
  return createHash("sha256").update(buf).digest("hex");
}

test.describe("T17: Browser Amount Demo and Prepared Manifest", () => {
  test("criterion 1: renamed identical bytes produce same reading", async ({ page }) => {
    await page.goto(`${harness.base}${DEMO_URL}`);
    await page.waitForSelector("#file-input");

    // Read original mapping-amount.pdf (F01) bytes
    const amountBytes = readFileSync(join(FIXTURE_PUBLIC, "mapping-amount.pdf"));
    const amountHash = sha256Hex(amountBytes);

    // Upload with a completely different file name
    await page.setInputFiles("#file-input", {
      name: "renamed-accounting-invoice-2026.pdf",
      mimeType: "application/pdf",
      buffer: amountBytes,
    });

    // Wait for live processing to finish
    await page.waitForSelector('#live-result-container[data-state="complete"]', {
      timeout: 15_000,
    });

    // Assert renamed file name is displayed
    const nameText = await page.locator("#live-file-name").textContent();
    expect(nameText).toBe("renamed-accounting-invoice-2026.pdf");

    // Assert SHA-256 matches exact original mapping-amount.pdf
    const hashText = await page.locator("#live-file-hash").textContent();
    expect(hashText).toBe(amountHash);

    // Assert live extraction produces $1,000 (same reading based on bytes, not name)
    await expect(page.locator("#live-extracted-text")).toContainText("$1,000");

    // Now test with mapping-control.pdf renamed
    const controlBytes = readFileSync(join(FIXTURE_PUBLIC, "mapping-control.pdf"));
    const controlHash = sha256Hex(controlBytes);

    await page.setInputFiles("#file-input", {
      name: "completely-different-name-control.pdf",
      mimeType: "application/pdf",
      buffer: controlBytes,
    });

    // Wait for text and hash to update to control values
    await expect(page.locator("#live-file-hash")).toHaveText(controlHash);
    await expect(page.locator("#live-extracted-text")).toContainText("$100");
  });

  test("criterion 2: modified bytes cannot replay old prepared result", async ({ page }) => {
    await page.goto(`${harness.base}${DEMO_URL}`);
    await page.waitForSelector("#file-input");

    // Read mapping-amount.pdf and tamper with its bytes (append valid comment)
    const originalBytes = readFileSync(join(FIXTURE_PUBLIC, "mapping-amount.pdf"));
    const modifiedBytes = Buffer.concat([originalBytes, Buffer.from("\n% tampered comment\n")]);
    const modifiedHash = sha256Hex(modifiedBytes);

    // Upload modified PDF
    await page.setInputFiles("#file-input", {
      name: "modified-tampered-amount.pdf",
      mimeType: "application/pdf",
      buffer: modifiedBytes,
    });

    // Wait for live processing to complete
    await page.waitForSelector('#live-result-container[data-state="complete"]', {
      timeout: 15_000,
    });

    // Assert hash is different from prepared manifest
    const hashText = await page.locator("#live-file-hash").textContent();
    expect(hashText).toBe(modifiedHash);

    // Assert replay rejection notice appears with tamper-warning class
    const notice = page.locator("#replay-notice");
    await expect(notice).toBeVisible();
    await expect(notice).toHaveClass(/tamper-warning/);
    const noticeText = await notice.textContent();
    expect(noticeText).toContain("Modified bytes detected");
    expect(noticeText).toContain("Prepared report replay rejected");

    // Evaluate client state to verify canned replay was NOT performed
    const lastResult = await page.evaluate(() => (window as any).__lastLiveResult);
    expect(lastResult).toBeDefined();
    expect(lastResult.replayedPrepared).toBe(false);
    expect(lastResult.hash).toBe(modifiedHash);
  });

  test("criterion 3: live and prepared paths label provenance correctly", async ({ page }) => {
    await page.goto(`${harness.base}${DEMO_URL}`);

    // Prepared state on initial load
    const badge = page.locator("#provenance-badge");
    await expect(badge).toBeVisible();
    await expect(badge).toHaveText("prepared");
    await expect(badge).toHaveAttribute("data-provenance", "prepared");
    await expect(badge).toHaveClass(/badge-prepared/);

    // Prepared timing display
    const timing = page.locator("#timing-display");
    await expect(timing).toBeVisible();
    expect(await timing.textContent()).toMatch(/^\d+\s*ms$/);

    // Now trigger live path via upload
    const amountBytes = readFileSync(join(FIXTURE_PUBLIC, "mapping-amount.pdf"));
    await page.setInputFiles("#file-input", {
      name: "live-test.pdf",
      mimeType: "application/pdf",
      buffer: amountBytes,
    });

    await page.waitForSelector('#live-result-container[data-state="complete"]', {
      timeout: 15_000,
    });

    // Provenance badge must now say 'live'
    await expect(badge).toHaveText("live");
    await expect(badge).toHaveAttribute("data-provenance", "live");
    await expect(badge).toHaveClass(/badge-live/);
  });

  test("criterion 4: real source downloadable and verifiable", async ({ request, page }) => {
    // Check download links exist on the page
    await page.goto(`${harness.base}${DEMO_URL}`);
    const sourceLink = page.locator("#download-source");
    const controlLink = page.locator("#download-control");
    const manifestLink = page.locator("#view-manifest");
    const reportLink = page.locator("#view-report");

    await expect(sourceLink).toBeVisible();
    await expect(controlLink).toBeVisible();
    await expect(manifestLink).toBeVisible();
    await expect(reportLink).toBeVisible();

    // 1. Download source PDF (mapping-amount.pdf)
    const resSource = await request.get(`${harness.base}/examples/amount/mapping-amount.pdf`);
    expect(resSource.status()).toBe(200);
    expect(resSource.headers()["content-type"]).toContain("application/pdf");
    const downloadedSourceBytes = await resSource.body();
    const expectedSourceBytes = readFileSync(join(FIXTURE_PUBLIC, "mapping-amount.pdf"));
    expect(sha256Hex(downloadedSourceBytes)).toBe(sha256Hex(expectedSourceBytes));
    expect(downloadedSourceBytes.length).toBe(expectedSourceBytes.length);

    // 2. Download clean control PDF (mapping-control.pdf)
    const resControl = await request.get(`${harness.base}/examples/amount/mapping-control.pdf`);
    expect(resControl.status()).toBe(200);
    expect(resControl.headers()["content-type"]).toContain("application/pdf");
    const downloadedControlBytes = await resControl.body();
    const expectedControlBytes = readFileSync(join(FIXTURE_PUBLIC, "mapping-control.pdf"));
    expect(sha256Hex(downloadedControlBytes)).toBe(sha256Hex(expectedControlBytes));
    expect(downloadedControlBytes.length).toBe(expectedControlBytes.length);

    // 3. Manifest JSON validation
    const resManifest = await request.get(`${harness.base}/examples/amount/manifest.json`);
    expect(resManifest.status()).toBe(200);
    const manifest = await resManifest.json();
    expect(manifest.schema_version).toBe("1.0.0");
    expect(manifest.files.source).toBeDefined();
    expect(manifest.files.source.filename).toBe("mapping-amount.pdf");
    expect(manifest.files.source.sha256).toBe(sha256Hex(expectedSourceBytes));
    expect(manifest.files.control.filename).toBe("mapping-control.pdf");
    expect(manifest.files.control.sha256).toBe(sha256Hex(expectedControlBytes));

    // 4. Report JSON validation with Inkflip contracts
    const resReport = await request.get(`${harness.base}/examples/amount/report.json`);
    expect(resReport.status()).toBe(200);
    const report = await resReport.json();
    const schemaIssues = checkSchema(report);
    expect(schemaIssues).toEqual([]);
    expect(() => validateReport(report)).not.toThrow();
  });

  test("criterion 5: actual timing visible, not decorative scan animation", async ({ page }) => {
    await page.goto(`${harness.base}${DEMO_URL}`);

    // Initial timing display exists and has actual numeric ms
    const timing = page.locator("#timing-display");
    await expect(timing).toBeVisible();
    const initialText = await timing.textContent();
    expect(initialText).toMatch(/^\d+\s*ms$/);

    // Verify there are no decorative infinite loading animations or fake progress bars
    const spinners = await page.locator(".spinner, .scan-line, .fake-scan, .loading-bar").count();
    expect(spinners).toBe(0);

    // Process a live file
    const amountBytes = readFileSync(join(FIXTURE_PUBLIC, "mapping-amount.pdf"));
    await page.setInputFiles("#file-input", {
      name: "timing-check.pdf",
      mimeType: "application/pdf",
      buffer: amountBytes,
    });

    await page.waitForSelector('#live-result-container[data-state="complete"]', {
      timeout: 15_000,
    });

    // Assert timing updated to actual numeric execution time
    const updatedText = await timing.textContent();
    expect(updatedText).toMatch(/^\d+\s*ms$/);

    // Check performance.now() elapsed recorded in client state
    const elapsed = await page.evaluate(() => (window as any).__lastLiveResult?.elapsed);
    expect(typeof elapsed).toBe("number");
    expect(elapsed).toBeGreaterThanOrEqual(0);
  });

  test("criterion 6: clean counterpart renders equal under same renderer", async ({ page }) => {
    await page.goto(`${harness.base}${DEMO_URL}`);

    // Wait for source PDF to finish initial render
    await page.waitForFunction(() => (window as any).__sourceRenderResult !== undefined, {
      timeout: 15_000,
    });

    const sourceResult = await page.evaluate(() => {
      const res = (window as any).__sourceRenderResult;
      return {
        textItems: res.textItems,
      };
    });
    expect(sourceResult.textItems).toContain("$1,000");

    // Click compare button to render control PDF and compute pixel diff
    const compareBtn = page.locator("#btn-compare-control");
    await compareBtn.click();

    // Wait for comparison result
    await page.waitForFunction(() => (window as any).__controlComparison !== undefined, {
      timeout: 15_000,
    });

    const comparison = await page.evaluate(() => (window as any).__controlComparison);
    expect(comparison.totalPixels).toBeGreaterThan(0);
    // Pixel difference MUST be exactly 0 (100% equal rendering)
    expect(comparison.diffCount).toBe(0);

    // Text reading of control MUST be $100 (differs from source $1,000)
    expect(comparison.controlText).toContain("$100");

    // Status label confirms 100% pixel match
    const statusEl = page.locator("#pixel-match-status");
    await expect(statusEl).toContainText("100% pixel match — 0 differing pixels");
  });

  test("criterion 7: accessibility check (WCAG AA)", async ({ page }) => {
    await page.goto(`${harness.base}${DEMO_URL}`);
    await page.waitForSelector("#rendered-amount-canvas");

    const axe = await new AxeBuilder({ page }).analyze();
    const seriousOrCritical = axe.violations.filter(
      (v) => v.impact === "critical" || v.impact === "serious",
    );
    expect(seriousOrCritical).toEqual([]);
  });
});
