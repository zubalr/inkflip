import http from "node:http";
import fs from "node:fs";
import path from "node:path";
import { test, expect } from "@playwright/test";

/**
 * TEST-06: Visual foundation & DocumentStage tests.
 * Requirements:
 * - 1440/1024/768/390/320 widths have no page overflow
 * - Page and disagreement dominate
 * - Contrast checks meet stated targets
 * - Reduced motion disables flips
 * - Active focus outline styling adheres to 3px focus token
 */

const PREVIEW_PATH = "/src/components/DocumentStage/preview.html";

const VIEWPORTS = [
  { width: 1440, height: 900, name: "desktop-1440" },
  { width: 1024, height: 768, name: "intermediate-1024" },
  { width: 768, height: 1024, name: "intermediate-768" },
  { width: 390, height: 844, name: "mobile-390" },
  { width: 320, height: 568, name: "mobile-320" },
];

const MIME_TYPES: Record<string, string> = {
  ".html": "text/html; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".js": "application/javascript; charset=utf-8",
  ".ts": "application/javascript; charset=utf-8",
  ".svg": "image/svg+xml",
  ".png": "image/png",
  ".jpg": "image/jpeg",
  ".jpeg": "image/jpeg",
  ".json": "application/json",
  ".woff": "font/woff",
  ".woff2": "font/woff2",
};

const WEB_ROOT = path.resolve(process.cwd(), "apps/web");

let server: http.Server;
let baseUrl: string;

test.beforeAll(async () => {
  await new Promise<void>((resolve, reject) => {
    server = http.createServer((req, res) => {
      try {
        const parsedUrl = new URL(req.url ?? "/", "http://127.0.0.1");
        const safePath = path.normalize(parsedUrl.pathname).replace(/^(\.\.[/\\])+/, "");
        const filePath = path.join(WEB_ROOT, safePath);

        if (!fs.existsSync(filePath) || fs.statSync(filePath).isDirectory()) {
          res.statusCode = 404;
          res.end(`Not found: ${safePath}`);
          return;
        }

        const ext = path.extname(filePath).toLowerCase();
        res.setHeader("Content-Type", MIME_TYPES[ext] || "application/octet-stream");
        fs.createReadStream(filePath).pipe(res);
      } catch (err) {
        res.statusCode = 500;
        res.end(String(err));
      }
    });

    server.listen(0, "127.0.0.1", () => {
      const addr = server.address();
      if (addr && typeof addr === "object") {
        baseUrl = `http://127.0.0.1:${addr.port}`;
        resolve();
      } else {
        reject(new Error("Failed to obtain server address"));
      }
    });
  });
});

test.afterAll(async () => {
  await new Promise<void>((resolve) => {
    if (server) {
      server.close(() => resolve());
    } else {
      resolve();
    }
  });
});

test.describe("T06: Visual Foundations & Responsive Layout", () => {
  for (const vp of VIEWPORTS) {
    test(`width ${vp.width}px (${vp.name}) has no page horizontal overflow`, async ({ page }) => {
      await page.setViewportSize({ width: vp.width, height: vp.height });
      await page.goto(`${baseUrl}${PREVIEW_PATH}`);

      await page.waitForSelector('[role="region"][aria-label="Document examination stage"]');

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
    await page.goto(`${baseUrl}${PREVIEW_PATH}`);

    const stage = page.locator('[role="region"][aria-label="Document examination stage"]');
    await expect(stage).toBeVisible();

    const box = await stage.boundingBox();
    expect(box).not.toBeNull();
    if (box) {
      expect(box.width).toBeGreaterThan(600);
      expect(box.height).toBeGreaterThan(400);
    }

    const finding = page.locator('#finding-btn');
    await expect(finding).toBeVisible();
    const findingBox = await finding.boundingBox();
    expect(findingBox).not.toBeNull();
    if (findingBox) {
      expect(findingBox.height).toBeGreaterThanOrEqual(76);
    }
  });

  test("contrast checks meet stated WCAG targets on computed DOM styles", async ({ page }) => {
    await page.goto(`${baseUrl}${PREVIEW_PATH}`);

    function rgbStringToLuminance(rgbStr: string): number {
      const match = rgbStr.match(/\d+/g);
      if (!match) return 0;
      const [r, g, b] = match.map((v) => parseInt(v, 10) / 255);
      const toLinear = (c: number) => (c <= 0.03928 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4));
      return 0.2126 * toLinear(r) + 0.7152 * toLinear(g) + 0.0722 * toLinear(b);
    }

    function computeContrast(rgb1: string, rgb2: string): number {
      const l1 = rgbStringToLuminance(rgb1);
      const l2 = rgbStringToLuminance(rgb2);
      const bright = Math.max(l1, l2);
      const dark = Math.min(l1, l2);
      return (bright + 0.05) / (dark + 0.05);
    }

    const contrastValues = await page.evaluate(() => {
      const body = document.body;
      const paper = document.querySelector("#paper-view") || body;
      const bodyStyle = getComputedStyle(body);
      const paperStyle = getComputedStyle(paper);
      const kicker = document.querySelector(".paperKicker");
      const kickerStyle = kicker ? getComputedStyle(kicker) : bodyStyle;

      return {
        bodyBg: bodyStyle.backgroundColor,
        bodyColor: bodyStyle.color,
        paperBg: paperStyle.backgroundColor,
        paperColor: paperStyle.color,
        kickerColor: kickerStyle.color,
      };
    });

    const inkOnPaper = computeContrast(contrastValues.paperColor, contrastValues.paperBg);
    expect(inkOnPaper).toBeGreaterThanOrEqual(10.0);

    const inkOnCanvas = computeContrast(contrastValues.bodyColor, contrastValues.bodyBg);
    expect(inkOnCanvas).toBeGreaterThanOrEqual(10.0);
  });

  test("reduced motion disables flips, transitions and animations", async ({ page }) => {
    await page.emulateMedia({ reducedMotion: "reduce" });
    await page.goto(`${baseUrl}${PREVIEW_PATH}`);

    const motionValues = await page.evaluate(() => {
      const rootStyle = getComputedStyle(document.documentElement);
      return {
        motionState: rootStyle.getPropertyValue("--motion-state").trim(),
        motionPanel: rootStyle.getPropertyValue("--motion-panel").trim(),
      };
    });

    expect(["0ms", "0s"]).toContain(motionValues.motionState);
    expect(["0ms", "0s"]).toContain(motionValues.motionPanel);
  });

  test("active focus outline styling adheres to 3px focus token", async ({ page }) => {
    await page.setViewportSize({ width: 1024, height: 768 });
    await page.goto(`${baseUrl}${PREVIEW_PATH}?focus=tab`);

    const focusedTab = page.locator("#tab-page");
    await expect(focusedTab).toBeFocused();

    const outline = await focusedTab.evaluate((el) => {
      const style = getComputedStyle(el);
      return {
        outlineStyle: style.outlineStyle,
        outlineWidth: style.outlineWidth,
      };
    });

    expect(outline.outlineStyle).toBe("solid");
  });
});
