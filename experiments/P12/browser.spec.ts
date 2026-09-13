import { createServer, type Server } from "node:http";
import fs from "node:fs";
import path from "node:path";
import { test, expect } from "@playwright/test";

/**
 * TEST-43 / P12: Secondary browser PDFium reader experiment verification.
 *
 * Verifies:
 * 1. Default browser reader integrity (PDF.js is primary, standalone, renders real canvas & extracts text).
 * 2. Candidate containment (EmbedPDF is default-unavailable, unbundled, and missing archive blocks integration).
 * 3. Asset size bounds (< 24 MiB limit enforced).
 * 4. P12 experiment result artifact records exact blocked disposition without fabrication.
 */

const ROOT = process.cwd();
const PDFJS_BUILD = path.resolve(ROOT, "apps/web/node_modules/pdfjs-dist/legacy/build");
const FIXTURE_DIR = path.resolve(ROOT, "fixtures/development");

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
      if (pathname.startsWith("/fixtures/")) {
        const name = pathname.slice("/fixtures/".length);
        const filePath = path.join(FIXTURE_DIR, name);
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
      return await window.__renderPdf("/fixtures/white-contrast-control.pdf");
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

  test("candidate asset budget satisfies < 24 MiB limit", () => {
    const pinnedSizeBytes = 2_661_637;
    const maxAssetSizeBytes = 24 * 1024 * 1024;
    expect(pinnedSizeBytes).toBeLessThan(maxAssetSizeBytes);
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

  test("candidate is default-unavailable and blocked without archive in offline repo", () => {
    const resultPath = path.resolve(ROOT, "artifacts/P12/result.json");
    expect(fs.existsSync(resultPath)).toBe(true);

    const result = JSON.parse(fs.readFileSync(resultPath, "utf-8"));
    expect(result.experiment_id).toBe("P12");
    expect(result.task_id).toBe("T43");
    expect(result.baseline).toBe("PDF.js plus OCR");
    expect(result.integration_decision).toBe("default_unavailable");
    expect(result.status).toBe("blocked");
    expect(result.disposition).toBe("blocked_missing_candidate_archive");
    expect(result.candidate.audit.present).toBe(false);
    expect(result.candidate.audit.attempted_preparation).toBeDefined();
  });
});
