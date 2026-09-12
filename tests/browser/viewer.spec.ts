import path from "node:path";
import { pathToFileURL } from "node:url";
import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

/**
 * TEST-13: Page, text and compare viewer integration browser verification (T13).
 *
 * Acceptance criteria:
 * 1. Click/keyboard finding selects correct duplicate/page after zoom/rotation.
 * 2. Two views sync without scroll loop.
 * 3. Narrow screen stacks instead of squeezing.
 * 4. Unknown geometry stays page-level.
 * 5. Canvas has equivalent reachable content and limits (WCAG 2.2 AA).
 */

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
      fs: {
        allow: [path.resolve(process.cwd())],
      },
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

test.describe("T13: Integrated Viewer & Evidence Navigation", () => {
  test("criterion 1: click/keyboard finding selects correct duplicate/page after zoom and rotation", async ({
    page,
  }) => {
    await page.setViewportSize({ width: 1280, height: 800 });
    await page.goto(`${baseUrl}/#/workspace?example=true`);
    await page.waitForSelector("#viewer-stage");

    // Zoom in to 150% (2 clicks on zoom-in)
    const zoomInBtn = page.locator("#btn-zoom-in");
    await zoomInBtn.click();
    await zoomInBtn.click();
    await expect(page.locator("#label-zoom")).toHaveText("150%");

    // Rotate 90 degrees
    const rotateBtn = page.locator("#btn-rotate");
    await rotateBtn.click();
    await expect(rotateBtn).toContainText("90°");

    // Select finding-dup2 (occurrence #2 of $1,000.00 at lower section)
    const finding2 = page.locator("#finding-item-finding-dup2");
    await expect(finding2).toBeVisible();
    await finding2.click();

    // Verify finding 2 is selected
    await expect(finding2).toHaveAttribute("aria-selected", "true");

    // Verify correct duplicate occurrence highlight is selected
    const occ2Highlight = page.locator("#highlight-occ-p0-dup2");
    await expect(occ2Highlight).toBeVisible();
    await expect(occ2Highlight).toHaveAttribute("data-ordinal", "2");
    const classAttr = await occ2Highlight.getAttribute("class");
    expect(classAttr).toContain("highlightSelected");

    // Verify occurrence 1 highlight is NOT selected
    const occ1Highlight = page.locator("#highlight-occ-p0-dup1");
    const classAttr1 = await occ1Highlight.getAttribute("class");
    expect(classAttr1).not.toContain("highlightSelected");

    await page.screenshot({
      path: "artifacts/tasks/T13/screenshots/zoom-rotate-duplicate-selection.png",
      fullPage: true,
    });
  });

  test("criterion 2: two views sync without scroll loop in compare mode", async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 800 });
    await page.goto(`${baseUrl}/#/workspace?example=true`);
    await page.waitForSelector("#viewer-stage");

    // Switch to compare mode
    const compareTab = page.locator("#tab-mode-compare");
    await compareTab.click();
    await expect(page.locator("#compare-panes-container")).toBeVisible();

    // Zoom to 200% so scrollbars are active
    const zoomInBtn = page.locator("#btn-zoom-in");
    await zoomInBtn.click();
    await zoomInBtn.click();
    await zoomInBtn.click();
    await zoomInBtn.click();

    const leftScroll = page.locator("#compare-scroll-left");
    const rightScroll = page.locator("#compare-scroll-right");

    await expect(leftScroll).toBeVisible();
    await expect(rightScroll).toBeVisible();

    // Scroll left pane and observe right pane synchronizes
    await leftScroll.evaluate((el) => {
      el.scrollTop = 120;
    });

    // Wait for frame sync
    await page.waitForTimeout(200);

    const rightScrollTop = await rightScroll.evaluate((el) => el.scrollTop);
    expect(rightScrollTop).toBeGreaterThan(50);

    // Scroll right pane back and observe left pane synchronizes without infinite loop
    await rightScroll.evaluate((el) => {
      el.scrollTop = 30;
    });

    await page.waitForTimeout(200);

    const leftScrollTop = await leftScroll.evaluate((el) => el.scrollTop);
    expect(leftScrollTop).toBeLessThan(60);

    await page.screenshot({
      path: "artifacts/tasks/T13/screenshots/compare-sync-scroll.png",
      fullPage: true,
    });
  });

  test("criterion 3: narrow screen stacks instead of squeezing in compare mode", async ({
    page,
  }) => {
    // Narrow mobile viewport (390px width)
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto(`${baseUrl}/#/workspace?example=true`);
    await page.waitForSelector("#viewer-stage");

    // Switch to compare mode
    await page.locator("#tab-mode-compare").click();
    await expect(page.locator("#compare-panes-container")).toBeVisible();

    const leftPane = page.locator("#compare-pane-left");
    const rightPane = page.locator("#compare-pane-right");

    const leftBox = await leftPane.boundingBox();
    const rightBox = await rightPane.boundingBox();

    expect(leftBox).not.toBeNull();
    expect(rightBox).not.toBeNull();

    if (leftBox && rightBox) {
      // Right pane must be stacked below left pane vertically
      expect(rightBox.y).toBeGreaterThanOrEqual(leftBox.y + leftBox.height - 5);
      // Both panes must retain readable width (>= 320px) rather than being squeezed
      expect(leftBox.width).toBeGreaterThanOrEqual(320);
      expect(rightBox.width).toBeGreaterThanOrEqual(320);
    }

    await page.screenshot({
      path: "artifacts/tasks/T13/screenshots/narrow-stacked-compare.png",
      fullPage: true,
    });
  });

  test("criterion 4: unknown/page-only geometry stays page-level and does not draw coordinate box", async ({
    page,
  }) => {
    await page.setViewportSize({ width: 1280, height: 800 });
    await page.goto(`${baseUrl}/#/workspace?example=true`);
    await page.waitForSelector("#viewer-stage");

    // Select the unknown / page-level finding on page 1
    const unknownFinding = page.locator("#finding-item-finding-page1-unknown");
    await expect(unknownFinding).toBeVisible();
    await unknownFinding.click();

    // Verify page index moved to Page 2 (index 1)
    const paper = page.locator("#document-paper");
    await expect(paper).toHaveAttribute("data-page-index", "1");

    // Verify page-level geometry notice is displayed
    const pageLevelNotice = page.locator("#page-level-geometry-notice");
    await expect(pageLevelNotice).toBeVisible();
    const noticeText = await pageLevelNotice.textContent();
    expect(noticeText).toContain("applies to Page 2 as a whole");
    expect(noticeText).toContain("No localized bounding coordinates exist");

    // Verify no false highlight box exists on the canvas overlay
    const falseHighlight = page.locator("#highlight-occ-p1-pagelevel");
    await expect(falseHighlight).toHaveCount(0);

    await page.screenshot({
      path: "artifacts/tasks/T13/screenshots/unknown-geometry-pagelevel.png",
      fullPage: true,
    });
  });

  test("criterion 5: canvas has equivalent reachable content and limits (WCAG 2.2 AA)", async ({
    page,
  }) => {
    await page.setViewportSize({ width: 1280, height: 800 });
    await page.goto(`${baseUrl}/#/workspace?example=true`);
    await page.waitForSelector("#viewer-stage");

    // Reachable accessible text layer
    const accessibleLayer = page.locator("#accessible-text-equivalent");
    await expect(accessibleLayer).toBeVisible();
    await expect(accessibleLayer).toHaveAttribute("role", "region");
    await expect(accessibleLayer).toHaveAttribute(
      "aria-label",
      "Document text equivalent and limits",
    );

    // Verify occurrences are listed with ordinals and text
    const textItems = page.locator("#accessible-text-equivalent li");
    const count = await textItems.count();
    expect(count).toBeGreaterThanOrEqual(3);

    // Verify limitations are published
    expect(await accessibleLayer.textContent()).toContain("OCR verification was not run on page 0");

    // Run axe-core automated accessibility audit
    const accessibilityScanResults = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"])
      .analyze();

    const seriousOrCritical = accessibilityScanResults.violations.filter(
      (v) => v.impact === "serious" || v.impact === "critical",
    );

    expect(seriousOrCritical).toEqual([]);

    await page.screenshot({
      path: "artifacts/tasks/T13/screenshots/accessible-text-layer.png",
      fullPage: true,
    });
  });
});
