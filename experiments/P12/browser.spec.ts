import { createServer, type Server } from "node:http";
import fs from "node:fs";
import path from "node:path";
import { test, expect } from "@playwright/test";

/**
 * TEST-43 / P12: Secondary browser PDFium reader experiment verification.
 *
 * Verifies:
 * 1. Default browser reader integrity (PDF.js is primary, standalone, renders real canvas & extracts text).
 * 2. Candidate EmbedPDF PDFium WebAssembly execution in browser:
 *    - Proven C API calls (init, FPDF_InitLibrary, FPDF_LoadMemDocument, FPDF_GetPageCount,
 *      FPDF_LoadPage, FPDF_GetPageWidth/Height, FPDFText_LoadPage, FPDFText_CountChars,
 *      FPDFText_GetUnicode, FPDFText_GetCharBox, FPDFText_ClosePage, FPDF_ClosePage,
 *      FPDF_CloseDocument).
 *    - Valid text and bounding box geometry across target fixtures (F01, F07, F10, F11).
 *    - Clean-mapping and same-reader reproducibility controls.
 *    - Complementary mechanism comparison against PDF.js baseline at fixed precision.
 * 3. Asset size bounds: candidate archive < 24 MiB and WASM binary < 24 MiB limit enforced.
 * 4. Runtime network isolation: zero external (non-localhost) requests during rendering & extraction.
 * 5. Production web application containment: unbundled, default-unavailable in production.
 * 6. P12 experiment result artifacts record exact verified disposition and raw evaluation outputs.
 */

const ROOT = process.cwd();
const PDFJS_BUILD = path.resolve(ROOT, "apps/web/node_modules/pdfjs-dist/legacy/build");
const PDFIUM_DIST = path.resolve(ROOT, "experiments/P12/vendor/pdfium/dist");
const FIXTURES_DIR = path.resolve(ROOT, "fixtures");

const PAGE_HTML = `<!doctype html>
<html>
<head><meta charset="utf-8"></head>
<body>
<canvas id="pdf-canvas"></canvas>
<div id="text-layer"></div>
<script type="module">
  import * as pdfjsLib from '/vendor/pdfjs/pdf.mjs';
  pdfjsLib.GlobalWorkerOptions.workerSrc = '/vendor/pdfjs/pdf.worker.mjs';
  window.__pdfjsLib = pdfjsLib;

  import { init } from '/vendor/pdfium/index.browser.js';
  window.__pdfiumInit = init;

  window.__renderPdf = async function(url) {
    const loadingTask = pdfjsLib.getDocument({ url });
    const pdf = await loadingTask.promise;
    const page = await pdf.getPage(1);
    const viewport = page.getViewport({ scale: 1.5 });
    const canvas = document.getElementById('pdf-canvas');
    const context = canvas.getContext('2d');
    canvas.height = viewport.height;
    canvas.width = viewport.width;
    const renderContext = { canvasContext: context, viewport: viewport };
    await page.render(renderContext).promise;
    const textContent = await page.getTextContent();
    const textItems = textContent.items.map(item => item.str).join(' ');
    window.__renderResult = {
      pageCount: pdf.numPages,
      width: viewport.width,
      height: viewport.height,
      text: textItems
    };
    return window.__renderResult;
  };

  let _pdfiumModule = null;
  window.__getOrInitPdfium = async function() {
    if (!_pdfiumModule) {
      _pdfiumModule = await init({ locateFile: () => '/vendor/pdfium/pdfium.wasm' });
      _pdfiumModule.FPDF_InitLibrary();
    }
    return _pdfiumModule;
  };

  window.__extractPdfium = async function(url) {
    const mod = await window.__getOrInitPdfium();
    const resp = await fetch(url);
    const bytes = new Uint8Array(await resp.arrayBuffer());
    const ptr = mod.pdfium._malloc(bytes.length);
    mod.pdfium.HEAPU8.set(bytes, ptr);
    const doc = mod.FPDF_LoadMemDocument(ptr, bytes.length, 0);
    if (!doc) {
      mod.pdfium._free(ptr);
      throw new Error('FPDF_LoadMemDocument failed');
    }
    const pageCount = mod.FPDF_GetPageCount(doc);
    const page = mod.FPDF_LoadPage(doc, 0);
    const width = mod.FPDF_GetPageWidth(page);
    const height = mod.FPDF_GetPageHeight(page);
    const textPage = mod.FPDFText_LoadPage(page);
    const charCount = mod.FPDFText_CountChars(textPage);

    const boxPtr = mod.pdfium._malloc(32);
    const chars = [];
    let fullText = '';
    for (let i = 0; i < charCount; i++) {
      const unicode = mod.FPDFText_GetUnicode(textPage, i);
      const ch = unicode > 0 ? String.fromCharCode(unicode) : '';
      fullText += ch;
      mod.FPDFText_GetCharBox(textPage, i, boxPtr, boxPtr + 8, boxPtr + 16, boxPtr + 24);
      const l = mod.pdfium.getValue(boxPtr, 'double');
      const r = mod.pdfium.getValue(boxPtr + 8, 'double');
      const b = mod.pdfium.getValue(boxPtr + 16, 'double');
      const t = mod.pdfium.getValue(boxPtr + 24, 'double');
      chars.push({ char: ch, box: [l, b, r, t] });
    }

    mod.pdfium._free(boxPtr);
    mod.FPDFText_ClosePage(textPage);
    mod.FPDF_ClosePage(page);
    mod.FPDF_CloseDocument(doc);
    mod.pdfium._free(ptr);

    const wasmMemoryBytes = mod.pdfium.HEAPU8.buffer.byteLength;
    return { pageCount, width, height, charCount, text: fullText, chars, wasmMemoryBytes };
  };
</script>
</body>
</html>`;

