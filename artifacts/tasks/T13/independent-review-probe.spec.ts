import path from "node:path";
import { pathToFileURL } from "node:url";
import { test, expect } from "@playwright/test";

/** Independent review probe for T13 — NOT part of the worker suite. */

const WEB_ROOT = path.resolve(process.cwd(), "apps/web");

let viteServer: any;
let baseUrl: string;

test.beforeAll(async () => {
  const viteModulePath = path.resolve(WEB_ROOT, "node_modules/vite/dist/node/index.js");
  const { createServer } = await import(pathToFileURL(viteModulePath).href);
  viteServer = await createServer({
    root: WEB_ROOT,
    server: { port: 0, strictPort: false, fs: { allow: [path.resolve(process.cwd())] } },
    logLevel: "silent",
  });
  await viteServer.listen();
  baseUrl = viteServer.resolvedUrls.local[0].replace(/\/$/, "");
});

test.afterAll(async () => {
  if (viteServer) await viteServer.close();
});

test.describe("T13 independent probes", () => {
  test("P1: rotation=270 + zoom=200% maps the correct duplicate via canonical geometry", async ({
    page,
  }) => {
    await page.setViewportSize({ width: 1280, height: 800 });
    await page.goto(`${baseUrl}/#/workspace?example=true`);
    await page.waitForSelector("#viewer-stage");

    // zoom to 200% (4 clicks)
    for (let i = 0; i < 4; i++) await page.locator("#btn-zoom-in").click();
    await expect(page.locator("#label-zoom")).toHaveText("200%");
    // rotate to 270 (3 clicks)
    for (let i = 0; i < 3; i++) await page.locator("#btn-rotate").click();
    await expect(page.locator("#btn-rotate")).toContainText("270°");

    // Click the SECOND duplicate finding
    await page.locator("#finding-item-finding-dup2").click();
    await expect(page.locator("#finding-item-finding-dup2")).toHaveAttribute(
      "aria-selected",
      "true",
    );

    const dup2 = page.locator("#highlight-occ-p0-dup2");
    const dup1 = page.locator("#highlight-occ-p0-dup1");
    await expect(dup2).toBeVisible();
    expect(await dup2.getAttribute("class")).toContain("highlightSelected");
    expect(await dup1.getAttribute("class")).not.toContain("highlightSelected");

    // Canonical rotation 270: (cx,cy)->(cy, w-cx); zoom s=2. w=612.
    // dup2 pt (100,350) -> (350,512) -> (700,1024)
    const pts2 = (await dup2.getAttribute("points")) || "";
    const pts1 = (await dup1.getAttribute("points")) || "";
    console.log("dup2 points:", pts2, "| dup1 points:", pts1);
    expect(pts2).toContain("700,1024");
    // dup1 pt (100,150) -> (150,512) -> (300,1024)
    expect(pts1).toContain("300,1024");
    // Distinct mapped positions despite identical normalized text
    expect(pts2).not.toEqual(pts1);

    // Now click the FIRST duplicate and confirm selection moves to the other box
    await page.locator("#finding-item-finding-dup1").click();
    expect(await dup1.getAttribute("class")).toContain("highlightSelected");
    expect(await dup2.getAttribute("class")).not.toContain("highlightSelected");
  });

  test("P2: keyboard paths select findings and occurrences", async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 800 });
    await page.goto(`${baseUrl}/#/workspace?example=true`);
    await page.waitForSelector("#viewer-stage");

    // Stage-level N/P shortcut: focus stage, press n -> next finding
    await page.locator("#viewer-stage").focus();
    await page.keyboard.press("n");
    await expect(page.locator("#finding-item-finding-dup1")).toHaveAttribute(
      "aria-selected",
      "true",
    );
    await page.keyboard.press("n");
    await expect(page.locator("#finding-item-finding-dup2")).toHaveAttribute(
      "aria-selected",
      "true",
    );
    await page.keyboard.press("p");
    await expect(page.locator("#finding-item-finding-dup1")).toHaveAttribute(
      "aria-selected",
      "true",
    );

    // Enter on a focused finding item selects it
    const item = page.locator("#finding-item-finding-page1-unknown");
    await item.focus();
    await page.keyboard.press("Enter");
    await expect(item).toHaveAttribute("aria-selected", "true");
    await expect(page.locator("#document-paper")).toHaveAttribute("data-page-index", "1");

    // Keyboard-reachable occurrence select in accessible layer (page-level occ)
    const selBtn = page.locator("#text-occ-occ-p1-pagelevel button");
    await selBtn.focus();
    await page.keyboard.press("Enter");
    await expect(selBtn).toHaveText("Selected");
    // page-level occurrence still draws no box
    await expect(page.locator("#highlight-occ-p1-pagelevel")).toHaveCount(0);
    await expect(page.locator("#page-level-geometry-notice")).toBeVisible();

    // Rotate+zoom then select exact-geometry occurrence via keyboard
    await page.keyboard.press("r");
    await page.keyboard.press("+");
    const occBtn = page.locator("#text-occ-occ-p1-item1 button");
    await occBtn.focus();
    await page.keyboard.press("Enter");
    const hi = page.locator("#highlight-occ-p1-item1");
    expect(await hi.getAttribute("class")).toContain("highlightSelected");
    // rotation 90: (120,200) -> (792-200,120)=(592,120); zoom 125 -> (740,150)
    const pts = (await hi.getAttribute("points")) || "";
    console.log("occ-p1-item1 points:", pts);
    expect(pts).toContain("740,150");
  });

  test("P3: scroll sync converges, no oscillation bounce", async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 800 });
    await page.goto(`${baseUrl}/#/workspace?example=true`);
    await page.waitForSelector("#viewer-stage");
    await page.locator("#tab-mode-compare").click();
    await expect(page.locator("#compare-panes-container")).toBeVisible();
    for (let i = 0; i < 4; i++) await page.locator("#btn-zoom-in").click();

    const left = page.locator("#compare-scroll-left");
    const right = page.locator("#compare-scroll-right");

    await left.evaluate((el) => {
      el.scrollTop = 400;
    });
    await page.waitForTimeout(100);

    // sample both panes over ~700ms to detect oscillation
    const samples: Array<[number, number]> = [];
    for (let i = 0; i < 10; i++) {
      samples.push([
        await left.evaluate((el) => el.scrollTop),
        await right.evaluate((el) => el.scrollTop),
      ]);
      await page.waitForTimeout(70);
    }
    console.log("samples after left scroll:", JSON.stringify(samples));
    // convergence: last three samples identical (no bounce oscillation)
    const tail = samples.slice(-3);
    for (const s of tail) {
      expect(s[0]).toBe(tail[0][0]);
      expect(s[1]).toBe(tail[0][1]);
    }
    expect(samples[samples.length - 1][0]).toBe(400);
    expect(samples[samples.length - 1][1]).toBeGreaterThan(100);

    // reverse direction: right -> left
    await right.evaluate((el) => {
      el.scrollTop = 40;
    });
    await page.waitForTimeout(300);
    const l1 = await left.evaluate((el) => el.scrollTop);
    const r1 = await right.evaluate((el) => el.scrollTop);
    await page.waitForTimeout(300);
    const l2 = await left.evaluate((el) => el.scrollTop);
    const r2 = await right.evaluate((el) => el.scrollTop);
    console.log("after right scroll:", l1, r1, "->", l2, r2);
    expect(r1).toBe(40);
    expect(l2).toBeLessThan(100);
    expect(l1).toBe(l2); // stable, no drift/bounce
    expect(r1).toBe(r2);
  });

  test("P4: 360px viewport stacks panes and keeps both reachable", async ({ page }) => {
    await page.setViewportSize({ width: 360, height: 740 });
    await page.goto(`${baseUrl}/#/workspace?example=true`);
    await page.waitForSelector("#viewer-stage");
    await page.locator("#tab-mode-compare").click();
    await expect(page.locator("#compare-panes-container")).toBeVisible();

    const lb = await page.locator("#compare-pane-left").boundingBox();
    const rb = await page.locator("#compare-pane-right").boundingBox();
    console.log("360px panes:", JSON.stringify(lb), JSON.stringify(rb));
    expect(lb).not.toBeNull();
    expect(rb).not.toBeNull();
    if (lb && rb) {
      expect(rb.y).toBeGreaterThanOrEqual(lb.y + lb.height - 5); // stacked
      // panes take full available container width (360 - outer gutters), not squeezed halves
      expect(lb.width).toBeGreaterThan(280);
      expect(rb.width).toBeGreaterThan(280);
      expect(rb.width).toBeGreaterThanOrEqual(lb.width - 2);
    }
    // outer page must not scroll horizontally
    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
    );
    console.log("horizontal overflow px:", overflow);
    expect(overflow).toBeLessThanOrEqual(2);
    // right pane is reachable by scrolling
    await page.locator("#compare-pane-right").scrollIntoViewIfNeeded();
    await expect(page.locator("#compare-pane-right")).toBeVisible();
    // evidence slip stacked below paper (reachable)
    await page.locator("#evidence-slip").scrollIntoViewIfNeeded();
    await expect(page.locator("#evidence-slip")).toBeVisible();
  });

  test("P5: unknown geometry + empty-doc edge cases do not crash", async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 800 });
    await page.goto(`${baseUrl}/#/workspace`); // no example
    await page.waitForSelector("#btn-load-demo");
    // empty workspace shows no viewer, doesn't crash
    await expect(page.locator("#viewer-stage")).toHaveCount(0);
    await page.locator("#btn-load-demo").click();
    await page.waitForSelector("#viewer-stage");

    // unknown-geometry finding via keyboard nav to last finding
    await page.locator("#viewer-stage").focus();
    await page.keyboard.press("n");
    await page.keyboard.press("n");
    await page.keyboard.press("n"); // wraps to page-level finding
    await expect(page.locator("#document-paper")).toHaveAttribute("data-page-index", "1");
    await expect(page.locator("#page-level-geometry-notice")).toBeVisible();
    // rotate + zoom while page-level selected: still no box, no crash
    await page.keyboard.press("r");
    await page.keyboard.press("+");
    await expect(page.locator("#highlight-occ-p1-pagelevel")).toHaveCount(0);
    await expect(page.locator("#page-level-geometry-notice")).toBeVisible();

    // canvas text alternative reachable & labeled
    const layer = page.locator("#accessible-text-equivalent");
    await expect(layer).toHaveAttribute("role", "region");
    const canvas = page.locator("#page-canvas-1");
    await expect(canvas).toHaveAttribute("role", "img");
    expect((await canvas.getAttribute("aria-label")) || "").toContain("page 2");
  });
});
