import { test } from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import {
  ARTIFACTS,
  FIXTURE,
  MAPPING_CONTROL_SHA,
  hostManifest,
  nativeInspect,
  sha256File,
  writeJson,
} from "./harness.mjs";
import {
  bootPage,
  extractInPage,
  startBrowserHarness,
} from "./browser-harness.mjs";

const ENGINES = ["chromium", "firefox", "webkit"];
const FIXTURE_NAME = "mapping-control.pdf";

async function loadPlaywright() {
  try {
    return await import("@playwright/test");
  } catch (error) {
    return { error: String(error) };
  }
}

async function launchEngine(playwright, name) {
  const launcher = playwright[name];
  if (!launcher) return { id: name, status: "unavailable", note: "unknown engine" };
  const profile = mkdtempSync(join(tmpdir(), `inkflip-p15-${name}-`));
  try {
    const context = await launcher.launch({
      headless: true,
    });
    const page = await context.newPage();
    await page.setViewportSize({ width: 1280, height: 800 });
    return {
      id: name,
      status: "executed",
      context,
      profile,
      page,
      version: context.version(),
    };
  } catch (error) {
    rmSync(profile, { recursive: true, force: true });
    return {
      id: name,
      status: "unavailable",
      note: String(error).slice(0, 500),
    };
  }
}

