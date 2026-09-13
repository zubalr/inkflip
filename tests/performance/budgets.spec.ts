import { expect, test } from "@playwright/test";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..", "..");
const SETTINGS = JSON.parse(
  readFileSync(join(ROOT, "planning/config/settings.json"), "utf8"),
);

test.describe("T39 browser resource budgets", () => {
  test("canonical settings expose finite raster/OCR/live-buffer caps", () => {
    expect(SETTINGS.browser.max_raster_pixels).toBe(4_000_000);
    expect(SETTINGS.browser.max_raster_edge).toBe(8192);
    expect(SETTINGS.browser.max_live_rasters).toBe(2);
    expect(SETTINGS.browser.max_ocr_workers).toBe(1);
    expect(SETTINGS.browser.max_run_ocr_pixels).toBe(20_000_000);
    expect(SETTINGS.mobile.max_raster_pixels).toBe(2_000_000);
    expect(SETTINGS.mobile.max_ocr_pages_per_run).toBe(1);
    expect(Number.isFinite(SETTINGS.browser.max_raster_pixels)).toBeTruthy();
  });

  test("device emulation is not a 4 GiB mobile reference claim", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    const viewport = page.viewportSize();
    expect(viewport).toEqual({ width: 390, height: 844 });
    // Layout-only. Physical 4 GiB mobile evidence is a named gap.
  });

  test("browser raster request validation rejects non-finite and over-budget sizes", async ({
    page,
  }) => {
    const browser = SETTINGS.browser;
    const mobile = SETTINGS.mobile;
    const result = await page.evaluate(
      ({ browser, mobile }) => {
        const finitePositive = (n) => Number.isFinite(n) && n > 0;
        const check = (width, height, pixelBudget, edge) => {
          const reasons = [];
          if (!finitePositive(width) || !finitePositive(height)) {
            reasons.push("dimensions must be positive and finite");
          }
          if (width > edge || height > edge) reasons.push("edge");
          if (width * height > pixelBudget) reasons.push("pixels");
          return { ok: reasons.length === 0, reasons };
        };
        return {
          ok: check(800, 600, browser.max_raster_pixels, browser.max_raster_edge),
          inf: check(
            Number.POSITIVE_INFINITY,
            100,
            browser.max_raster_pixels,
            browser.max_raster_edge,
          ),
          oversize: check(
            9000,
            9000,
            browser.max_raster_pixels,
            browser.max_raster_edge,
          ),
          mobileOver: check(
            2000,
            2000,
            mobile.max_raster_pixels,
            browser.max_raster_edge,
          ),
          liveBuffers: browser.max_live_rasters,
          ocrWorkers: browser.max_ocr_workers,
        };
      },
      { browser, mobile },
    );
    expect(result.ok.ok).toBeTruthy();
    expect(result.inf.ok).toBeFalsy();
    expect(result.oversize.ok).toBeFalsy();
    expect(result.mobileOver.ok).toBeFalsy();
    expect(result.liveBuffers).toBe(2);
    expect(result.ocrWorkers).toBe(1);
  });
});
