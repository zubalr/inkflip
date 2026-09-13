// Loopback PDF.js adapter server for T46 browser parity (not a mock).
import { execFileSync } from "node:child_process";
import { existsSync, mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { createServer } from "node:http";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { ROOT } from "./harness.mjs";

export const PDFJS_BUILD = join(ROOT, "apps/web/node_modules/pdfjs-dist/legacy/build");
export const PDFJS_ASSETS = join(ROOT, "apps/web/public/assets/pdfjs/6.3.289");
export const PKG = join(ROOT, "packages/readers-pdfjs/src");
export const FIXTURE_PUBLIC = join(ROOT, "fixtures/public");
export const FIXTURE_DEV = join(ROOT, "fixtures/development");

export const ADAPTER_ARGS = {
  workerSrc: "/vendor/pdfjs/pdf.worker.mjs",
  cMapUrl: "/assets/pdfjs/6.3.289/cmaps/",
  standardFontDataUrl: "/assets/pdfjs/6.3.289/standard_fonts/",
  wasmUrl: "/assets/pdfjs/6.3.289/wasm/",
  iccUrl: "/assets/pdfjs/6.3.289/iccs/",
};

const MIME = {
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".mjs": "text/javascript; charset=utf-8",
  ".pdf": "application/pdf",
  ".bcmap": "application/octet-stream",
  ".wasm": "application/wasm",
  ".icc": "application/vnd.iccprofile",
  ".icm": "application/vnd.iccprofile",
};

const PAGE_HTML = `<!doctype html>
<meta charset="utf-8">
<title>inkflip t46 browser parity</title>
<script type="module" src="/boot.mjs"></script>
`;

const BOOT_JS = `const proto = globalThis.ReadableStream && ReadableStream.prototype;
globalThis.__t46ready = false;
globalThis.__t46error = null;
if (proto && typeof proto[Symbol.asyncIterator] !== 'function') {
  proto[Symbol.asyncIterator] = async function* () {
    const reader = this.getReader();
    try {
      while (true) {
        const { done, value } = await reader.read();
        if (done) return;
        yield value;
      }
    } finally {
      reader.releaseLock();
    }
  };
}
Promise.all([
  import('/vendor/pdfjs/pdf.mjs').then((m) => { globalThis.__pdfjs = m; }),
  import('/bundle.js'),
]).then(() => { globalThis.__t46ready = true; })
  .catch((e) => { globalThis.__t46error = String(e && e.stack || e); });
`;

function mimeFor(pathname) {
  const dot = pathname.lastIndexOf(".");
  return (dot >= 0 && MIME[pathname.slice(dot)]) || "application/octet-stream";
}

export async function startBrowserHarness() {
  if (!existsSync(join(PDFJS_BUILD, "pdf.mjs"))) {
    throw new Error(`pinned pdfjs-dist missing at ${PDFJS_BUILD}`);
  }
  const tmp = mkdtempSync(join(tmpdir(), "inkflip-p15-srv-"));
  const entry = join(tmp, "entry.mjs");
  const bundlePath = join(tmp, "bundle.js");
  writeFileSync(
    entry,
    [
      `import * as api from ${JSON.stringify(join(PKG, "index.ts"))};`,
      `globalThis.__t46 = { api };`,
    ].join("\n"),
  );
  execFileSync(
    "bun",
    ["build", "--target", "browser", "--format", "esm", "--outfile", bundlePath, entry],
    { cwd: ROOT, stdio: "pipe" },
  );

  const server = createServer((req, res) => {
    const url = new URL(req.url ?? "/", "http://127.0.0.1");
    const pathname = decodeURIComponent(url.pathname);
    const send = (status, body, type = "application/octet-stream") => {
      res.writeHead(status, {
        "content-type": type,
        "cache-control": "no-store",
        "content-security-policy":
          "default-src 'none'; script-src 'self'; worker-src 'self'; connect-src 'self'; img-src 'self' data: blob:; font-src 'self'; style-src 'none'; base-uri 'none'",
      });
      res.end(body);
    };
    try {
      if (pathname === "/" || pathname === "/t46.html") {
        return send(200, PAGE_HTML, "text/html; charset=utf-8");
      }
      if (pathname === "/boot.mjs") {
        return send(200, BOOT_JS, "text/javascript; charset=utf-8");
      }
      if (pathname === "/bundle.js") {
        return send(200, readFileSync(bundlePath), "text/javascript; charset=utf-8");
      }
      if (pathname.startsWith("/vendor/pdfjs/")) {
        const name = pathname.slice("/vendor/pdfjs/".length);
        if (!/^[A-Za-z0-9._-]+$/.test(name)) return send(403, "forbidden");
        return send(200, readFileSync(join(PDFJS_BUILD, name)), mimeFor(name));
      }
      if (pathname.startsWith("/assets/pdfjs/6.3.289/")) {
        const rel = pathname.slice("/assets/pdfjs/6.3.289/".length);
        const file = join(PDFJS_ASSETS, rel);
        if (!file.startsWith(PDFJS_ASSETS) || !existsSync(file)) return send(404, "not found");
        return send(200, readFileSync(file), mimeFor(file));
      }
      if (pathname.startsWith("/fixtures/")) {
        const name = pathname.slice("/fixtures/".length);
        if (!/^[A-Za-z0-9._-]+$/.test(name)) return send(403, "forbidden");
        for (const dir of [FIXTURE_PUBLIC, FIXTURE_DEV]) {
          const file = join(dir, name);
          if (existsSync(file)) return send(200, readFileSync(file), "application/pdf");
        }
        return send(404, "not found");
      }
      return send(404, "not found");
    } catch (error) {
      return send(500, String(error));
    }
  });
  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  const address = server.address();
  if (address === null || typeof address !== "object") throw new Error("harness bind failed");
  return { server, base: `http://127.0.0.1:${address.port}`, tmp };
}

export async function bootPage(page, base) {
  page.setDefaultTimeout(30_000);
  await page.goto(`${base}/t46.html`);
  await page.waitForFunction(() => globalThis.__t46ready || globalThis.__t46error);
  const bootError = await page.evaluate(() => globalThis.__t46error ?? null);
  if (bootError) throw new Error(`module boot failure: ${bootError}`);
}

export async function extractInPage(page, request) {
  return page.evaluate(async ({ fixtureName, adapterArgs, pages, capabilities, regionId }) => {
    const { api } = globalThis.__t46;
    const pdfjs = globalThis.__pdfjs;
    if (typeof api.ensureReadableStreamAsyncIterator === 'function') {
      api.ensureReadableStreamAsyncIterator();
    }
    const adapter = api.createPdfJsReader({ pdfjs, ...adapterArgs });
    const bytes = new Uint8Array(await (await fetch(`/fixtures/${fixtureName}`)).arrayBuffer());
    const sha = api.hexSha256(bytes);
    const workerSrc = adapterArgs.workerSrc;
    let workerIdentity = null;
    try {
      const workerText = await (await fetch(workerSrc)).text();
      workerIdentity = {
        url: workerSrc,
        bytes: workerText.length,
        mentionsMainVersion: workerText.includes(pdfjs.version),
        hasAsyncIterator: typeof ReadableStream.prototype[Symbol.asyncIterator] === 'function',
      };
    } catch (error) {
      workerIdentity = { url: workerSrc, error: String(error && error.message || error) };
    }
    let directText = null;
    try {
      pdfjs.GlobalWorkerOptions.workerSrc = workerSrc;
      const task = pdfjs.getDocument({ data: bytes.slice(), enableXfa: false, isEvalSupported: false });
      const doc = await task.promise;
      const page1 = await doc.getPage(1);
      const tc = await page1.getTextContent({ includeMarkedContent: true, disableNormalization: true });
      directText = {
        ok: true,
        items: tc.items.length,
        typeofGetText: typeof page1.getTextContent,
        hasStreamTextContent: typeof page1.streamTextContent === 'function',
      };
      await task.destroy();
    } catch (error) {
      directText = {
        ok: false,
        name: error && error.name,
        message: error && error.message,
        stack: String(error && error.stack || error).slice(0, 800),
      };
    }
    const handle = await adapter.open({ bytes, sha256: sha, generation: 1 });
    const meta = await adapter.pages(handle);
    const regions = regionId ? { [`native_text:p${pages[0]}`]: regionId } : undefined;
    const checks = adapter.plan(handle, { pages, capabilities, regions });
    const results = [];
    for (const check of checks) {
      const chunks = [];
      const t0 = performance.now();
      let outcome;
      let extractError = null;
      try {
        outcome = await adapter.extract(handle, check, (chunk) => chunks.push(chunk));
      } catch (error) {
        extractError = String(error && error.stack || error);
        outcome = { result: { status: "failed", reason: extractError }, emitted: 0 };
      }
      results.push({
        checkId: check.id,
        capability: check.capability,
        page_index: check.page_index,
        region_id: check.region_id,
        status: outcome.result.status,
        reason: outcome.result.reason,
        emitted: outcome.emitted,
        raw_texts: chunks.flat().map((o) => o.raw_text),
        ms: performance.now() - t0,
        extractError,
        workerSrc: pdfjs.GlobalWorkerOptions.workerSrc ?? null,
      });
    }
    const textCheck = checks.find((c) => c.capability === "native_text");
    let warm = null;
    if (textCheck) {
      const t1 = performance.now();
      const again = await adapter.extract(handle, textCheck, () => undefined);
      warm = {
        status: again.result.status,
        emitted: again.emitted,
        ms: performance.now() - t1,
      };
    }
    const described = adapter.describe();
    let renderProbe = null;
    const renderPlan = adapter.plan(handle, { pages, capabilities: ['render'] });
    const planned = renderPlan[0];
    if (planned) {
      try {
        const rendered = await adapter.extract(handle, planned, () => undefined);
        renderProbe = {
          status: rendered.result.status,
          reason: rendered.result.reason,
          widthPx: rendered.raster?.widthPx ?? null,
          heightPx: rendered.raster?.heightPx ?? null,
          hasPngLike: Boolean(rendered.raster?.imageData && rendered.raster.imageData.length > 0),
          fontFace: typeof FontFace === 'function',
          moduleWorker: typeof Worker === 'function',
        };
      } catch (error) {
        renderProbe = { status: 'failed', reason: String(error && error.message || error) };
      }
    }
    await adapter.close(handle);
    return {
      sha256: sha,
      pdfjs_version: pdfjs.version,
      page_count: meta.count,
      reader: described.readers[0],
      results,
      warm,
      directText,
      workerIdentity,
      renderProbe,
    };
  }, { adapterArgs: ADAPTER_ARGS, pages: [0], capabilities: ["native_text"], regionId: null, ...request });
}
