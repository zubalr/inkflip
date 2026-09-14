/**
 * Accessibility behaviours that can be measured in an automated browser.
 *
 * These are layout, motion and focus facts, not assistive-technology results:
 * passing here says nothing about VoiceOver or Safari, which need the manual flow
 * recorded with this delivery. Each case asserts a computed value or a real
 * keyboard interaction rather than the presence of an ARIA attribute.
 */
import { test, expect } from "@playwright/test";
import { startProdServer, type ProdServerInstance } from "./prod_server.ts";

let prodServer: ProdServerInstance;
let baseUrl: string;

test.beforeAll(async () => {
  prodServer = await startProdServer();
  baseUrl = prodServer.baseUrl;
});

test.afterAll(async () => {
  await prodServer?.close();
});

test.describe("Accessibility: reflow, motion and focus", () => {
  test("a 400%-zoom-equivalent width reflows without horizontal overflow", async ({ page }) => {
    // 320 CSS px is the reflow width a 1280px viewport reaches at 400% zoom.
    await page.setViewportSize({ width: 320, height: 800 });
    await page.goto(`${baseUrl}/#/workspace`);
    await page.waitForSelector('[data-testid="file-drop"]');

    const overflow = await page.evaluate(() => ({
      scrollWidth: document.documentElement.scrollWidth,
      clientWidth: document.documentElement.clientWidth,
    }));
    expect(
      overflow.scrollWidth,
      `content must not overflow horizontally at 320px (${overflow.scrollWidth} > ${overflow.clientWidth})`,
    ).toBeLessThanOrEqual(overflow.clientWidth + 1);
  });

  test("reduced motion collapses transition and animation durations", async ({ page }) => {
    await page.emulateMedia({ reducedMotion: "reduce" });
    await page.goto(`${baseUrl}/#/help`);
    await page.waitForSelector('[data-testid="help-page"]');

    const durations = await page.evaluate(() => {
      const samples = Array.from(document.querySelectorAll("button, a, [role='dialog'], [data-testid]")).slice(0, 40);
      const toSeconds = (value: string) => value.split(",").map((part) => {
        const trimmed = part.trim();
        return trimmed.endsWith("ms") ? parseFloat(trimmed) / 1000 : parseFloat(trimmed) || 0;
      });
      return samples.flatMap((element) => {
        const style = getComputedStyle(element);
        return [...toSeconds(style.transitionDuration), ...toSeconds(style.animationDuration)];
      });
    });
    expect(durations.length).toBeGreaterThan(0);
    expect(
      Math.max(...durations),
      "reduced motion must not leave a visible transition or animation duration",
    ).toBeLessThan(0.05);
  });

  test("Help opens from the keyboard and Escape returns focus to its trigger", async ({ page }) => {
    await page.goto(`${baseUrl}/#/workspace`);
    await page.waitForSelector("#btn-header-help");

    await page.locator("#btn-header-help").focus();
    await page.keyboard.press("Enter");
    await expect(page.locator('[data-testid="help-page"]')).toBeVisible({ timeout: 15000 });

    await page.locator("#btn-guide-cli").focus();
    await page.keyboard.press("Enter");
    await expect(page.locator('[role="dialog"]')).toBeVisible({ timeout: 15000 });

    await page.keyboard.press("Escape");
    await expect(page.locator('[role="dialog"]')).toHaveCount(0, { timeout: 15000 });

    const active = await page.evaluate(() => (document.activeElement as HTMLElement | null)?.id ?? "");
    expect(active, "focus must return to the control that opened the dialog").toBe("btn-guide-cli");
  });

  test("tabbing from the top reaches a focusable control without a keyboard trap", async ({ page }) => {
    await page.goto(`${baseUrl}/#/workspace`);
    await page.waitForSelector('[data-testid="file-drop"]');

    const reached: string[] = [];
    for (let i = 0; i < 25; i += 1) {
      await page.keyboard.press("Tab");
      const id = await page.evaluate(() => (document.activeElement as HTMLElement | null)?.id ?? "");
      if (id) reached.push(id);
      if (reached.length >= 6) break;
    }
    expect(reached.length, "tabbing must reach real controls").toBeGreaterThanOrEqual(4);
    expect(new Set(reached).size, "tabbing must move, not stall on one element").toBeGreaterThan(1);
  });
});
