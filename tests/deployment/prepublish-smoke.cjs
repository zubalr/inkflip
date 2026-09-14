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

    // --- Real rendering: the page canvas must contain painted source
    // pixels, not a blank element. Wait for paint, then sample. ---
    await page
      .waitForFunction(
        () => {
          const c = document.getElementById("page-canvas-0");
          if (!c || !c.width || !c.height) return false;
          const d = c.getContext("2d").getImageData(0, 0, c.width, c.height).data;
          for (let i = 0; i < d.length; i += 400) {
            if (d[i + 3] > 0 && d[i] < 240) return true;
          }
          return false;
        },
        { timeout: 30_000 },
      )
      .catch(() => {});
    const paintInfo = await page.evaluate(() => {
      const c = document.getElementById("page-canvas-0");
      if (!c || !c.width || !c.height) return { canvas: false };
      const d = c.getContext("2d").getImageData(0, 0, c.width, c.height).data;
      const colors = new Set();
      let dark = 0;
      for (let i = 0; i < d.length; i += 400) {
        const r = d[i], g = d[i + 1], b = d[i + 2], a = d[i + 3];
        if (a > 0 && r < 245 && g < 245 && b < 245) dark++;
        if (colors.size < 64) colors.add((r << 16) | (g << 8) | b);
      }
      return { canvas: true, w: c.width, h: c.height, dark, colors: colors.size };
    });
    record(
      results,
      "render: page canvas painted with source pixels",
      Boolean(paintInfo.canvas) && paintInfo.dark > 20 && paintInfo.colors > 3,
      JSON.stringify(paintInfo),
    );

    // --- Highlight masks must be translucent, never opaque black. ---
    const highlights = await page.evaluate(() =>
      [...document.querySelectorAll("[id^=highlight-]")].map((el) => {
        const cs = getComputedStyle(el);
        const m = /rgba?\(([^)]+)\)/.exec(cs.fill || "");
        const fillAlpha = m && m[1].split(",").length === 4 ? parseFloat(m[1].split(",")[3]) : 1;
        const black = m ? m[1].split(",").slice(0, 3).every((v) => parseFloat(v) === 0) : false;
        return {
          id: el.id,
          alpha: fillAlpha * parseFloat(cs.fillOpacity || "1") * parseFloat(cs.opacity || "1"),
          black,
        };
      }),
    );
    const opaque = highlights.filter((h) => h.alpha >= 0.9);
    const blackMask = highlights.filter((h) => h.black && h.alpha >= 0.9);
    record(
      results,
      "highlights: translucent, no opaque masks",
      highlights.length > 0 && opaque.length === 0 && blackMask.length === 0,
      `${highlights.length} highlights` +
        (opaque.length ? ` opaque:${opaque.map((h) => h.id).join(",")}` : ""),
    );

    // --- Finding disclosure toggles closed and open on repeat clicks. ---
    const firstFinding = page.locator("[id^=finding-item-]").first();
    const expanded1 = await firstFinding.getAttribute("aria-expanded");
    await firstFinding.click();
    const collapsed = await firstFinding.getAttribute("aria-expanded");
    await firstFinding.click();
    const expanded2 = await firstFinding.getAttribute("aria-expanded");
    record(
      results,
      "disclosure: finding card toggles closed/open",
      expanded1 === "true" && collapsed === "false" && expanded2 === "true",
      `${expanded1}->${collapsed}->${expanded2}`,
    );

    // --- Compare names the finding's readers; both panes paint. ---
    await page.locator("#tab-mode-compare").click();
    await page.waitForSelector("#compare-panes-container", { timeout: 15_000 });
    const compare = await page.evaluate(() => {
      const sel = (id) => {
        const el = document.getElementById(id);
        if (!el) return null;
        const opt = el.tagName === "SELECT" ? el.options[el.selectedIndex] : el;
        return opt ? opt.textContent.trim() : null;
      };
      const painted = (paneId) => {
        const pane = document.getElementById(paneId);
        if (!pane) return false;
        const c = pane.querySelector("canvas");
        if (!c || !c.width) return false;
        const d = c.getContext("2d").getImageData(0, 0, c.width, c.height).data;
        for (let i = 0; i < d.length; i += 400) {
          if (d[i + 3] > 0 && d[i] < 240) return true;
        }
        return false;
      };
      return {
        left: sel("compare-reader-left"),
        right: sel("compare-reader-right"),
        leftPainted: painted("compare-pane-left"),
        rightPainted: painted("compare-pane-right"),
        readings: document.querySelectorAll("[id^=compare-reading-]").length,
      };
    });
    record(
      results,
      "compare: panes name the finding's readers",
      Boolean(compare.left) &&
        Boolean(compare.right) &&
        compare.left !== compare.right &&
        /pdf\.js|tesseract|pypdf|pdfium/i.test(compare.left + compare.right),
      `${compare.left} vs ${compare.right}`,
    );
    record(
      results,
      "compare: both panes painted + named readings shown",
      compare.leftPainted && compare.rightPainted && compare.readings >= 2,
      JSON.stringify(compare),
    );

    // --- Reading mode exposes the text layer as the main content. ---
    await page.locator("#tab-mode-reading").click();
    await page.waitForSelector("#accessible-text-equivalent", { timeout: 15_000 });
    const reading = await page.evaluate(() => {
      const layer = document.getElementById("accessible-text-equivalent");
      const stage = document.getElementById("viewer-stage");
      return {
        layerText: layer ? layer.innerText.length : 0,
        stageText: stage ? stage.innerText.length : 0,
        occurrences: document.querySelectorAll("#accessible-text-equivalent li").length,
      };
    });
    record(
      results,
      "reading: text layer is the main content",
      reading.layerText > 50 && reading.occurrences >= 1,
      JSON.stringify(reading),
    );

    // --- Fit: page must fit inside the pane with no page-level overflow. ---
    await page.locator("#tab-mode-page").click();
    await page.waitForSelector("#document-paper", { timeout: 15_000 });
    await page.locator("#btn-zoom-fit").click();
    await page.waitForTimeout(300);
    const fit = await page.evaluate(() => {
      const paper = document.getElementById("document-paper");
      const area = document.getElementById("viewer-paper-area");
      return {
        zoom: (document.getElementById("label-zoom") || {}).textContent,
        paperW: paper ? paper.offsetWidth : 0,
        areaW: area ? area.clientWidth : 0,
        docOverflow:
          document.documentElement.scrollWidth - document.documentElement.clientWidth,
      };
    });
    record(
      results,
      "controls: fit sizes page to pane, no horizontal overflow",
      fit.paperW > 0 && fit.paperW <= fit.areaW + 2 && fit.docOverflow <= 1,
      JSON.stringify(fit),
    );

    // --- Page navigation exists and reports page state honestly. ---
    const pageNav = await page.evaluate(() => ({
      indicator: (document.getElementById("page-indicator") || {}).textContent || "",
      prevDisabled: (document.getElementById("btn-page-prev") || {}).disabled,
      nextDisabled: (document.getElementById("btn-page-next") || {}).disabled,
    }));
    record(
      results,
      "controls: page navigation present and honest",
      /1/.test(pageNav.indicator) && pageNav.prevDisabled === true,
      JSON.stringify(pageNav),
    );

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

    // --- Public example dependencies: every linked asset must serve. ---
    const indexJson = JSON.parse(readFileSync(join(DIST, "examples/index.json"), "utf8"));
    for (const card of indexJson.cards || []) {
      const manifestRes = await page.request.get(baseUrl + card.manifest_url);
      const reportRes = await page.request.get(baseUrl + card.report_url);
      let ok = manifestRes.ok() && reportRes.ok();
      let detail = `manifest=${manifestRes.status()} report=${reportRes.status()}`;
      if (manifestRes.ok()) {
        const manifest = JSON.parse(await manifestRes.text());
        for (const [key, file] of Object.entries(manifest.files || {})) {
          if (file.download_url) {
            const r = await page.request.get(baseUrl + file.download_url);
            if (!r.ok()) {
              ok = false;
              detail += ` ${key}=${r.status()}`;
            }
          }
          if (file.report_file) {
            const r = await page.request.get(
              baseUrl + `/examples/${card.example_id}/${file.report_file}`,
            );
            if (!r.ok()) {
              ok = false;
              detail += ` ${file.report_file}=${r.status()}`;
            }
          }
        }
      }
      record(results, `example deps: ${card.example_id}`, ok, detail);
    }

    // --- Every public example loads through the real inspector route. ---
    for (const card of indexJson.cards || []) {
      await page.goto(`${baseUrl}/#/workspace?example=${card.example_id}`, {
        waitUntil: "networkidle",
        timeout: 60_000,
      });
      const opened = await page
        .waitForSelector("#viewer-stage", { timeout: 45_000 })
        .then(() => true)
        .catch(() => false);
      const importError = opened
        ? await page.locator("#import-error").count()
        : -1;
      record(
        results,
        `example opens: ${card.example_id}`,
        opened && importError === 0,
        opened ? `findings=${await page.locator("[id^=finding-item-]").count()}` : "no viewer-stage",
      );
    }

    // --- The retired standalone amount page must redirect into the
    // inspector and must not reference node_modules. ---
    const legacyPath = join(DIST, "examples/amount/index.html");
    if (existsSync(legacyPath)) {
      const legacy = readFileSync(legacyPath, "utf8");
      record(
        results,
        "legacy amount page redirects into inspector",
        /workspace\?example=amount/.test(legacy) && !/node_modules/.test(legacy),
        legacy.slice(0, 0),
      );
    } else {
      record(results, "legacy amount page redirects into inspector", true, "page removed");
    }
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