test("browser reader entry points run on available Playwright engines", { timeout: 180_000 }, async (t) => {
  assert.equal(sha256File(FIXTURE), MAPPING_CONTROL_SHA);
  const playwright = await loadPlaywright();
  const host = hostManifest();
  const platforms = [];
  const browserRows = [];

  if (playwright.error) {
    writeJson(join(ARTIFACTS, "platforms.json"), {
      host,
      platforms: ENGINES.map((id) => ({
        id: id === "webkit" ? "webkit-safari" : id,
        status: "unavailable",
        evidence: [],
        note: playwright.error,
      })),
    });
    assert.fail(`@playwright/test could not be imported: ${playwright.error}`);
  }

  const harness = await startBrowserHarness();
  t.after(async () => {
    await new Promise((resolve) => harness.server.close(resolve));
    rmSync(harness.tmp, { recursive: true, force: true });
  });

  for (const name of ENGINES) {
    const launched = await launchEngine(playwright, name);
    const receiptId = name === "webkit" ? "webkit-safari" : name;
    if (launched.status !== "executed") {
      platforms.push({
        id: receiptId,
        status: "unavailable",
        evidence: [],
        note: launched.note,
      });
      continue;
    }
    t.after(async () => {
      await launched.context.close();
      rmSync(launched.profile, { recursive: true, force: true });
    });
    const page = launched.page;
    const pageErrors = [];
    page.on("pageerror", (error) => pageErrors.push(String(error)));
    page.on("console", (msg) => {
      if (msg.type() === "error") pageErrors.push(`console:${msg.text()}`);
    });
    await bootPage(page, harness.base);
    const extracted = await extractInPage(page, {
      fixtureName: FIXTURE_NAME,
      pages: [0],
      capabilities: ["native_text", "ocr"],
    });
    assert.equal(extracted.sha256, MAPPING_CONTROL_SHA);
    assert.equal(extracted.pdfjs_version, "6.3.289");
    const text = extracted.results.find((r) => r.capability === "native_text");
    const ocr = extracted.results.find((r) => r.capability === "ocr");
    assert.equal(text.status, "completed", JSON.stringify({ text, pageErrors, directText: extracted.directText, workerIdentity: extracted.workerIdentity }));
    assert.equal(ocr.status, "unsupported", JSON.stringify(ocr));
    assert.ok(typeof text.emitted === "number");
    assert.equal(extracted.workerIdentity?.mentionsMainVersion, true, JSON.stringify(extracted.workerIdentity));
    const ua = await page.evaluate(() => navigator.userAgent);
    const evidenceRel = `artifacts/P15/${receiptId}.json`;
    const row = {
      engine: name,
      receipt_id: receiptId,
      playwright: "1.57.0",
      browser_version: launched.version,
      user_agent: ua,
      pdfjs_version: extracted.pdfjs_version,
      reader: extracted.reader,
      source_sha256: extracted.sha256,
      page_count: extracted.page_count,
      text,
      ocr,
      warm: extracted.warm,
      render: extracted.renderProbe,
      workerIdentity: extracted.workerIdentity,
      directText: extracted.directText,
      profile: launched.profile,
      harness: harness.base,
      note:
        name === "webkit"
          ? "Playwright WebKit automation with paired pdf.js worker; not a physical Safari device observation"
          : null,
    };
    writeJson(join(ARTIFACTS, `${receiptId}.json`), row);
    browserRows.push(row);
    platforms.push({
      id: receiptId,
      status: "executed",
      evidence: [evidenceRel],
      identity: {
        browser: `${name} ${launched.version}`,
        playwright: "1.57.0",
        pdfjs: extracted.pdfjs_version,
        user_agent: ua,
      },
      note: row.note,
    });
  }

  const chromiumOk = browserRows.find((r) => r.engine === "chromium" && r.text.status === "completed");
  const firefoxOk = browserRows.find((r) => r.engine === "firefox" && r.text.status === "completed");
  const webkitOk = browserRows.find((r) => r.engine === "webkit" && r.text.status === "completed");
  assert.ok(chromiumOk, "Chromium pdf.js adapter extract must complete");
  assert.ok(firefoxOk, "Firefox pdf.js adapter extract must complete");
  assert.ok(webkitOk, "WebKit pdf.js adapter extract must complete (ReadableStream async iterator repair)");

  const chromium = browserRows.find((r) => r.engine === "chromium");
  if (chromium) {
    const ctx = (await launchEngine(playwright, "chromium"));
    assert.equal(ctx.status, "executed", ctx.note);
    t.after(async () => {
      await ctx.context.close();
      rmSync(ctx.profile, { recursive: true, force: true });
    });
    const page = ctx.page;
    await bootPage(page, harness.base);
    const cold = await extractInPage(page, {
      fixtureName: FIXTURE_NAME,
      pages: [0],
      capabilities: ["native_text"],
    });
    const pagesAndRegion = await extractInPage(page, {
      fixtureName: FIXTURE_NAME,
      pages: [0],
      capabilities: ["native_text"],
      regionId: "selected-page-region",
    });
    const nativeDir = mkdtempSync(join(tmpdir(), "inkflip-p15-browser-native-"));
    const nativePath = join(nativeDir, "native.json");
    const native = nativeInspect(FIXTURE, nativePath);
    assert.equal(native.status, 0, native.stderr);
    const nativeReport = JSON.parse(readFileSync(nativePath, "utf8"));
    assert.equal(nativeReport.document.sha256, cold.sha256);
    assert.equal(nativeReport.checks[0].status, "completed");
    assert.equal(cold.results[0].status, "completed");
    const nativeText = (nativeReport.occurrences || []).map((o) => o.raw_text).join(" ");
    const browserText = (cold.results[0].raw_texts || []).join(" ");
    writeJson(join(ARTIFACTS, "cold-warm.json"), {
      cold_ms: cold.results[0].ms,
      warm_ms: cold.warm?.ms ?? null,
      same_handle_warm_completed: cold.warm?.status === "completed",
      second_context_source: cold.sha256,
    });
    writeJson(join(ARTIFACTS, "pages-regions.json"), {
      selected_pages: [0],
      region_id: pagesAndRegion.results[0].region_id,
      page_count: pagesAndRegion.page_count,
      note: "region_id is recorded on the check; pdf.js text extraction is still page-scoped, not a raster clip",
    });
    writeJson(join(ARTIFACTS, "semantic-equivalence-browser.json"), {
      source_hash_agreed: true,
      native_reader: nativeReport.readers[0],
      browser_reader: cold.reader,
      native_check: nativeReport.checks[0].status,
      browser_check: cold.results[0].status,
      raw_text_equal: nativeText === browserText,
      explanation:
        nativeText === browserText
          ? "raw text happened to match"
          : "expected engine difference: PDFium vs pdf.js getTextContent; rasters not compared",
    });
    writeJson(join(ARTIFACTS, "terminal-failures.json"), {
      unsupported_ocr: chromium.ocr,
      native_environment: nativeReport.execution?.environment ?? null,
    });
  }

  writeJson(join(ARTIFACTS, "platforms.json"), { host, platforms });
  writeJson(join(ARTIFACTS, "browser-parity.json"), {
    host,
    playwright: "1.57.0",
    engines: browserRows.map((r) => ({
      engine: r.engine,
      version: r.browser_version,
      pdfjs: r.pdfjs_version,
      source: r.source_sha256,
    })),
    safari_physical: "unavailable",
    linux_amd64_native: "unavailable",
  });
});
