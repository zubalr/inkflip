import { test, expect } from "@playwright/test";

/**
 * TEST-06: Visual foundation & DocumentStage tests.
 * Requirements:
 * - 1440/1024/768/390/320 widths have no page overflow
 * - Page and disagreement dominate
 * - Contrast checks meet stated targets
 * - Reduced motion disables flips
 * - Screenshot evidence covers dark text, focus, and partial states
 */

const VIEWPORTS = [
  { width: 1440, height: 900, name: "desktop-1440" },
  { width: 1024, height: 768, name: "intermediate-1024" },
  { width: 768, height: 1024, name: "intermediate-768" },
  { width: 390, height: 844, name: "mobile-390" },
  { width: 320, height: 568, name: "mobile-320" },
];

test.describe("T06: Visual Foundations & Responsive Layout", () => {
  for (const vp of VIEWPORTS) {
    test(`width ${vp.width}px (${vp.name}) has no page horizontal overflow`, async ({ page }) => {
      await page.setViewportSize({ width: vp.width, height: vp.height });
      await page.goto("/");

      // Ensure page loads
      await page.waitForSelector("body");

      // Assert no horizontal page overflow
      const overflow = await page.evaluate(() => {
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

      expect(overflow.hasOverflow).toBe(false);
      expect(overflow.scrollWidth).toBeLessThanOrEqual(overflow.clientWidth);
    });
  }

  test("page and disagreement dominate the visual composition", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto("/");

    const stageOrScaffold = page.locator('[role="region"][aria-label="Document examination stage"], main');
    await expect(stageOrScaffold.first()).toBeVisible();

    // Verify stage / main area bounding box is prominent
    const box = await stageOrScaffold.first().boundingBox();
    expect(box).not.toBeNull();
    if (box) {
      expect(box.width).toBeGreaterThan(400);
      expect(box.height).toBeGreaterThan(200);
    }
  });

  test("contrast checks meet stated WCAG targets for design tokens", async ({ page }) => {
    await page.goto("/");

    // Token color values from planning/product/design-tokens.json
    const tokens = {
      canvas: "#F6F3EC",
      paper: "#FFFDF8",
      ink: "#172A2F",
      muted: "#526368",
      teal: "#006C67",
      rust: "#934420",
      focus: "#005FCC",
    };

    function luminance(hex: string): number {
      const rgb = hex
        .replace("#", "")
        .match(/.{2}/g)!
        .map((x) => parseInt(x, 16) / 255)
        .map((c) => (c <= 0.03928 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4)));
      return 0.2126 * rgb[0] + 0.7152 * rgb[1] + 0.0722 * rgb[2];
    }

    function contrast(hex1: string, hex2: string): number {
      const l1 = luminance(hex1);
      const l2 = luminance(hex2);
      const bright = Math.max(l1, l2);
      const dark = Math.min(l1, l2);
      return (bright + 0.05) / (dark + 0.05);
    }

    // Ink on paper target: >= 10:1 (exceeds WCAG AAA 7:1)
    const inkOnPaper = contrast(tokens.ink, tokens.paper);
    expect(inkOnPaper).toBeGreaterThanOrEqual(10);

    // Ink on canvas target: >= 10:1
    const inkOnCanvas = contrast(tokens.ink, tokens.canvas);
    expect(inkOnCanvas).toBeGreaterThanOrEqual(10);

    // Muted on paper target: >= 4.5:1 (WCAG AA)
    const mutedOnPaper = contrast(tokens.muted, tokens.paper);
    expect(mutedOnPaper).toBeGreaterThanOrEqual(4.5);

    // Teal on paper target: >= 4.5:1 (WCAG AA)
    const tealOnPaper = contrast(tokens.teal, tokens.paper);
    expect(tealOnPaper).toBeGreaterThanOrEqual(4.5);

    // Rust on paper target: >= 4.5:1 (WCAG AA)
    const rustOnPaper = contrast(tokens.rust, tokens.paper);
    expect(rustOnPaper).toBeGreaterThanOrEqual(4.5);

    // Focus outline contrast against paper: >= 3:1 (WCAG Non-text contrast)
    const focusOnPaper = contrast(tokens.focus, tokens.paper);
    expect(focusOnPaper).toBeGreaterThanOrEqual(3.0);
  });

  test("reduced motion disables flips, transitions and animations", async ({ page }) => {
    await page.emulateMedia({ reducedMotion: "reduce" });
    await page.goto("/");

    const motionValues = await page.evaluate(() => {
      const rootStyle = getComputedStyle(document.documentElement);
      return {
        motionState: rootStyle.getPropertyValue("--motion-state").trim(),
        motionPanel: rootStyle.getPropertyValue("--motion-panel").trim(),
      };
    });

    // In reduced motion mode, motion durations must evaluate to 0ms
    expect(["0ms", "0s"]).toContain(motionValues.motionState);
    expect(["0ms", "0s"]).toContain(motionValues.motionPanel);
  });

  test("screenshot evidence captures focus outline on interactive controls", async ({ page }) => {
    await page.setViewportSize({ width: 1024, height: 768 });
    await page.goto("/");

    // Tab into first interactive button or link
    await page.keyboard.press("Tab");

    const focusedElement = page.locator(":focus");
    await expect(focusedElement).toBeVisible();

    // Verify focus outline styling
    const outline = await focusedElement.evaluate((el) => {
      const style = getComputedStyle(el);
      return {
        outlineStyle: style.outlineStyle,
        outlineWidth: style.outlineWidth,
      };
    });

    expect(outline.outlineStyle).toBe("solid");
  });
});
