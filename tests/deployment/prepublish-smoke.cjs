/* Prepublish smoke against the already-built production dist.
 * Subset of tests/deployment/production-journey.cjs: example opens, a real
 * disagreement is visible, default JSON export reimports, test hooks stay
 * off, and CSP/worker headers from dist/_headers are actually served.
 * Does not rebuild. Failure must prevent Vercel promotion.
 */
const { chromium } = require("@playwright/test");
const { createServer } = require("node:http");
const { existsSync, readFileSync, mkdirSync, writeFileSync } = require("node:fs");
const { extname, join, normalize, resolve, sep } = require("node:path");

const ROOT = resolve(__dirname, "..", "..");
const DIST = resolve(process.env.DIST_DIR || join(ROOT, "apps/web/dist"));
const EVIDENCE = join(__dirname, "evidence");

const MIME = {
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".mjs": "text/javascript; charset=utf-8",
  ".css": "text/css",
  ".json": "application/json",
  ".pdf": "application/pdf",
  ".wasm": "application/wasm",
  ".png": "image/png",
  ".svg": "image/svg+xml",
};

function parseHeadersFile(text) {
  const rules = [];
  let pattern = null;
  let headers = {};
  const flush = () => {
    if (pattern) rules.push({ pattern, headers });
    pattern = null;
    headers = {};
  };
  for (const raw of text.split(/\r?\n/)) {
    const line = raw.replace(/\s+$/, "");
    if (!line || line.startsWith("#")) continue;
    if (!line.startsWith(" ") && !line.startsWith("\t") && line.startsWith("/")) {
      flush();
      pattern = line.trim();
      continue;
    }
    const trimmed = line.trim();
    const idx = trimmed.indexOf(":");
    if (idx === -1 || !pattern) {
      throw new Error("malformed _headers: " + trimmed);
    }
    headers[trimmed.slice(0, idx).trim().toLowerCase()] = trimmed.slice(idx + 1).trim();
  }
  flush();
  return rules;
}

function headersFor(pathname, rules) {
  const out = {};
  for (const rule of rules) {
    const pat = rule.pattern;
    let match = false;
    if (pat === "/*") match = true;
    else if (pat.endsWith("/*")) match = pathname.startsWith(pat.slice(0, -1));
    else match = pathname === pat || (pat === "/index.html" && pathname === "/");
    if (match) Object.assign(out, rule.headers);
  }
  return out;
}

function startServer(dist, rules) {
  const root = resolve(dist) + sep;
  const server = createServer((req, res) => {
    const url = new URL(req.url || "/", "http://127.0.0.1");
    let pathname = decodeURIComponent(url.pathname);
    if (pathname === "/") pathname = "/index.html";
    const file = normalize(join(dist, pathname));
    const hdrs = {
      "X-Content-Type-Options": "nosniff",
      ...headersFor(pathname === "/index.html" ? "/" : pathname, rules),
      ...headersFor(pathname, rules),
    };
    if (!file.startsWith(root) || !existsSync(file)) {
      res.writeHead(404, hdrs).end("not found");
      return;
    }
    const body = readFileSync(file);
    res
      .writeHead(200, {
        ...hdrs,
        "Content-Type": MIME[extname(file)] || "application/octet-stream",
      })
      .end(body);
  });
  return new Promise((resolve, reject) => {
    server.once("error", reject);
    server.listen(0, "127.0.0.1", () => {
      const { port } = server.address();
      resolve({ server, baseUrl: `http://127.0.0.1:${port}` });
    });
  });
}

function record(results, step, ok, detail) {
  results.push({ step, ok, detail: detail || "" });
  console.log(`${ok ? "PASS" : "FAIL"} ${step}${detail ? " — " + detail : ""}`);
  if (!ok) process.exitCode = 1;
}

