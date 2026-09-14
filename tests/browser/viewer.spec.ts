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
    await page.goto(`${baseUrl}/#/workspace?example=fixture`);
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
    await expect(finding2).toHaveAttribute("aria-current", "true");

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

    // Keyboard selection verification (P3-F4): press 'n' to cycle to next finding
    await page.keyboard.press("n");
    const unknownFinding = page.locator("#finding-item-finding-page1-unknown");
    await expect(unknownFinding).toHaveAttribute("aria-current", "true");

    // Press 'p' to cycle back to finding-dup2
    await page.keyboard.press("p");
    await expect(finding2).toHaveAttribute("aria-current", "true");

    // Verify Enter on focused finding item selects it
    const finding1 = page.locator("#finding-item-finding-dup1");
    await finding1.focus();
    await page.keyboard.press("Enter");
    await expect(finding1).toHaveAttribute("aria-current", "true");
    const occ1HighlightAfter = page.locator("#highlight-occ-p0-dup1");
    await expect(occ1HighlightAfter).toBeVisible();
    const classAttrOcc1 = await occ1HighlightAfter.getAttribute("class");
    expect(classAttrOcc1).toContain("highlightSelected");

    await page.screenshot({
      path: "artifacts/tasks/T13/screenshots/zoom-rotate-duplicate-selection.png",
      fullPage: true,
    });
  });

  test("criterion 2: two views sync without scroll loop in compare mode", async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 800 });
    await page.goto(`${baseUrl}/#/workspace?example=fixture`);
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
    // Narrow mobile viewport (360px width)
    await page.setViewportSize({ width: 360, height: 800 });
    await page.goto(`${baseUrl}/#/workspace?example=fixture`);
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
      // Both panes must retain readable width (>= 280px) rather than being squeezed
      expect(leftBox.width).toBeGreaterThanOrEqual(280);
      expect(rightBox.width).toBeGreaterThanOrEqual(280);
    }

    // P2-F2 verification: ensure zero horizontal page scroll at 360px
    const scrollWidth = await page.evaluate(() => document.documentElement.scrollWidth);
    const clientWidth = await page.evaluate(() => document.documentElement.clientWidth);
    expect(scrollWidth).toBeLessThanOrEqual(clientWidth);

    await page.screenshot({
      path: "artifacts/tasks/T13/screenshots/narrow-stacked-compare.png",
      fullPage: true,
    });
  });

  test("criterion 4: unknown/page-only geometry stays page-level and does not draw coordinate box", async ({
    page,
  }) => {
    await page.setViewportSize({ width: 1280, height: 800 });
    await page.goto(`${baseUrl}/#/workspace?example=fixture`);
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
    await page.goto(`${baseUrl}/#/workspace?example=fixture`);
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

  test("document open and report import entry integration (P1-F1)", async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 800 });
    // Navigate to workspace without example
    await page.goto(`${baseUrl}/#/workspace`);
    await page.waitForSelector('[data-testid="file-drop"]');

    await expect(page.locator('[data-testid="file-drop"]')).toBeVisible();
    await expect(page.locator("#btn-import-report")).toBeVisible();
    await expect(page.locator("#btn-open-pdf")).toBeVisible();
    await expect(page.locator("#btn-empty-load-example")).toBeVisible();

    // Import a valid report JSON via the hidden file input
    const reportPath = path.resolve(
      process.cwd(),
      "planning/contracts/examples/valid/native-evidence.inkflip.json",
    );
    const fileInput = page.locator("#input-import-report");
    await fileInput.setInputFiles(reportPath);

    // Verify viewer stage mounts with the imported report
    await page.waitForSelector("#viewer-stage");
    await expect(page.locator("#document-paper")).toBeVisible();
    await expect(page.locator("#btn-close-doc")).toBeVisible();

    // Verify closing returns to intake state
    await page.locator("#btn-close-doc").click();
    await expect(page.locator('[data-testid="file-drop"]')).toBeVisible();
  });

  test("home landing view does not overflow at 360px viewport (P2-F2)", async ({ page }) => {
    await page.setViewportSize({ width: 360, height: 740 });
    await page.goto(`${baseUrl}/#/`);
    await page.waitForSelector("#hero-headline");

    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
    );
    expect(overflow).toBeLessThanOrEqual(1);

    // Verify key action buttons are visible and stacked cleanly
    await expect(page.locator("#btn-try-example")).toBeVisible();
    await expect(page.locator("#btn-open-report")).toBeVisible();
    await expect(page.locator("#btn-open-locally")).toBeVisible();
  });

  test("report import rejects degenerate/invalid JSON without white-screen crash (P2)", async ({
    page,
  }) => {
    await page.setViewportSize({ width: 1280, height: 800 });
    await page.goto(`${baseUrl}/#/workspace`);
    await page.waitForSelector('[data-testid="file-drop"]');

    const fs = await import("node:fs");
    const testDir = path.resolve(process.cwd(), "test-results");
    fs.mkdirSync(testDir, { recursive: true });

    // 1. Degenerate JSON with empty pages
    const degeneratePath = path.resolve(testDir, "degenerate-report.json");
    fs.writeFileSync(degeneratePath, '{"pages":[],"findings":[]}');
    await page.locator("#input-import-report").setInputFiles(degeneratePath);

    await expect(page.locator("#import-error")).toBeVisible();
    await expect(page.locator("#viewer-stage")).toHaveCount(0);
    const bodyText = (await page.locator("body").textContent()) || "";
    expect(bodyText.length).toBeGreaterThan(50);

    // 2. Malformed JSON syntax
    const badJsonPath = path.resolve(testDir, "malformed-syntax.json");
    fs.writeFileSync(badJsonPath, "{not json !!!");
    await page.locator("#input-import-report").setInputFiles(badJsonPath);
    await expect(page.locator("#import-error")).toBeVisible();
    await expect(page.locator("#viewer-stage")).toHaveCount(0);
  });

  test("PDF open candidate validation rejects non-PDF and does not fabricate findings (P1)", async ({
    page,
  }) => {
    await page.setViewportSize({ width: 1280, height: 800 });
    await page.goto(`${baseUrl}/#/workspace`);
    await page.waitForSelector('[data-testid="file-drop"]');

    const fs = await import("node:fs");
    const testDir = path.resolve(process.cwd(), "test-results");
    fs.mkdirSync(testDir, { recursive: true });

    // 1. Fake binary file masquerading as PDF without %PDF- magic
    const fakeExePath = path.resolve(testDir, "fake.pdf");
    fs.writeFileSync(fakeExePath, "MZ This is not a PDF binary file!");
    await page.locator("#input-open-pdf").setInputFiles(fakeExePath);

    await expect(page.locator("#import-error")).toBeVisible();
    expect(await page.locator("#import-error").textContent()).toContain(
      "This file could not be opened as a PDF",
    );
    await expect(page.locator("#viewer-stage")).toHaveCount(0);

    // 2. Real PDF magic but unparseable body: the real pipeline rejects it
    // honestly — error surfaces, no canned findings mount.
    const validPdfPath = path.resolve(testDir, "my-tax-return.pdf");
    fs.writeFileSync(validPdfPath, "%PDF-1.4\n%real-bytes\n1 0 obj\n<<>>\nendobj\n");
    await page.locator("#input-open-pdf").setInputFiles(validPdfPath);

    // Viewer stage with canned findings must NOT be mounted
    await expect(page.locator("#viewer-stage")).toHaveCount(0);
    // The parse failure surfaces as an honest open error
    await expect(page.locator("#import-error")).toBeVisible();
    expect(await page.locator("#import-error").textContent()).toContain("could not open this PDF");
  });

  test("canonical sealed report import mounts the viewer (P1)", async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 800 });
    await page.goto(`${baseUrl}/#/workspace`);
    await page.waitForSelector('[data-testid="file-drop"]');

    // The strict import gate (T24) verifies the report's seal — a
    // hand-edited page-level occurrence breaks the digest, so the sealed
    // canonical example is imported as-is. Page-level (polygon: null)
    // rendering itself is covered by criterion 4's example finding.
    const reportPath = path.resolve(
      process.cwd(),
      "planning/contracts/examples/valid/native-evidence.inkflip.json",
    );
    await page.locator("#input-import-report").setInputFiles(reportPath);

    // Must mount viewer stage cleanly on the sealed import
    await page.waitForSelector("#viewer-stage");
    await expect(page.locator("#document-paper")).toBeVisible();
    await expect(page.locator("#import-error")).toHaveCount(0);

    // Verify closing returns to intake state
    await page.locator("#btn-close-doc").click();
    await expect(page.locator('[data-testid="file-drop"]')).toBeVisible();
  });

  test("FileDrop drag-and-drop handles PDF candidate validation (P3)", async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 800 });
    await page.goto(`${baseUrl}/#/workspace`);
    const drop = page.locator('[data-testid="file-drop"]');
    await expect(drop).toBeVisible();

    // Drag-drop a valid PDF file via FileDrop
    const pdfBytes = new TextEncoder().encode("%PDF-1.4\n%test-drag-bytes\n");
    const dataTransfer = await page.evaluateHandle((bytes) => {
      const dt = new DataTransfer();
      const f = new File([new Uint8Array(bytes)], "dropped-document.pdf", {
        type: "application/pdf",
      });
      dt.items.add(f);
      return dt;
    }, Array.from(pdfBytes));

    await drop.dispatchEvent("drop", { dataTransfer });

    // Viewer stage must NOT mount canned findings
    await expect(page.locator("#viewer-stage")).toHaveCount(0);
    // The dropped bytes are unparseable — the real pipeline surfaces an
    // honest open error rather than a dead-end notice.
    const notice = page.locator("#import-error");
    await expect(notice).toBeVisible();
    expect(await notice.textContent()).toContain("could not open this PDF");
  });
});
