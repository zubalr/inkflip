import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createServer } from "node:http";
import { fileURLToPath } from "node:url";
import { dirname, join, resolve } from "node:path";
import { chromium } from "@playwright/test";
import { projectReport, renderReportHtml } from "../../../packages/reports/export/index.ts";
import { seal } from "../../../packages/contracts/src/index.ts";

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "../../..");
const VALID_DIR = join(ROOT, "planning/contracts/examples/valid");
const loadExample = (name) => JSON.parse(readFileSync(join(VALID_DIR, name), "utf8"));

async function serve(html) {
  const server = createServer((req, res) => {
    if (req.url === "/favicon.ico") {
      res.writeHead(204).end();
      return;
    }
    res.setHeader("Content-Type", "text/html; charset=utf-8");
    res.end(html);
  });
  await new Promise((resolve, reject) => {
    server.once("error", reject);
    server.listen(0, "127.0.0.1", resolve);
  });
  const origin = "http://127.0.0.1:" + server.address().port;
  return {
    origin,
    close: () => new Promise((resolve) => server.close(resolve)),
  };
}

async function overflowAt(page, width) {
  await page.setViewportSize({ width, height: 900 });
  return page.evaluate(() => ({
    scrollWidth: document.documentElement.scrollWidth,
    clientWidth: document.documentElement.clientWidth,
    h1: document.querySelector("h1")?.textContent ?? "",
    lede: document.querySelector(".lede")?.textContent ?? "",
    scripts: document.scripts.length,
    remote: performance.getEntriesByType("resource").filter((e) => {
      try {
        return new URL(e.name).origin !== location.origin;
      } catch {
        return false;
      }
    }).length,
  }));
}

test(
  "rendered HTML is readable at desktop, narrow, and print without remote loads",
  { timeout: 30000 },
  async () => {
    const named = structuredClone(loadExample("native-evidence.inkflip.json"));
    named.document.display_name = `${"year-end-statement-".repeat(8)}amount.pdf`;
    seal(named);
    const { report } = projectReport(named, { filename: true });
    const html = renderReportHtml(report);
    const replay = renderReportHtml(
      projectReport(loadExample("native-replay.inkflip.json"), { sourcePdf: "carry" }).report,
    );
    const failed = renderReportHtml(projectReport(loadExample("failed.json"), {}).report);

    const server = await serve(html);
    let browser;
    try {
      browser = await chromium.launch({ headless: true });
      const page = await browser.newPage();
      const remote = [];
      page.on("request", (req) => {
        const url = req.url();
        if (!url.startsWith(server.origin) && !url.startsWith("data:")) remote.push(url);
      });
      await page.goto(server.origin, { waitUntil: "load" });
      const desktop = await overflowAt(page, 1100);
      const narrow = await overflowAt(page, 390);
      assert.equal(desktop.scripts, 0);
      assert.equal(narrow.scripts, 0);
      assert.equal(desktop.remote, 0);
      assert.ok(desktop.scrollWidth <= desktop.clientWidth + 1, JSON.stringify(desktop));
      assert.ok(narrow.scrollWidth <= narrow.clientWidth + 1, JSON.stringify(narrow));
      assert.match(desktop.h1, /amount\.pdf/);
      assert.match(desktop.lede, /1 difference is included/);
      assert.deepEqual(remote, []);

      await page.setViewportSize({ width: 1100, height: 900 });
      await page.emulateMedia({ media: "print" });
      const printCss = await page.evaluate(() => getComputedStyle(document.body).backgroundColor);
      assert.equal(printCss, "rgb(255, 255, 255)");
      const printOverflow = await page.evaluate(() => document.documentElement.scrollWidth);
      assert.ok(printOverflow <= 1100);

      await page.setContent(replay, { waitUntil: "load" });
      const replayText = await page.locator("body").innerText();
      assert.match(replayText, /separately saved JSON includes the original PDF/);
      assert.equal(replayText.includes("Source PDF present in this report: yes"), false);
      assert.equal(replayText.includes("This report includes the original PDF"), false);

      await page.setContent(failed, { waitUntil: "load" });
      const failedText = await page.locator("body").innerText();
      assert.match(failedText, /No differences recorded/);
      assert.match(failedText, /did not finish \(failed\)/);
    } finally {
      if (browser) await browser.close();
      await server.close();
    }
  },
);
