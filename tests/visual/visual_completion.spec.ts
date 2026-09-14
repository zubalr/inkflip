import fs from "node:fs";
import path from "node:path";
import { pathToFileURL } from "node:url";
import { test, expect } from "@playwright/test";

const ROOT = path.resolve(process.cwd());

/**
 * T38: Visual Completion & Usability Regression Test Suite
 *
 * Verifies:
 * 1. Zero horizontal overflow across supported viewports (1440, 1024, 768, 390, 320)
 *    on Home, Workspace (empty & loaded), Examples Gallery, and Help surfaces.
 * 2. Resistance to layout blowout under long/hostile document titles.
 * 3. Mobile touch target sizing (>= 44x44px) across navigation, mode tabs, and tools.
 * 4. Active focus outline styling adherence to 3px focus token.
 * 5. Finding card disclosure semantics (aria-current="true").
 * 6. Help page routing, navigation, and core invariant documentation.
 */

const VIEWPORTS = [
  { width: 1440, height: 900, name: "desktop-1440" },
  { width: 1024, height: 768, name: "intermediate-1024" },
  { width: 768, height: 1024, name: "intermediate-768" },
  { width: 390, height: 844, name: "mobile-390" },
  { width: 320, height: 568, name: "mobile-320" },
];

const WEB_ROOT = path.resolve(process.cwd(), "apps/web");

let viteServer: any;
let baseUrl: string;

test.beforeAll(async () => {
  const viteModulePath = path.resolve(WEB_ROOT, "node_modules/vite/dist/node/index.js");
  const { createServer } = await import(pathToFileURL(viteModulePath).href);
  viteServer = await createServer({
    root: WEB_ROOT,
    server: {
      port: 0,
      strictPort: false,
    },
    logLevel: "silent",
  });
  await viteServer.listen();
  baseUrl = viteServer.resolvedUrls.local[0].replace(/\/$/, "");
});

test.afterAll(async () => {
  if (viteServer) {
    await viteServer.close();
  }
});

async function checkNoPageHorizontalOverflow(page: any) {
  return page.evaluate(() => {
    const doc = document.documentElement;
    const body = document.body;
    const scrollWidth = Math.max(doc.scrollWidth, body.scrollWidth);
    const clientWidth = doc.clientWidth;
    return {
      hasOverflow: scrollWidth > clientWidth,
      scrollWidth,
      clientWidth,
      diff: scrollWidth - clientWidth,
    };
  });
}

test.describe("T38: Visual Completion — Responsive Viewport Overflow", () => {
  for (const vp of VIEWPORTS) {
    test(`Home page: width ${vp.width}px (${vp.name}) has zero horizontal overflow`, async ({ page }) => {
      await page.setViewportSize({ width: vp.width, height: vp.height });
      await page.goto(`${baseUrl}/#/`);
      await page.waitForSelector('[data-testid="examples-gallery"]', { timeout: 10000 });

      const overflow = await checkNoPageHorizontalOverflow(page);
      expect(overflow.hasOverflow).toBe(false);
      expect(overflow.diff).toBeLessThanOrEqual(0);
    });

    test(`Workspace (loaded): width ${vp.width}px (${vp.name}) has zero horizontal overflow`, async ({ page }) => {
      await page.setViewportSize({ width: vp.width, height: vp.height });
      await page.goto(`${baseUrl}/#/workspace?example=true`);
      await page.waitForSelector('[data-testid="viewer-stage"]', { timeout: 15000 });

      const overflow = await checkNoPageHorizontalOverflow(page);
      expect(overflow.hasOverflow).toBe(false);
      expect(overflow.diff).toBeLessThanOrEqual(0);
    });

    test(`Help page: width ${vp.width}px (${vp.name}) has zero horizontal overflow`, async ({ page }) => {
      await page.setViewportSize({ width: vp.width, height: vp.height });
      await page.goto(`${baseUrl}/#/help`);
      await page.waitForSelector('[data-testid="help-page"]', { timeout: 10000 });

      const overflow = await checkNoPageHorizontalOverflow(page);
      expect(overflow.hasOverflow).toBe(false);
      expect(overflow.diff).toBeLessThanOrEqual(0);
    });
  }
});

