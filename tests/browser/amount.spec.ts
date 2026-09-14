/**
 * TEST-17: Browser amount example and prepared manifest verification (T17).
 *
 * Acceptance criteria (from planning/tasks/T17.md):
 * 1. Renamed identical bytes produce same reading (F01 mapping-amount / F02).
 * 2. Modified bytes cannot replay old prepared result.
 * 3. Live and prepared paths label provenance correctly.
 * 4. Real source downloadable (HTTP GET returns status 200, PDF mime, and exact fixture SHA-256).
 * 5. Actual timing visible, not decorative scan animation.
 * 6. Clean counterpart renders equal under same renderer (0 pixel difference, diverging text).
 * 7. Accessibility: No critical or serious WCAG violations.
 *
 * The standalone /examples/amount/index.html page is a redirect into the
 * real inspector; these criteria now run against #/workspace?example=amount
 * and a real local-file inspection.
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
const EXAMPLE_URL = "/#/workspace?example=amount";
const REDIRECT_URL = "/examples/amount/index.html";

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

test.setTimeout(180_000);

function sha256Hex(buf: Buffer | Uint8Array): string {
  return createHash("sha256").update(buf).digest("hex");
}

/** Open a local PDF through the workspace's real file input. */
async function openPdf(page: Page, bytes: Buffer, name: string) {
  await page.locator("#input-open-pdf").setInputFiles({
    name,
    mimeType: "application/pdf",
    buffer: bytes,
  });
  await page.waitForSelector('[data-testid="pages-summary"]', { timeout: 30_000 });
}

/** Render page 0 through the session's real PDF.js render path. */
async function renderDigest(page: Page): Promise<{ w: number; h: number; sha: string } | null> {
  return page.evaluate(async () => {
    const session = (window as unknown as { __inspect?: any }).__inspect;
    if (!session?.renderViewerPage) return null;
    const raster = await session.renderViewerPage(0, 1.5, new AbortController().signal);
    if (!raster) return null;
    const digest = await crypto.subtle.digest("SHA-256", raster.imageData);
    return {
      w: raster.widthPx,
      h: raster.heightPx,
      sha: [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, "0")).join(""),
    };
  });
}

async function reportSha256(page: Page): Promise<string | null> {
  return page.evaluate(
    () => (window as unknown as { __inspect?: any }).__inspect?.getState().report?.document.sha256 ?? null,
  );
}