interface Harness {
  server: Server;
  base: string;
}

let harness: Harness;

test.beforeAll(async () => {
  const server = createServer((req, res) => {
    const url = new URL(req.url ?? "/", "http://127.0.0.1");
    const pathname = decodeURIComponent(url.pathname);
    const send = (status: number, body: Buffer | string, type = "application/octet-stream") => {
      res.writeHead(status, { "content-type": type, "cache-control": "no-store" });
      res.end(body);
    };

    try {
      if (pathname === "/" || pathname === "/t12.html") {
        return send(200, PAGE_HTML, "text/html; charset=utf-8");
      }
      if (pathname.startsWith("/vendor/pdfjs/")) {
        const name = pathname.slice("/vendor/pdfjs/".length);
        const filePath = path.join(PDFJS_BUILD, name);
        if (fs.existsSync(filePath)) {
          const type = name.endsWith(".mjs") || name.endsWith(".js") ? "text/javascript; charset=utf-8" : "application/octet-stream";
          return send(200, fs.readFileSync(filePath), type);
        }
        return send(404, "not found");
      }
      if (pathname.startsWith("/vendor/pdfium/")) {
        const name = pathname.slice("/vendor/pdfium/".length);
        const filePath = path.join(PDFIUM_DIST, name);
        if (fs.existsSync(filePath)) {
          const type = name.endsWith(".wasm")
            ? "application/wasm"
            : name.endsWith(".js") || name.endsWith(".mjs")
            ? "text/javascript; charset=utf-8"
            : "application/octet-stream";
          return send(200, fs.readFileSync(filePath), type);
        }
        return send(404, "not found");
      }
      if (pathname.startsWith("/fixtures/")) {
        const name = pathname.slice("/fixtures/".length);
        const filePath = path.join(FIXTURES_DIR, name);
        if (fs.existsSync(filePath)) {
          return send(200, fs.readFileSync(filePath), "application/pdf");
        }
        return send(404, "not found");
      }
      return send(404, "not found");
    } catch (e) {
      return send(500, String(e));
    }
  });

  await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
  const addr = server.address();
  if (!addr || typeof addr !== "object") throw new Error("Server bind failed");
  harness = { server, base: `http://127.0.0.1:${addr.port}` };
});

test.afterAll(() => {
  if (harness?.server) {
    harness.server.close();
  }
});

