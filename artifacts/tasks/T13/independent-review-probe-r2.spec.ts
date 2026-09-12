import path from "node:path";
import { pathToFileURL } from "node:url";
import { test, expect } from "@playwright/test";

/** Round-2 independent probes for T13 fixes. */

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

test.describe("T13 round-2 probes", () => {
  test("R1: no horizontal scroll at 360px in all app states", async ({ page }) => {
    await page.setViewportSize({ width: 360, height: 740 });
    // Home
    await page.goto(`${baseUrl}/#/`);
    await page.waitForSelector("#hero-headline");
    let overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
    );
    console.log("home 360 overflow:", overflow);
    expect(overflow).toBeLessThanOrEqual(1);

    // Workspace example, page mode
    await page.goto(`${baseUrl}/#/workspace?example=true`);
    await page.waitForSelector("#viewer-stage");
    overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
    );
    console.log("workspace page-mode 360 overflow:", overflow);
    expect(overflow).toBeLessThanOrEqual(1);

    // toolbar controls still reachable at 360
    await expect(page.locator("#btn-zoom-in")).toBeVisible();
    await expect(page.locator("#btn-rotate")).toBeVisible();
    await expect(page.locator("#tab-mode-compare")).toBeVisible();

    // compare mode
    await page.locator("#tab-mode-compare").click();
    await page.waitForSelector("#compare-panes-container");
    overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
    );
    console.log("compare 360 overflow:", overflow);
    expect(overflow).toBeLessThanOrEqual(1);
  });

  test("R2: report import mounts real report data; invalid JSON errors cleanly", async ({
    page,
  }) => {
    await page.setViewportSize({ width: 1280, height: 800 });
    await page.goto(`${baseUrl}/#/workspace`);
    await page.waitForSelector('[data-testid="file-drop"]');

    // valid canonical report
    const reportPath = path.resolve(
      process.cwd(),
      "planning/contracts/examples/valid/native-evidence.inkflip.json",
    );
    await page.locator("#input-import-report").setInputFiles(reportPath);
    await page.waitForSelector("#viewer-stage");
    const title = await page.locator(".documentTitle, [class*=documentTitle]").first().textContent();
    console.log("imported doc title:", title);
    // should NOT be the canned invoice
    const meta = await page.locator("header").first().textContent();
    console.log("header meta:", meta);

    // close and try invalid JSON
    await page.locator("#btn-close-doc").click();
    await page.waitForSelector('[data-testid="file-drop"]');
    const badPath = path.resolve(process.cwd(), "test-results", "bad-report.json");
    const fs = await import("node:fs");
    fs.mkdirSync(path.dirname(badPath), { recursive: true });
    fs.writeFileSync(badPath, "{not json !!!");
    await page.locator("#input-import-report").setInputFiles(badPath);
    await expect(page.locator("#import-error")).toBeVisible();
    console.log("import error text:", await page.locator("#import-error").textContent());
    await expect(page.locator("#viewer-stage")).toHaveCount(0);

    // degenerate JSON: valid JSON, wrong shape
    fs.writeFileSync(badPath, '{"pages":[],"findings":[]}');
    await page.locator("#input-import-report").setInputFiles(badPath);
    await page.waitForTimeout(500);
    const stageCount = await page.locator("#viewer-stage").count();
    const errCount = await page.locator("#import-error").count();
    const bodyText = await page.locator("body").textContent();
    console.log("empty-pages: stage=", stageCount, "err=", errCount, "body-has-error=", !!bodyText);
    // must not white-screen
    expect((bodyText || "").length).toBeGreaterThan(50);
  });

  test("R3: PDF open path behavior — does it show the user's file or canned data?", async ({
    page,
  }) => {
    await page.setViewportSize({ width: 1280, height: 800 });
    await page.goto(`${baseUrl}/#/workspace`);
    await page.waitForSelector('[data-testid="file-drop"]');

    const fs = await import("node:fs");
    const pdfPath = path.resolve(process.cwd(), "test-results", "my-tax-return.pdf");
    fs.mkdirSync(path.dirname(pdfPath), { recursive: true });
    fs.writeFileSync(pdfPath, "%PDF-1.4 fake review bytes");
    await page.locator("#input-open-pdf").setInputFiles(pdfPath);
    await page.waitForTimeout(800);

    const stageVisible = await page.locator("#viewer-stage").count();
    const header = await page.locator("header").first().textContent();
    const findingsCount = await page.locator("#findings-nav-list > div").count();
    const findingTitles = await page.locator("#findings-nav-list h3").allTextContents();
    console.log(
      "after pdf open: stage=",
      stageVisible,
      "| header=",
      header,
      "| findings=",
      findingsCount,
      "| titles=",
      JSON.stringify(findingTitles),
    );
    // record what actually happens for the review finding
  });

  test("R4: FileDrop drag path imports json; FileDrop has real affordance", async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 800 });
    await page.goto(`${baseUrl}/#/workspace`);
    const drop = page.locator('[data-testid="file-drop"]');
    await expect(drop).toBeVisible();
    const dropText = await drop.textContent();
    console.log("filedrop text:", (dropText || "").slice(0, 200));

    // simulate a real drag-drop of a JSON report through the FileDrop component
    const reportPath = path.resolve(
      process.cwd(),
      "planning/contracts/examples/valid/native-evidence.inkflip.json",
    );
    const fs = await import("node:fs");
    const reportBytes = fs.readFileSync(reportPath);
    const dataTransfer = await page.evaluateHandle((bytes) => {
      const dt = new DataTransfer();
      const f = new File([new Uint8Array(bytes)], "dropped-report.inkflip.json", {
        type: "application/json",
      });
      dt.items.add(f);
      return dt;
    }, Array.from(reportBytes));
    await drop.dispatchEvent("drop", { dataTransfer });
    await page.waitForTimeout(800);
    const stageCount = await page.locator("#viewer-stage").count();
    const header = await page.locator("header").first().textContent();
    console.log("after json drop: stage=", stageCount, "header=", header);
  });
});
import path from "node:path";
import { pathToFileURL } from "node:url";
import { test } from "@playwright/test";

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