test.describe("T17: Browser Amount Demo and Prepared Manifest", () => {
  test("criterion 1: renamed identical bytes produce same reading", async ({ page }) => {
    await page.goto(`${harness.base}/#/workspace`);
    await page.waitForSelector('[data-testid="file-input"]');

    const amountBytes = readFileSync(join(FIXTURE_PUBLIC, "mapping-amount.pdf"));
    const amountHash = sha256Hex(amountBytes);

    // Upload under a completely different name and run a real inspection.
    await openPdf(page, amountBytes, "renamed-accounting-invoice-2026.pdf");
    await expect(page.locator("#workspace-doc-title")).toContainText(
      "renamed-accounting-invoice-2026.pdf",
    );
    await page.locator('[data-testid="start-run"]').click();
    await page.waitForSelector("#viewer-stage", { timeout: 120_000 });

    // The report binds to the byte identity, not the file name.
    expect(await reportSha256(page)).toBe(amountHash);

    // The real reading is the recorded $1,000 text-layer value.
    await expect(page.locator("#accessible-text-equivalent")).toContainText("$1,000");

    // Same bytes under a control name read differently — mapping-control.pdf
    // carries identity ToUnicode, so its text layer reads $100.
    await page.locator("#btn-close-doc").click();
    const controlBytes = readFileSync(join(FIXTURE_PUBLIC, "mapping-control.pdf"));
    const controlHash = sha256Hex(controlBytes);
    await openPdf(page, controlBytes, "completely-different-name-control.pdf");
    await expect(page.locator("#workspace-doc-title")).toContainText(
      "completely-different-name-control.pdf",
    );
    await page.locator('[data-testid="start-run"]').click();
    await page.waitForSelector("#viewer-stage", { timeout: 120_000 });
    expect(await reportSha256(page)).toBe(controlHash);
    await expect(page.locator("#accessible-text-equivalent")).toContainText("$100");
  });

  test("criterion 2: modified bytes cannot replay old prepared result", async ({ page }) => {
    const originalBytes = readFileSync(join(FIXTURE_PUBLIC, "mapping-amount.pdf"));
    const modifiedBytes = Buffer.concat([originalBytes, Buffer.from("\n% tampered comment\n")]);
    const modifiedHash = sha256Hex(modifiedBytes);
    const reportBytes = readFileSync(
      join(WEB, "public", "examples", "amount", "report.json"),
    );

    // Attach tampered bytes as the source of the prepared report: the
    // import/attach gate must reject them as not matching the recorded
    // document — the prepared result cannot be replayed onto other bytes.
    await page.goto(`${harness.base}/#/workspace`);
    await page.locator("#input-import-report").setInputFiles({
      name: "amount.inkflip.json",
      mimeType: "application/json",
      buffer: reportBytes,
    });
    await page.waitForSelector("#btn-attach-source", { timeout: 30_000 });
    await page.locator("#input-attach-source").setInputFiles({
      name: "modified-tampered-amount.pdf",
      mimeType: "application/pdf",
      buffer: modifiedBytes,
    });
    await expect(page.locator("#import-error")).toContainText("does not match", {
      timeout: 15_000,
    });

    // The same modified bytes opened directly get their own fresh
    // inspection bound to the modified digest — never the prepared one.
    await page.locator("#btn-close-doc").click();
    await openPdf(page, modifiedBytes, "modified-tampered-amount.pdf");
    await page.locator('[data-testid="start-run"]').click();
    await page.waitForSelector("#viewer-stage", { timeout: 120_000 });
    expect(await reportSha256(page)).toBe(modifiedHash);
    await expect(page.locator('[data-testid="result-provenance"]')).toHaveText("Fresh inspection");
  });

  test("criterion 3: live and prepared paths label provenance correctly", async ({ page }) => {
    // Prepared example: imported captured report keeps its gallery label.
    await page.goto(`${harness.base}${EXAMPLE_URL}`);
    await page.waitForSelector("#viewer-stage", { timeout: 30_000 });
    const badge = page.locator('[data-testid="result-provenance"]');
    await expect(badge).toHaveText("Prepared example");
    await expect(page.locator('[data-testid="prepared-example-note"]')).toBeVisible();

    // A report opened by hand (no gallery card) is a plain saved report.
    await page.goto(`${harness.base}/#/workspace`);
    await page.locator("#input-import-report").setInputFiles({
      name: "amount.inkflip.json",
      mimeType: "application/json",
      buffer: readFileSync(join(WEB, "public", "examples", "amount", "report.json")),
    });
    await page.waitForSelector("#viewer-stage", { timeout: 30_000 });
    await expect(badge).toHaveText("Saved report");

    // A fresh local inspection of the same source file is labelled as such.
    await page.locator("#btn-close-doc").click();
    const amountBytes = readFileSync(join(FIXTURE_PUBLIC, "mapping-amount.pdf"));
    await openPdf(page, amountBytes, "live-run.pdf");
    await page.locator('[data-testid="start-run"]').click();
    await page.waitForSelector("#viewer-stage", { timeout: 120_000 });
    await expect(badge).toHaveText("Fresh inspection");
  });

  test("criterion 4: real source downloadable and verifiable", async ({ request }) => {
    // The redirect page keeps every publicly linked dependency reachable.
    const resPage = await request.get(`${harness.base}${REDIRECT_URL}`);
    expect(resPage.status()).toBe(200);
    const html = await resPage.text();
    expect(html).toContain("/#/workspace?example=amount");
    for (const asset of [
      "mapping-amount.pdf",
      "mapping-control.pdf",
      "manifest.json",
      "report.json",
    ]) {
      expect(html).toContain(`/examples/amount/${asset}`);
    }

    const expectedSourceBytes = readFileSync(join(FIXTURE_PUBLIC, "mapping-amount.pdf"));
    const expectedControlBytes = readFileSync(join(FIXTURE_PUBLIC, "mapping-control.pdf"));

    const resSource = await request.get(`${harness.base}/examples/amount/mapping-amount.pdf`);
    expect(resSource.status()).toBe(200);
    expect(resSource.headers()["content-type"]).toContain("application/pdf");
    const downloadedSourceBytes = await resSource.body();
    expect(sha256Hex(downloadedSourceBytes)).toBe(sha256Hex(expectedSourceBytes));
    expect(downloadedSourceBytes.length).toBe(expectedSourceBytes.length);

    const resControl = await request.get(`${harness.base}/examples/amount/mapping-control.pdf`);
    expect(resControl.status()).toBe(200);
    expect(resControl.headers()["content-type"]).toContain("application/pdf");
    const downloadedControlBytes = await resControl.body();
    expect(sha256Hex(downloadedControlBytes)).toBe(sha256Hex(expectedControlBytes));
    expect(downloadedControlBytes.length).toBe(expectedControlBytes.length);

    const resManifest = await request.get(`${harness.base}/examples/amount/manifest.json`);
    expect(resManifest.status()).toBe(200);
    const manifest = await resManifest.json();
    expect(manifest.schema_version).toBe("1.0.0");
    expect(manifest.files.source).toBeDefined();
    expect(manifest.files.source.filename).toBe("mapping-amount.pdf");
    expect(manifest.files.source.sha256).toBe(sha256Hex(expectedSourceBytes));
    expect(manifest.files.control.filename).toBe("mapping-control.pdf");
    expect(manifest.files.control.sha256).toBe(sha256Hex(expectedControlBytes));

    const resReport = await request.get(`${harness.base}/examples/amount/report.json`);
    expect(resReport.status()).toBe(200);
    const report = await resReport.json();
    const schemaIssues = checkSchema(report);
    expect(schemaIssues).toEqual([]);
    expect(() => validateReport(report)).not.toThrow();
  });

  test("criterion 5: actual timing visible, not decorative scan animation", async ({
    request,
    page,
  }) => {
    // The recorded timing lives in the manifest and the sealed report's
    // execution record — real measured values, not a decorative spinner.
    const manifest = await (
      await request.get(`${harness.base}/examples/amount/manifest.json`)
    ).json();
    expect(typeof manifest.timing?.duration_ms).toBe("number");
    expect(manifest.timing.duration_ms).toBeGreaterThan(0);
    expect(manifest.timing.method).toBe("browser_measured");
    const report = await (
      await request.get(`${harness.base}/examples/amount/report.json`)
    ).json();
    expect(report.execution.duration_ms).toBe(manifest.timing.duration_ms);

    await page.goto(`${harness.base}${EXAMPLE_URL}`);
    await page.waitForSelector("#viewer-stage", { timeout: 30_000 });
    const spinners = await page.locator(".spinner, .scan-line, .fake-scan, .loading-bar").count();
    expect(spinners).toBe(0);
    // Real check accounting is shown for the prepared run.
    await expect(page.locator("text=Completed 4 of 4 checks")).toBeVisible();
  });

  test("criterion 6: clean counterpart renders equal under same renderer", async ({ page }) => {
    await page.goto(`${harness.base}/#/workspace`);
    await page.waitForSelector('[data-testid="file-input"]');

    // Render both PDFs through the session's real PDF.js render path and
    // compare the actual pixels — identical operators must paint identically.
    const amountBytes = readFileSync(join(FIXTURE_PUBLIC, "mapping-amount.pdf"));
    await openPdf(page, amountBytes, "mapping-amount.pdf");
    const source = await renderDigest(page);
    expect(source).not.toBeNull();

    await page.locator("#btn-close-doc").click();
    const controlBytes = readFileSync(join(FIXTURE_PUBLIC, "mapping-control.pdf"));
    await openPdf(page, controlBytes, "mapping-control.pdf");
    const control = await renderDigest(page);
    expect(control).not.toBeNull();

    // Same raster dimensions and byte-identical pixels: 0 differing pixels.
    expect(control!.w).toBe(source!.w);
    expect(control!.h).toBe(source!.h);
    expect(control!.sha).toBe(source!.sha);

    // The control's sealed report records the diverging text-layer reading.
    const resReport = await page.request.get(
      `${harness.base}/examples/amount/report.control.json`,
    );
    expect(resReport.status()).toBe(200);
    const controlReport = await resReport.json();
    expect(checkSchema(controlReport)).toEqual([]);
    expect(() => validateReport(controlReport)).not.toThrow();
    expect(controlReport.document.sha256).toBe(sha256Hex(controlBytes));
    const controlTexts = controlReport.occurrences.map((o: { raw_text: string }) => o.raw_text);
    expect(controlTexts).toContain("$100");
    expect(controlTexts).not.toContain("$1,000");
  });

  test("criterion 7: accessibility check (WCAG AA)", async ({ page }) => {
    await page.goto(`${harness.base}${EXAMPLE_URL}`);
    await page.waitForSelector("#viewer-stage", { timeout: 30_000 });

    const axe = await new AxeBuilder({ page }).analyze();
    const seriousOrCritical = axe.violations.filter(
      (v) => v.impact === "critical" || v.impact === "serious",
    );
    expect(seriousOrCritical).toEqual([]);
  });
});