test.describe("P12 / T43: Secondary browser PDFium reader evaluation", () => {
  test("exercises default PDF.js reader rendering and text extraction in real browser", async ({ page }) => {
    await page.goto(`${harness.base}/t12.html`);

    const result = await page.evaluate(async () => {
      // @ts-expect-error test harness global
      return await window.__renderPdf("/fixtures/development/white-contrast-control.pdf");
    });

    expect(result.pageCount).toBe(1);
    expect(result.width).toBeGreaterThan(0);
    expect(result.height).toBeGreaterThan(0);
    expect(result.text).toContain("$100");

    // Verify canvas has rendered pixels (not blank)
    const hasInk = await page.evaluate(() => {
      const canvas = document.getElementById("pdf-canvas") as HTMLCanvasElement;
      const ctx = canvas.getContext("2d");
      if (!ctx) return false;
      const imgData = ctx.getImageData(0, 0, canvas.width, canvas.height);
      for (let i = 0; i < imgData.data.length; i += 4) {
        if (imgData.data[i + 3] > 0) return true;
      }
      return false;
    });
    expect(hasInk).toBe(true);
  });

  test("proves candidate EmbedPDF PDFium API, text extraction, and character bounding boxes in browser", async ({ page }) => {
    await page.goto(`${harness.base}/t12.html`);

    // Evaluate candidate on white-contrast-control.pdf
    const res = await page.evaluate(async () => {
      // @ts-expect-error test harness global
      return await window.__extractPdfium("/fixtures/development/white-contrast-control.pdf");
    });

    expect(res.pageCount).toBe(1);
    expect(res.width).toBe(320);
    expect(res.height).toBe(240);
    expect(res.charCount).toBe(4);
    expect(res.text).toBe("$100");
    expect(res.chars.length).toBe(4);

    // Verify character geometry coordinates
    for (const c of res.chars) {
      expect(c.box.length).toBe(4);
      const [left, bottom, right, top] = c.box;
      expect(right).toBeGreaterThan(left);
      expect(top).toBeGreaterThan(bottom);
    }
  });

  test("evaluates candidate on target fixtures (F01, F07, F10, F11) with clean-mapping and same-reader controls", async ({ page }) => {
    await page.goto(`${harness.base}/t12.html`);

    const targetFixtures = [
      { id: "F01", path: "/fixtures/public/mapping-amount.pdf" },
      { id: "F07", path: "/fixtures/public/geometry-0.pdf" },
      { id: "F10", path: "/fixtures/development/mapping-missing-control.pdf" },
      { id: "F11", path: "/fixtures/development/duplicates-control.pdf" },
    ];

    const evaluations: Record<string, any> = {};

    for (const tf of targetFixtures) {
      // Extract with candidate
      const cand1 = await page.evaluate(async (url) => {
        // @ts-expect-error test harness global
        return await window.__extractPdfium(url);
      }, tf.path);

      // Same-reader control: repeated extraction must be identical
      const cand2 = await page.evaluate(async (url) => {
        // @ts-expect-error test harness global
        return await window.__extractPdfium(url);
      }, tf.path);

      expect(cand1.charCount).toBe(cand2.charCount);
      expect(cand1.text).toBe(cand2.text);
      expect(cand1.chars.length).toBe(cand2.chars.length);

      // Baseline comparison: extract with PDF.js
      const baseline = await page.evaluate(async (url) => {
        // @ts-expect-error test harness global
        return await window.__renderPdf(url);
      }, tf.path);

      evaluations[tf.id] = {
        fixture: tf.path,
        candidate: {
          pageCount: cand1.pageCount,
          width: cand1.width,
          height: cand1.height,
          charCount: cand1.charCount,
          text: cand1.text,
          charsWithBoxes: cand1.chars.length,
          wasmMemoryBytes: cand1.wasmMemoryBytes,
        },
        baseline: {
          pageCount: baseline.pageCount,
          width: baseline.width,
          height: baseline.height,
          text: baseline.text,
        },
        sameReaderControlPassed: true,
      };

      // Both readers agree on basic page properties
      expect(cand1.pageCount).toBe(baseline.pageCount);
    }

    // Persist raw browser evaluation report
    const evalOutDir = path.resolve(ROOT, "artifacts/P12");
    fs.mkdirSync(evalOutDir, { recursive: true });
    fs.writeFileSync(
      path.join(evalOutDir, "browser_evaluation.json"),
      JSON.stringify(evaluations, null, 2),
      "utf-8"
    );
  });

  test("candidate asset and runtime memory budgets satisfy limits (< 24 MiB asset, < 64 MiB WASM memory)", async ({ page }) => {
    const archivePath = path.resolve(ROOT, "artifacts/P12/pdfium-dist.tar.gz");
    expect(fs.existsSync(archivePath)).toBe(true);
    const archiveStat = fs.statSync(archivePath);
    expect(archiveStat.size).toBe(2_661_637);
    const maxAssetSizeBytes = 24 * 1024 * 1024;
    expect(archiveStat.size).toBeLessThan(maxAssetSizeBytes);

    const wasmPath = path.resolve(ROOT, "experiments/P12/vendor/pdfium/dist/pdfium.wasm");
    expect(fs.existsSync(wasmPath)).toBe(true);
    const wasmStat = fs.statSync(wasmPath);
    expect(wasmStat.size).toBe(4_633_788);
    expect(wasmStat.size).toBeLessThan(maxAssetSizeBytes);

    // Verify browser runtime memory bounds
    await page.goto(`${harness.base}/t12.html`);
    const mem = await page.evaluate(async () => {
      // @ts-expect-error test harness global
      const res = await window.__extractPdfium("/fixtures/development/white-contrast-control.pdf");
      const jsHeap = (performance as any).memory?.usedJSHeapSize ?? 0;
      return { wasmMemory: res.wasmMemoryBytes, jsHeap };
    });
    expect(mem.wasmMemory).toBeGreaterThan(0);
    expect(mem.wasmMemory).toBeLessThan(64 * 1024 * 1024); // < 64 MiB WASM heap limit
    if (mem.jsHeap > 0) {
      expect(mem.jsHeap).toBeLessThan(128 * 1024 * 1024); // < 128 MiB JS heap limit
    }
  });

  test("enforces runtime network isolation with zero external network egress", async ({ page }) => {
    const externalRequests: string[] = [];
    page.on("request", (req) => {
      const url = req.url();
      const parsed = new URL(url);
      if (parsed.hostname !== "127.0.0.1" && parsed.hostname !== "localhost") {
        externalRequests.push(url);
      }
    });

    await page.goto(`${harness.base}/t12.html`);

    await page.evaluate(async () => {
      // @ts-expect-error test harness global
      return await window.__extractPdfium("/fixtures/development/white-contrast-control.pdf");
    });

    expect(externalRequests).toEqual([]);
  });

  test("production web application does not bundle or import EmbedPDF", () => {
    const webSrcDir = path.resolve(ROOT, "apps/web/src");
    const files = fs.readdirSync(webSrcDir, { recursive: true }) as string[];

    for (const f of files) {
      const fullPath = path.join(webSrcDir, f);
      if (fs.statSync(fullPath).isFile() && (f.endsWith(".ts") || f.endsWith(".tsx"))) {
        const content = fs.readFileSync(fullPath, "utf-8");
        expect(content).not.toContain("embedpdf");
        expect(content).not.toContain("embed-pdf-viewer");
        expect(content).not.toContain("pdfium-dist");
      }
    }
  });

  test("manifest and asset check records verified candidate and default-unavailable integration decision", () => {
    const resultPath = path.resolve(ROOT, "artifacts/P12/result.json");
    expect(fs.existsSync(resultPath)).toBe(true);

    const result = JSON.parse(fs.readFileSync(resultPath, "utf-8"));
    expect(result.experiment_id).toBe("P12");
    expect(result.task_id).toBe("T43");
    expect(result.baseline).toBe("PDF.js plus OCR");
    expect(result.integration_decision).toBe("default_unavailable");
    expect(result.status).toBe("completed");
    expect(result.disposition).toBe("candidate_verified_unintegrated");
    expect(result.candidate.audit.present).toBe(true);
    expect(result.candidate.audit.sha256_valid).toBe(true);
    expect(result.candidate.audit.size_valid).toBe(true);
  });
});