test("home overflow culprits at 360px", async ({ page }) => {
  await page.setViewportSize({ width: 360, height: 740 });
  await page.goto(`${baseUrl}/#/`);
  await page.waitForSelector("#hero-headline");
  const report = await page.evaluate(() => {
    const vw = document.documentElement.clientWidth;
    const bad: string[] = [];
    document.querySelectorAll("*").forEach((el) => {
      const r = el.getBoundingClientRect();
      if (r.right > vw + 1) {
        bad.push(
          `${el.tagName.toLowerCase()}#${el.id || ""} right=${Math.round(r.right)} w=${Math.round(r.width)}`,
        );
      }
    });
    return { vw, scrollW: document.documentElement.scrollWidth, bad: bad.slice(0, 15) };
  });
  console.log(JSON.stringify(report));
});

test("degenerate import crash mode", async ({ page }) => {
  const fs = await import("node:fs");
  const p = path.resolve(process.cwd(), "test-results", "degenerate.json");
  fs.mkdirSync(path.dirname(p), { recursive: true });
  fs.writeFileSync(p, '{"pages":[],"findings":[]}');
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.goto(`${baseUrl}/#/workspace`);
  await page.waitForSelector('[data-testid="file-drop"]');
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  await page.locator("#input-import-report").setInputFiles(p);
  await page.waitForTimeout(800);
  const overlay = await page.locator("vite-error-overlay").count();
  const rootKids = await page.evaluate(
    () => document.getElementById("root")?.childElementCount ?? -1,
  );
  console.log("pageerrors:", JSON.stringify(errors.slice(0, 3)));
  console.log("vite-error-overlay count:", overlay, "| root children:", rootKids);
});