(async () => {
  if (!existsSync(join(DIST, "index.html")) || !existsSync(join(DIST, "_headers"))) {
    console.error("prepublish-smoke: missing production dist at", DIST);
    process.exit(1);
  }
  const rules = parseHeadersFile(readFileSync(join(DIST, "_headers"), "utf8"));
  const { server, baseUrl } = await startServer(DIST, rules);
  const results = [];
  const browser = await chromium.launch();
  try {
    const page = await browser.newPage();
    await page.goto(baseUrl + "/", { waitUntil: "networkidle", timeout: 60_000 });

    const hooks = await page.evaluate(() => {
      if (typeof __INKFLIP_TEST_HOOKS__ === "undefined") return "absent";
      return String(__INKFLIP_TEST_HOOKS__);
    });
    const inspect = await page.evaluate(() => typeof window.__inspect);
    record(results, "prod: test hooks off", hooks !== "true" && inspect === "undefined", `hooks=${hooks}`);

    const home = await page.request.get(baseUrl + "/");
    const csp = home.headers()["content-security-policy"] || "";
    record(results, "headers: CSP default-src none", /default-src 'none'/.test(csp), csp.slice(0, 80));
    record(results, "headers: worker-src self", /worker-src 'self'/.test(csp), csp.slice(0, 80));

    const workerPath = "/assets/tesseract/7.0.0/worker.min.js";
    if (existsSync(join(DIST, workerPath))) {
      const worker = await page.request.get(baseUrl + workerPath);
      const workerCsp = worker.headers()["content-security-policy"] || "";
      record(
        results,
        "headers: worker response keeps CSP",
        worker.ok() && /worker-src 'self'/.test(workerCsp),
        String(worker.status()),
      );
    }

    await page.locator("#btn-try-example").click();
    await page.waitForSelector("[id^=finding-item-]", { timeout: 30_000 });
    const findingText = await page.locator("[id^=finding-item-]").first().innerText();
    record(
      results,
      "example: finding card shows a real disagreement",
      /amount|reads|differ|\$/.test(findingText),
      findingText.split("\n")[0],
    );
    await page.locator("[id^=finding-item-]").first().click();
    const current = await page.locator("[id^=finding-item-]").first().getAttribute("aria-current");
    record(results, "example: a difference can be selected", current === "true", String(current));

    const jsonButton = page.getByRole("button", { name: "Save JSON (reopens in Inkflip)" });
    await jsonButton.waitFor({ state: "visible", timeout: 60_000 });
    await page.waitForFunction(() => {
      const buttons = [...document.querySelectorAll("button")];
      const b = buttons.find((x) => /Save JSON \(reopens in Inkflip\)/.test(x.textContent || ""));
      return b && !b.disabled;
    }, { timeout: 90_000 });
    const downloadPromise = page.waitForEvent("download", { timeout: 60_000 });
    await jsonButton.click();
    const download = await downloadPromise;
    mkdirSync(EVIDENCE, { recursive: true });
    const defaultPath = join(EVIDENCE, "prepublish-default.json");
    await download.saveAs(defaultPath);
    const payload = JSON.parse(readFileSync(defaultPath, "utf8"));
    record(results, "export default: JSON report downloaded", payload.kind === "report", payload.kind);
    record(
      results,
      "export default: original PDF omitted",
      payload.document.source_asset_id == null,
      String(payload.document.source_asset_id),
    );

    await page.locator("#btn-close-doc").click();
    await page.locator("#input-import-report").waitFor({ state: "attached", timeout: 15_000 });
    await page.locator("#input-import-report").setInputFiles(defaultPath);
    await page.waitForSelector("[id^=finding-item-]", { timeout: 60_000 });
    const reimported = await page.locator("[id^=finding-item-]").first().innerText();
    record(
      results,
      "reimport default: findings return",
      /amount|reads|differ|\$/.test(reimported),
      reimported.split("\n")[0],
    );
  } finally {
    await browser.close();
    await new Promise((resolve) => server.close(resolve));
    mkdirSync(EVIDENCE, { recursive: true });
    writeFileSync(
      join(EVIDENCE, "prepublish-results.json"),
      JSON.stringify({ dist: DIST, results, at: new Date().toISOString() }, null, 2),
    );
  }
  if (process.exitCode) {
    console.error("prepublish-smoke failed");
    process.exit(1);
  }
  console.log("prepublish-smoke ok");
})().catch((error) => {
  console.error("DRIVER ERROR:", error);
  process.exit(1);
});
