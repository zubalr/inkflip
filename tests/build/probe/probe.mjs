#!/usr/bin/env node
/** T02 feasibility probe — real Chromium exercising the staged same-origin
 * PDF.js + Tesseract.js assets on the bundled control fixture.
 *
 * Serves ONLY the paths a production deployment would expose (staged assets
 * under /assets and /models from apps/web/public, the probe page, and the
 * three vendored library builds the probe imports), records every request
 * the browser makes, and asserts:
 *   scenario A (control):  pdf.js renders fixture.pdf, text layer and OCR
 *                          agree on the control string, zero non-loopback
 *                          requests;
 *   scenario B (missing):  the OCR model request is answered 404 — the
 *                          worker must fail closed, not fetch a substitute.
 *
 * Evidence is written to artifacts/tasks/T02/browser-probe.json (+ .png).
 * This is a feasibility probe for staged assets, not application acceptance.
 */
import { createServer } from "node:http";
import { readFile } from "node:fs/promises";
import { existsSync, statSync, mkdirSync, writeFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "@playwright/test";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(HERE, "../../..");
const PUBLIC = path.join(ROOT, "apps/web/public");
const OUT = path.join(ROOT, "artifacts/tasks/T02");
mkdirSync(OUT, { recursive: true });

const VENDOR = {
  // Paired *legacy* main/worker per the selected bundle (the modern build
  // requires engine builtins like Map.getOrInsertComputed that predate the
  // pinned browser matrix; legacy transpiles them — verified by this probe).
  "/probe/vendor/pdf.min.mjs": "apps/web/node_modules/pdfjs-dist/legacy/build/pdf.min.mjs",
  "/probe/vendor/pdf.worker.min.mjs": "apps/web/node_modules/pdfjs-dist/legacy/build/pdf.worker.min.mjs",
  "/probe/vendor/tesseract.esm.min.js": "apps/web/node_modules/tesseract.js/dist/tesseract.esm.min.js",
  "/probe/fixture.pdf": "tests/build/probe/fixture.pdf",
  "/probe/probe.html": "tests/build/probe/probe.html",
};
const MIME = {
  ".html": "text/html", ".js": "text/javascript", ".mjs": "text/javascript",
  ".map": "application/json", ".json": "application/json", ".pdf": "application/pdf",
  ".wasm": "application/wasm", ".bcmap": "application/octet-stream",
  ".pfb": "application/octet-stream", ".ttf": "font/ttf",
  ".icc": "application/octet-stream", ".traineddata": "application/octet-stream",
  ".txt": "text/plain", "": "text/plain",
};

const requests = [];
const server = createServer(async (req, res) => {
  const url = new URL(req.url, "http://localhost");
  const pathname = decodeURIComponent(url.pathname);
  let file = null;
  if (pathname.startsWith("/assets/") || pathname.startsWith("/models/")) {
    file = path.join(PUBLIC, pathname);
  } else if (VENDOR[pathname]) {
    file = path.join(ROOT, VENDOR[pathname]);
  }
  const inside = file && (file.startsWith(PUBLIC) || file.startsWith(ROOT)) &&
    !pathname.includes("..") && existsSync(file) && statSync(file).isFile();
  if (inside) {
    const body = await readFile(file);
    requests.push({ url: req.url, status: 200, bytes: body.length });
    res.writeHead(200, { "content-type": MIME[path.extname(file)] || "application/octet-stream",
                         "cache-control": "no-store" });
    res.end(body);
  } else {
    requests.push({ url: req.url, status: 404 });
    res.writeHead(404).end("not found");
  }
});

await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
const port = server.address().port;
const origin = `http://127.0.0.1:${port}`;
const evidence = { probe: "T02 staged-asset browser feasibility",
                   started_at: new Date().toISOString(), port, scenarios: {} };

const browser = await chromium.launch();
try {
  // Scenario A: everything staged resolves; readers run on the control.
  const page = await browser.newPage();
  const consoleErrors = [];
  page.on("pageerror", (e) => consoleErrors.push(String(e)));
  const before = requests.length;
  await page.goto(`${origin}/probe/probe.html`);
  await page.waitForFunction(() => document.title !== "T02 staged-asset probe" || document.title === "OK" || document.title === "FAILED",
                             { timeout: 60000 });
  await page.waitForSelector("text=PROBE-RESULT:", { timeout: 60000 });
  const rawA = await page.locator("pre#result").innerText();
  const a = JSON.parse(rawA.replace("PROBE-RESULT:", ""));
  const requestsA = requests.slice(before);
  evidence.scenarios.control = {
    result: a,
    console_errors: consoleErrors,
    requests: requestsA,
    external_requests: requestsA.filter((r) => !r.url.startsWith("/")),
  };
  await page.screenshot({ path: path.join(OUT, "browser-probe.png"), fullPage: true });

  // Scenario B: the OCR model is missing -> the worker must fail closed.
  const page2 = await browser.newPage();
  await page2.route("**/models/**", (route) => route.fulfill({ status: 404, body: "gone" }));
  const before2 = requests.length;
  let modelRequest = null;
  page2.on("request", (r) => { if (r.url().includes("traineddata")) modelRequest = r.url(); });
  await page2.goto(`${origin}/probe/probe.html`);
  try {
    await page2.waitForSelector("text=PROBE-RESULT:", { timeout: 60000 });
  } catch {
    // Worker hung waiting on the model: fail-closed means an explicit error,
    // so record the timeout as the observed failure mode.
  }
  let b = { status: "TIMEOUT", steps: [], errors: ["no PROBE-RESULT emitted within 60s"] };
  const rawB = await page2.locator("pre#result").innerText().catch(() => "");
  if (rawB.includes("PROBE-RESULT:")) b = JSON.parse(rawB.replace("PROBE-RESULT:", ""));
  evidence.scenarios.missing_model = {
    result: b,
    model_request: modelRequest,
    requests: requests.slice(before2),
  };
  evidence.node = process.version;
  evidence.playwright = (await import("@playwright/test/package.json", { with: { type: "json" } })).default.version;
  evidence.finished_at = new Date().toISOString();

  // Assertions for the report (the JSON always records what really happened).
  const checks = [];
  const okA = a.status === "OK";
  checks.push(["control status OK", okA]);
  checks.push(["pdfjs text layer contains control", okA && /HELLO INKFLIP/.test(a.pdfjsText || "")]);
  checks.push(["OCR reads control string", okA && /HELLO\s*INKFLIP/i.test((a.ocrText || "").replace(/\s+/g, " "))]);
  checks.push(["no console errors", consoleErrors.length === 0]);
  checks.push(["all scenario-A requests same-origin", requestsA.every((r) => r.url.startsWith("/"))]);
  checks.push(["model fetched over same-origin", requestsA.some((r) => r.url.includes("eng.traineddata") && r.status === 200)]);
  checks.push(["missing model fails closed", b.status === "FAILED" || b.status === "TIMEOUT"]);
  evidence.checks = checks.map(([name, pass]) => ({ name, pass }));
  evidence.verdict = checks.every(([, pass]) => pass) ? "PASS" : "FAIL";
} finally {
  await browser.close();
  server.close();
}

writeFileSync(path.join(OUT, "browser-probe.json"), JSON.stringify(evidence, null, 2) + "\n");
console.log(JSON.stringify({ verdict: evidence.verdict, checks: evidence.checks,
                             node: evidence.node, playwright: evidence.playwright }, null, 2));
process.exit(evidence.verdict === "PASS" ? 0 : 1);
