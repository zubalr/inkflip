import path from "node:path";
import { pathToFileURL } from "node:url";
import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

/**
 * TEST-07: Accessible reusable controls, navigation, and dialogs (T07).
 * Requirements:
 * - Keyboard can reach/operate all controls
 * - Escape/focus return works
 * - No focus trap outside modal
 * - Dynamic progress does not announce every OCR token
 * - No serious/critical automated violations in primitives
 */

const PREVIEW_PATH = "/src/components/Controls/preview.html";
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

test.describe("T07: Accessible Controls, Dialogs, and Navigation", () => {
  test("no serious or critical automated accessibility violations (WCAG 2.2 AA)", async ({
    page,
  }) => {
    await page.goto(`${baseUrl}${PREVIEW_PATH}`);
    await page.waitForSelector("main");

    const accessibilityScanResults = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"])
      .analyze();

    const seriousOrCritical = accessibilityScanResults.violations.filter(
      (v) => v.impact === "serious" || v.impact === "critical",
    );

    expect(seriousOrCritical).toEqual([]);
  });

  test("keyboard can reach and operate all controls (buttons, tabs, disclosures)", async ({
    page,
  }) => {
    await page.goto(`${baseUrl}${PREVIEW_PATH}`);
    await page.waitForSelector("main");

    // 1. Primary button click via keyboard
    const primaryBtn = page.locator("#btn-primary");
    await primaryBtn.focus();
    await expect(primaryBtn).toBeFocused();

    // 2. Tabs: roving tabindex and arrow key navigation
    const tab1 = page.locator("[role='tablist'] button[role='tab']").nth(0);
    const tab2 = page.locator("[role='tablist'] button[role='tab']").nth(1);
    const tab3 = page.locator("[role='tablist'] button[role='tab']").nth(2);

    await tab1.focus();
    await expect(tab1).toBeFocused();
    expect(await tab1.getAttribute("aria-selected")).toBe("true");

    // Press ArrowRight to move to Tab 2
    await page.keyboard.press("ArrowRight");
    await expect(tab2).toBeFocused();
    expect(await tab2.getAttribute("aria-selected")).toBe("true");
    expect(await tab1.getAttribute("aria-selected")).toBe("false");

    // Press End to move to Tab 3
    await page.keyboard.press("End");
    await expect(tab3).toBeFocused();
    expect(await tab3.getAttribute("aria-selected")).toBe("true");

    // Press Home to return to Tab 1
    await page.keyboard.press("Home");
    await expect(tab1).toBeFocused();
    expect(await tab1.getAttribute("aria-selected")).toBe("true");

    // 3. Disclosure: expand and collapse via keyboard
    const discTrigger = page.locator("#disc-1-trigger");
    await discTrigger.focus();
    await expect(discTrigger).toBeFocused();
    expect(await discTrigger.getAttribute("aria-expanded")).toBe("false");

    // Expand disclosure
    await page.keyboard.press("Enter");
    expect(await discTrigger.getAttribute("aria-expanded")).toBe("true");
    await expect(page.locator("#disc-1-panel")).toBeVisible();

    // Collapse disclosure
    await page.keyboard.press("Space");
    expect(await discTrigger.getAttribute("aria-expanded")).toBe("false");
    await expect(page.locator("#disc-1-panel")).not.toBeVisible();
  });

  test("escape key and focus return work cleanly on modal dialogs", async ({ page }) => {
    await page.goto(`${baseUrl}${PREVIEW_PATH}`);
    await page.waitForSelector("#btn-open-custom-modal");

    const openBtn = page.locator("#btn-open-custom-modal");
    await openBtn.focus();
    await expect(openBtn).toBeFocused();

    // Open modal via keyboard Enter
    await page.keyboard.press("Enter");

    const dialog = page.locator('[role="dialog"]');
    await expect(dialog).toBeVisible();

    // Verify focus moved into dialog
    await page.waitForTimeout(50);
    const isFocusInside = await page.evaluate(() => {
      const active = document.activeElement;
      const dlg = document.querySelector('[role="dialog"]');
      return dlg ? dlg.contains(active) : false;
    });
    expect(isFocusInside).toBe(true);

    // Press Escape to close modal
    await page.keyboard.press("Escape");
    await expect(dialog).not.toBeVisible();

    // Verify focus returned to the trigger button
    await expect(openBtn).toBeFocused();
  });

  test("focus is trapped inside modal and not trapped outside modal", async ({ page }) => {
    await page.goto(`${baseUrl}${PREVIEW_PATH}`);
    await page.waitForSelector("#btn-open-custom-modal");

    // Part A: Outside modal, Tab moves freely without getting trapped
    const primaryBtn = page.locator("#btn-primary");
    await primaryBtn.focus();
    await page.keyboard.press("Tab");
    const secondaryBtn = page.locator("#btn-secondary");
    await expect(secondaryBtn).toBeFocused();

    // Part B: Inside modal, Tab cycles within dialog elements
    const openBtn = page.locator("#btn-open-custom-modal");
    await openBtn.click();

    const dialog = page.locator('[role="dialog"]');
    await expect(dialog).toBeVisible();
    await page.waitForTimeout(50);

    // Collect focusable elements inside dialog
    const focusableCount = await page.evaluate(() => {
      const dlg = document.querySelector('[role="dialog"]');
      if (!dlg) return 0;
      return dlg.querySelectorAll(
        'button:not([disabled]), [href], input, [tabindex]:not([tabindex="-1"])',
      ).length;
    });
    expect(focusableCount).toBeGreaterThanOrEqual(2); // close btn + footer btn

    // Tab through all focusable elements + 1 more to test wrap-around
    for (let i = 0; i < focusableCount + 1; i++) {
      await page.keyboard.press("Tab");
      const focusInside = await page.evaluate(() => {
        const active = document.activeElement;
        const dlg = document.querySelector('[role="dialog"]');
        return dlg ? dlg.contains(active) : false;
      });
      expect(focusInside).toBe(true);
    }

    // Shift+Tab backwards wrap-around
    await page.keyboard.press("Shift+Tab");
    const focusStillInside = await page.evaluate(() => {
      const active = document.activeElement;
      const dlg = document.querySelector('[role="dialog"]');
      return dlg ? dlg.contains(active) : false;
    });
    expect(focusStillInside).toBe(true);

    // Close modal
    await page.keyboard.press("Escape");
    await expect(dialog).not.toBeVisible();
  });

  test("dynamic progress does not announce every OCR token (polite stage announcements only)", async ({
    page,
  }) => {
    await page.goto(`${baseUrl}${PREVIEW_PATH}`);
    await page.waitForSelector("#btn-update-token");

    const liveRegion = page.locator('[role="status"][aria-live="polite"]');
    await expect(liveRegion).toContainText("Rendering page 1…");

    // Click token update: visual detail changes, but live region does NOT change
    await page.locator("#btn-update-token").click();
    await expect(page.locator("text=2,841 characters read")).toBeVisible();
    await expect(liveRegion).toHaveText("Rendering page 1…"); // unchanged, no chatter!

    // Click stage update: named stage transition is politely announced
    await page.locator("#btn-update-stage").click();
    await expect(liveRegion).toHaveText("Reading text on page 2…");
  });

  test("interactive controls adhere to 44px minimum touch target size and 3px focus outline", async ({
    page,
  }) => {
    await page.goto(`${baseUrl}${PREVIEW_PATH}`);
    await page.waitForSelector("#btn-primary");

    // Target size checks: >= 44x44
    for (const selector of ["#btn-primary", "#btn-secondary", "#btn-icon"]) {
      const box = await page.locator(selector).boundingBox();
      expect(box).not.toBeNull();
      if (box) {
        expect(box.height).toBeGreaterThanOrEqual(44);
        expect(box.width).toBeGreaterThanOrEqual(44);
      }
    }

    // Focus outline check
    const primaryBtn = page.locator("#btn-primary");
    await primaryBtn.focus();

    const outline = await primaryBtn.evaluate((el) => {
      const style = getComputedStyle(el);
      return {
        outlineStyle: style.outlineStyle,
        outlineWidth: style.outlineWidth,
      };
    });

    expect(outline.outlineStyle).toBe("solid");
    expect(outline.outlineWidth).toBe("3px");
  });

  test("replace confirmation dialog displays canonical copy and restores focus on cancel", async ({
    page,
  }) => {
    await page.goto(`${baseUrl}${PREVIEW_PATH}`);
    await page.waitForSelector("#btn-open-replace-modal");

    const openReplaceBtn = page.locator("#btn-open-replace-modal");
    await openReplaceBtn.click();

    const dialog = page.locator('[role="dialog"]');
    await expect(dialog).toBeVisible();

    // Verify copy from copy.json
    await expect(dialog.locator("h2")).toHaveText("Open a different PDF?");
    await expect(
      dialog.locator("text=This clears the current file and its unsaved report"),
    ).toBeVisible();
    await expect(dialog.locator("button:has-text('Clear and open file')")).toBeVisible();
    await expect(dialog.locator("button:has-text('Keep this file')")).toBeVisible();

    // Click cancel button
    await dialog.locator("button:has-text('Keep this file')").click();
    await expect(dialog).not.toBeVisible();

    // Focus returns to the trigger button
    await expect(openReplaceBtn).toBeFocused();
  });
});