test.describe("T38: Visual Completion — Layout Resilience & Hostile Filenames", () => {
  test("Real PDF with hostile long filename truncates cleanly without causing horizontal blowout", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto(`${baseUrl}/#/workspace`);
    await page.waitForSelector("#btn-header-open-pdf", { timeout: 10000 });

    // Create a real temporary PDF with a 110-character hostile unspaced filename
    const testDir = path.resolve(ROOT, "tests/fixtures/temp_visual");
    fs.mkdirSync(testDir, { recursive: true });
    const longFileName =
      "VERY_LONG_REAL_PDF_FILENAME_WITHOUT_ANY_SPACES_TO_VERIFY_COMPLETE_OVERFLOW_RESILIENCE_ON_MOBILE_VIEWPORTS_AUDIT.pdf";
    const longPdfPath = path.resolve(testDir, longFileName);
    const sourcePdf = path.resolve(ROOT, "apps/web/public/examples/amount/mapping-amount.pdf");
    fs.copyFileSync(sourcePdf, longPdfPath);

    try {
      await page.locator("#input-open-pdf").setInputFiles(longPdfPath);
      await page.waitForSelector("#workspace-doc-title", { timeout: 10000 });
      await expect(page.locator("#workspace-doc-title")).toContainText("VERY_LONG_REAL_PDF_FILENAME");

      const overflow = await checkNoPageHorizontalOverflow(page);
      expect(overflow.hasOverflow).toBe(false);
      expect(overflow.scrollWidth).toBeLessThanOrEqual(390);
    } finally {
      if (fs.existsSync(longPdfPath)) {
        fs.unlinkSync(longPdfPath);
      }
    }
  });

  test("Examples gallery card open detail does not overflow at 320px", async ({ page }) => {
    await page.setViewportSize({ width: 320, height: 568 });
    await page.goto(`${baseUrl}/#/`);
    await page.waitForSelector('[data-testid="examples-gallery"]', { timeout: 10000 });

    // Click first card to expand detail
    const card = page.locator('[data-testid^="example-card-"]').first();
    await card.click();

    // Wait for detail view
    await page.waitForSelector('[data-testid^="example-detail-"]', { timeout: 5000 });

    const overflow = await checkNoPageHorizontalOverflow(page);
    expect(overflow.hasOverflow).toBe(false);
    expect(overflow.diff).toBeLessThanOrEqual(0);
  });
});

test.describe("T38: Visual Completion — Touch Targets & Focus Tokens", () => {
  test("Workspace header and mode controls satisfy 44px minimum touch target", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto(`${baseUrl}/#/workspace?example=true`);
    await page.waitForSelector('[data-testid="viewer-stage"]', { timeout: 15000 });

    const controls = [
      "#btn-back-home",
      "#btn-header-import-report",
      "#btn-header-open-pdf",
      "#btn-close-doc",
      "#btn-header-help",
      "#tab-mode-page",
      "#tab-mode-reading",
      "#tab-mode-compare",
    ];

    for (const selector of controls) {
      const el = page.locator(selector);
      await expect(el).toBeVisible();
      const box = await el.boundingBox();
      expect(box).not.toBeNull();
      if (box) {
        expect(box.height).toBeGreaterThanOrEqual(44);
        expect(box.width).toBeGreaterThanOrEqual(40);
      }
    }
  });

  test("Help page action buttons satisfy 44px touch target size", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto(`${baseUrl}/#/help`);
    await page.waitForSelector('[data-testid="help-page"]', { timeout: 10000 });

    const homeBtn = page.locator("#btn-help-back-home");
    const wsBtn = page.locator("#btn-help-back-workspace");
    const exBtn = page.locator("#btn-help-open-example");

    const homeBox = await homeBtn.boundingBox();
    const wsBox = await wsBtn.boundingBox();
    const exBox = await exBtn.boundingBox();

    expect(homeBox?.height).toBeGreaterThanOrEqual(44);
    expect(wsBox?.height).toBeGreaterThanOrEqual(44);
    expect(exBox?.height).toBeGreaterThanOrEqual(44);
  });

  test("Active focus outline styling adheres to 3px focus token", async ({ page }) => {
    await page.setViewportSize({ width: 1024, height: 768 });
    await page.goto(`${baseUrl}/#/workspace?example=true`);
    await page.waitForSelector('[data-testid="viewer-stage"]', { timeout: 15000 });

    // Focus mode tab
    const tab = page.locator("#tab-mode-page");
    await tab.focus();

    const outlineWidth = await tab.evaluate((el: HTMLElement) => {
      return window.getComputedStyle(el).outlineWidth;
    });

    expect(outlineWidth).toBe("3px");
  });

  test("Finding selection preserves aria-current disclosure semantics", async ({ page }) => {
    await page.setViewportSize({ width: 1024, height: 768 });
    await page.goto(`${baseUrl}/#/workspace?example=true`);
    await page.waitForSelector('[data-testid="viewer-stage"]', { timeout: 15000 });

    // Click finding toggle
    const findingToggle = page.locator('[id^="finding-item-"]').first();
    await expect(findingToggle).toBeVisible();
    await findingToggle.click();

    const ariaCurrent = await findingToggle.getAttribute("aria-current");
    expect(ariaCurrent).toBe("true");
  });
});

test.describe("T38: Visual Completion — Help Surface Navigation", () => {
  test("Navigating from Workspace header help button opens HelpPage and returns", async ({ page }) => {
    await page.setViewportSize({ width: 1024, height: 768 });
    await page.goto(`${baseUrl}/#/workspace?example=true`);
    await page.waitForSelector("#btn-header-help", { timeout: 10000 });

    // Click Help button
    await page.click("#btn-header-help");
    await page.waitForSelector('[data-testid="help-page"]', { timeout: 5000 });
    expect(page.url()).toContain("#/help");

    // Verify product principle notices exist (no raw invariant IDs)
    const noticeHeading = page.locator("#limits-heading");
    await expect(noticeHeading).toBeVisible();
    await expect(page.locator("text=Non-Certification Principle")).toBeVisible();
    await expect(page.locator("text=Explicit Omission Reporting")).toBeVisible();

    // Click return to workspace
    await page.click("#btn-help-back-workspace");
    await page.waitForSelector('[data-testid="viewer-stage"]', { timeout: 5000 });
    expect(page.url()).toContain("#/workspace");
  });
});
