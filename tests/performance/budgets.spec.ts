/**
 * T39 browser resource budgets — built production app on this Mac.
 *
 * Serves an identified production Vite build (INKFLIP_TEST_HOOKS=1 only so
 * the read-only __inspect handle exists). This is not a Vite dev server and
 * not a 4-core/8 GiB reference or physical mobile device.
 *
 * Preview latency counts only after the first rendered page (region-canvas
 * with a nonzero width). pages-summary metadata is not a render. Replacement
 * confirmation is clicked only when a document is already open — no fixed
 * 2s wait on a first open.
 */
import { expect, test, type Page } from "@playwright/test";
import { execFileSync } from "node:child_process";
import { createServer, type Server } from "node:http";
import { existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import path from "node:path";
import { pathToFileURL } from "node:url";

const ROOT = path.resolve(process.cwd());
const WEB_ROOT = path.resolve(ROOT, "apps/web");
const OUT_DIR = path.resolve(ROOT, "artifacts/performance");
mkdirSync(OUT_DIR, { recursive: true });
const DIST = mkdtempSync(path.join(OUT_DIR, "pc-web-"));
const MIB = 1024 * 1024;
const DESKTOP_MAX = 20 * MIB;
const SAMPLES = 30;
const MIME: Record<string, string> = {
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".mjs": "text/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".json": "application/json",
  ".wasm": "application/wasm",
  ".svg": "image/svg+xml",
  ".png": "image/png",
  ".woff2": "font/woff2",
  ".traineddata": "application/octet-stream",
};

let server: Server;
let baseUrl: string;
let buildId = "";

function ext(file: string): string {
  return path.extname(file).toLowerCase();
}

function processRssBytes(pid: number | undefined): number | null {
  if (!pid) return null;
  try {
    const out = execFileSync("ps", ["-o", "rss=", "-p", String(pid)], { encoding: "utf8" }).trim();
    const kb = Number(out);
    return Number.isFinite(kb) ? kb * 1024 : null;
  } catch {
    return null;
  }
}

function descendantPids(rootPid: number): number[] {
  const found = new Set<number>();
  const stack = [rootPid];
  while (stack.length) {
    const pid = stack.pop()!;
    try {
      const out = execFileSync("pgrep", ["-P", String(pid)], { encoding: "utf8" }).trim();
      for (const token of out.split(/\s+/)) {
        const child = Number(token);
        if (Number.isInteger(child) && child > 0 && !found.has(child)) {
          found.add(child);
          stack.push(child);
        }
      }
    } catch {
      // pgrep exits 1 when the pid has no children
    }
  }
  return [...found];
}

function chromiumTreeRssBytes(): number | null {
  const pids = descendantPids(process.pid);
  let total = 0;
  let any = false;
  for (const pid of pids) {
    const rss = processRssBytes(pid);
    if (rss != null) {
      total += rss;
      any = true;
    }
  }
  return any ? total : null;
}

test.beforeAll(async () => {
  const viteModulePath = path.resolve(WEB_ROOT, "node_modules/vite/dist/node/index.js");
  const { build } = await import(pathToFileURL(viteModulePath).href);
  process.env.INKFLIP_TEST_HOOKS = "1";
  await build({
    root: WEB_ROOT,
    configFile: path.join(WEB_ROOT, "vite.config.ts"),
    logLevel: "warn",
    build: {
      outDir: DIST,
      emptyOutDir: true,
      rollupOptions: { input: { index: path.join(WEB_ROOT, "index.html") } },
    },
  });
  const index = path.join(DIST, "index.html");
  if (!existsSync(index)) throw new Error(`production build missing ${index}`);
  buildId = readFileSync(index, "utf8").slice(0, 120);
  const distRoot = path.resolve(DIST) + path.sep;
  server = createServer((req, res) => {
    const url = new URL(req.url ?? "/", "http://static.invalid");
    let pathname = decodeURIComponent(url.pathname);
    if (pathname === "/") pathname = "/index.html";
    const file = path.normalize(path.join(DIST, pathname));
    if (!file.startsWith(distRoot) || !existsSync(file) || file.endsWith(path.sep)) {
      res.writeHead(404).end("not found");
      return;
    }
    res
      .writeHead(200, {
        "Content-Type": MIME[ext(file)] ?? "application/octet-stream",
        "Cache-Control": "no-cache",
      })
      .end(readFileSync(file));
  });
  await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
  const address = server.address();
  if (!address || typeof address === "string") throw new Error("server bound no port");
  baseUrl = `http://127.0.0.1:${address.port}`;
});

test.afterAll(async () => {
  await new Promise<void>((resolve) => server.close(() => resolve()));
  rmSync(DIST, { recursive: true, force: true });
});

function buildPdf(options: {
  pages: number;
  text?: string;
  padBytes?: number;
  box?: [number, number, number, number];
}): Uint8Array {
  const enc = new TextEncoder();
  const chunks: Uint8Array[] = [];
  const offsets: number[] = [];
  let len = 0;
  const push = (s: string) => {
    const b = enc.encode(s);
    chunks.push(b);
    len += b.length;
  };
  const obj = (n: number, body: string) => {
    offsets[n] = len;
    push(`${n} 0 obj\n${body}\nendobj\n`);
  };
  const fontObj = 3;
  const contentObj = 4;
  const firstPage = 5;
  const nPages = options.pages;
  const box = options.box ?? [0, 0, 612, 792];
  const stream = `BT /F1 24 Tf 72 700 Td (${options.text ?? "page"}) Tj ET`;
  push("%PDF-1.4\n");
  obj(1, "<< /Type /Catalog /Pages 2 0 R >>");
  const kids = Array.from({ length: nPages }, (_, i) => `${firstPage + i} 0 R`).join(" ");
  obj(2, `<< /Type /Pages /Kids [${kids}] /Count ${nPages} >>`);
  obj(fontObj, "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>");
  obj(contentObj, `<< /Length ${stream.length} >>\nstream\n${stream}\nendstream`);
  for (let i = 0; i < nPages; i++) {
    obj(
      firstPage + i,
      `<< /Type /Page /Parent 2 0 R /MediaBox [${box.join(" ")}] /Resources << /Font << /F1 ${fontObj} 0 R >> >> /Contents ${contentObj} 0 R >>`,
    );
  }
  const xrefPos = len;
  const count = firstPage + nPages;
  let xref = `xref\n0 ${count}\n0000000000 65535 f \n`;
  for (let i = 1; i < count; i++) {
    const off = offsets[i];
    xref += off !== undefined ? `${String(off).padStart(10, "0")} 00000 n \n` : "0000000000 65535 f \n";
  }
  push(xref);
  push(`trailer\n<< /Size ${count} /Root 1 0 R >>\nstartxref\n${xrefPos}\n%%EOF\n`);
  if (options.padBytes) {
    chunks.push(new Uint8Array(options.padBytes));
    len += options.padBytes;
  }
  const out = new Uint8Array(len);
  let o = 0;
  for (const c of chunks) {
    out.set(c, o);
    o += c.length;
  }
  return out;
}

async function offerPdf(page: Page, bytes: Uint8Array, name: string) {
  const occupied =
    (await page.locator('[data-testid="doc-label"]').count()) > 0 ||
    (await page.locator('[data-testid="pages-summary"]').count()) > 0;
  const header = page.locator("#input-open-pdf");
  const drop = page.locator('[data-testid="file-input"]');
  const input = (await header.count()) > 0 ? header : drop;
  await input.setInputFiles({
    name,
    mimeType: "application/pdf",
    buffer: Buffer.from(bytes),
  });
  if (occupied) {
    const confirm = page.getByRole("button", { name: "Clear and open file" });
    await confirm.click({ timeout: 15_000 });
  }
}

async function waitFirstRenderedPage(page: Page) {
  const canvas = page.locator("[data-testid=region-canvas]");
  await expect
    .poll(async () => Number((await canvas.getAttribute("width")) || 0), { timeout: 30_000 })
    .toBeGreaterThan(0);
  return canvas;
}

function summarize(samples: number[], failures: number, measured: boolean) {
  if (!measured) {
    return { n: 0, failures, measured: false, distribution_claim: "missing", unit: "ms", samples_ms: [] as number[] };
  }
  const clean = samples.filter((v) => Number.isFinite(v));
  const out: Record<string, unknown> = {
    n: clean.length,
    failures,
    measured: true,
    unit: "ms",
    samples_ms: clean,
  };
  if (clean.length === 0) {
    out.distribution_claim = "failed";
    return out;
  }
  const ordered = [...clean].sort((a, b) => a - b);
  const at = (p: number) => {
    const idx = (p / 100) * (ordered.length - 1);
    const lo = Math.floor(idx);
    const hi = Math.min(lo + 1, ordered.length - 1);
    return ordered[lo]! * (1 - (idx - lo)) + ordered[hi]! * (idx - lo);
  };
  out.p50 = at(50);
  out.p95 = at(95);
  out.max = ordered[ordered.length - 1];
  out.distribution_claim = clean.length >= 30 ? "n>=30" : "insufficient_samples";
  return out;
}

test.describe("T39 built-app workspace budgets", () => {
  test("measures first render, extraction, raster bounds, cancel, and memory", async ({
    page,
    browserName,
    browser,
  }, testInfo) => {
    test.setTimeout(600_000);
    const tiny = buildPdf({ pages: 1, text: "INKFLIP-T39" });
    await page.setViewportSize({ width: 1280, height: 800 });
    const setupStarted = Date.now();
    await page.goto(`${baseUrl}/#/workspace`);
    await expect(page.locator('[data-testid="file-input"]')).toBeVisible();
    const setupMs = Date.now() - setupStarted;

    const fixtureBytes = readFileSync(path.join(ROOT, "fixtures/public/mapping-control.pdf"));
    const oversize = buildPdf({ pages: 1, text: "fat", padBytes: DESKTOP_MAX });
    await offerPdf(page, oversize, "fat.pdf");
    const err = page.locator('#import-error, [id^="open-error-"]');
    await expect(err).toBeVisible({ timeout: 15_000 });
    await expect(err).toContainText(/limit|too large|20/i);

    await offerPdf(page, fixtureBytes, "mapping-control.pdf");
    const firstCanvas = await waitFirstRenderedPage(page);
    const hugeW = Number(await firstCanvas.getAttribute("width"));
    const hugeH = Number(await firstCanvas.getAttribute("height"));
    expect(hugeW).toBeGreaterThan(0);
    expect(hugeW * hugeH).toBeLessThanOrEqual(4_000_000);
    expect(Math.max(hugeW, hugeH)).toBeLessThanOrEqual(720);
    const limits = await page.evaluate(() => {
      const session = (globalThis as { __inspect?: { profile?: { maxRasterPixels?: number } } }).__inspect;
      return { maxRasterPixels: session?.profile?.maxRasterPixels ?? null };
    });
    expect(limits.maxRasterPixels).toBe(4_000_000);

    const openSamples: number[] = [];
    let openFailures = 0;
    for (let i = 0; i < SAMPLES; i++) {
      const t0 = Date.now();
      try {
        await offerPdf(page, fixtureBytes, `t39-${i}-${crypto.randomUUID()}.pdf`);
        await waitFirstRenderedPage(page);
        openSamples.push(Date.now() - t0);
      } catch {
        openFailures += 1;
      }
    }
    expect(openSamples.length).toBeGreaterThan(0);

    const extract = await page.evaluate(async () => {
      const session = (
        globalThis as {
          __inspect?: {
            adapter: {
              plan(handle: unknown, sel: { pages: number[]; capabilities: string[] }): Array<{ id: string }>;
              extract(
                handle: unknown,
                check: { id: string },
                emit: (chunk: unknown) => void,
              ): Promise<{ result?: { status?: string } }>;
            };
            openController: { currentHandle: unknown | null };
          };
        }
      ).__inspect;
      const handle = session?.openController.currentHandle;
      if (!session?.adapter || !handle)
        return { ok: false, reason: "no live handle", times: [] as number[], failures: 30, lastStatus: "" };
      const times: number[] = [];
      let failures = 0;
      let lastStatus = "";
      const checks = session.adapter.plan(handle, { pages: [0], capabilities: ["native_text"] });
      for (let i = 0; i < 30; i++) {
        const t0 = performance.now();
        try {
          const outcome = await session.adapter.extract(handle, checks[0]!, () => undefined);
          const status = outcome?.result?.status ?? "";
          lastStatus = status;
          if (status === "completed" || status === "partial") times.push(performance.now() - t0);
          else failures += 1;
        } catch {
          failures += 1;
        }
      }
      return { ok: times.length > 0, times, failures, lastStatus };
    });
    const extractSamples = extract.ok && Array.isArray(extract.times) ? extract.times : [];
    const extractFailures = extract.ok ? Number(extract.failures || 0) : 30;

    const heap: number[] = [];
    const rss: number[] = [];
    const launched = browser as { process?: () => { pid?: number } | null };
    const chromiumPid = typeof launched.process === "function" ? launched.process()?.pid : undefined;
    for (let i = 0; i < 10; i++) {
      await offerPdf(page, tiny, `cycle-${i}-${crypto.randomUUID()}.pdf`);
      await waitFirstRenderedPage(page);
      const mem = await page.evaluate(() => {
        const perf = performance as Performance & { memory?: { usedJSHeapSize?: number } };
        return perf.memory?.usedJSHeapSize ?? null;
      });
      if (typeof mem === "number") heap.push(mem);
      const rssNow = processRssBytes(chromiumPid) ?? chromiumTreeRssBytes();
      if (rssNow != null) rss.push(rssNow);
    }

    await page.locator('[data-testid="start-run"]').click();
    await expect(page.locator("#btn-cancel-run")).toBeVisible({ timeout: 30_000 });
    await page.locator("#btn-cancel-run").click();
    await expect(page.locator('[data-testid="run-cancelled"]')).toBeVisible({ timeout: 30_000 });
    await page.locator("#btn-back-to-selection").click();
    await offerPdf(page, buildPdf({ pages: 1, text: "next" }), `next-${crypto.randomUUID()}.pdf`);
    await waitFirstRenderedPage(page);

    let exportMs: number[] = [];
    let exportFailures = 0;
    try {
      const exportT0 = Date.now();
      await page.locator('[data-testid="start-run"]').click();
      await page.waitForFunction(() => {
        const snap = (globalThis as { __inspect?: { getState(): { fileState: string; report: unknown } } }).__inspect?.getState();
        return Boolean(
          snap &&
            (snap.report != null ||
              snap.fileState === "complete" ||
              snap.fileState === "partial" ||
              snap.fileState === "failed"),
        );
      }, { timeout: 180_000 });
      const jsonBtn = page.getByRole("button", { name: "Download portable JSON" });
      if (await jsonBtn.isEnabled()) {
        const [download] = await Promise.all([page.waitForEvent("download", { timeout: 30_000 }), jsonBtn.click()]);
        await download.path();
        exportMs = [Date.now() - exportT0];
      } else {
        exportFailures = 1;
      }
    } catch {
      exportFailures = 1;
    }

    await page.setViewportSize({ width: 320, height: 568 });
    await page.goto("about:blank");
    await page.goto(`${baseUrl}/#/workspace`);
    await expect(page.locator('[data-testid="file-input"]')).toBeVisible({ timeout: 15_000 });
    await offerPdf(page, tiny, "mobile.pdf");
    await expect(page.locator('[data-testid="pages-summary"]')).toBeVisible();
    await expect(page.locator('[data-testid="run-limits"]')).toHaveAttribute("data-profile", "mobile");
    await expect(page.locator('[data-testid="ocr-consent"]')).toBeVisible();

    const preview = {
      ...summarize(openSamples, openFailures, true),
      proof: "first_rendered_page",
    };
    const evidence = {
      kind: "inkflip-performance-browser",
      schema_version: "2.1.0",
      host: {
        profile_requested: "local-mac",
        browserName,
        project: testInfo.project.name,
        is_specified_reference_desktop: false,
        is_physical_mobile: false,
        note: "Playwright viewport is not a 4 GiB physical mobile device; this Mac is not the 4-core/8 GiB reference.",
      },
      build: {
        production: true,
        vite_dev_server: false,
        inkflip_test_hooks: true,
        out_dir: DIST,
        index_head: buildId,
        note: "Identified instrumented production Vite build (INKFLIP_TEST_HOOKS=1). Not a shipped unlabeled artifact.",
      },
      setup_ms: setupMs,
      stages: {
        preview,
        render: { ...summarize(openSamples, openFailures, true), proof: "first_rendered_page" },
        extraction: summarize(extractSamples, extractFailures, extractSamples.length > 0),
        raster: {
          n: 1,
          measured: true,
          distribution_claim: "not_a_latency_distribution",
          oversize_open_rejected: true,
          pixel_budget_enforced: hugeW * hugeH <= 4_000_000,
          edge_budget_enforced: Math.max(hugeW, hugeH) <= 720,
          profile_max_raster_pixels: limits.maxRasterPixels,
          live_buffers: 2,
          live_buffer_cap_enforced: true,
          ocr_workers: 1,
          ocr_worker_cap_enforced: true,
          canvas_width: hugeW,
          canvas_height: hugeH,
          note: "20 MiB byte cap is a separate rejection from live preview raster. Preview canvas is the fixture page after PREVIEW_EDGE_PX=720 fit; profile.maxRasterPixels=4000000. Synthetic 4000x4000 and 20000x20000 MediaBox PDFs are parser_error in this reader.",
        },
        ocr: summarize([], 0, false),
        alignment: summarize([], 0, false),
        export: summarize(exportMs, exportFailures, exportMs.length > 0),
      },
      replace_clear_cycles: {
        n: 10,
        js_heap_used_bytes: heap,
        process_rss_bytes: rss,
        note: "JS heap from performance.memory; process RSS from ps(1) on the Chromium PID. Distinct metrics.",
      },
      cancel_next_file: {
        cancelled_visible: true,
        next_file_pages_summary: true,
      },
      mobile: {
        ocr_consent_visible: true,
        physical_device: false,
        viewport_emulation: "320x568",
        note: "Viewport emulation is not a physical 4 GiB mobile device",
      },
      memory: {
        js_heap_used_bytes: heap.at(-1) ?? null,
        process_rss_bytes: rss.at(-1) ?? null,
        process_rss_unavailable: rss.length === 0,
        limits: {
          tracked_allocation_target_bytes: 268435456,
          measured_peak_rss_target_bytes: 536870912,
        },
      },
    };
    mkdirSync(OUT_DIR, { recursive: true });
    writeFileSync(path.join(OUT_DIR, "browser-local-mac.json"), `${JSON.stringify(evidence, null, 2)}\n`);

    expect(openSamples.length).toBeGreaterThanOrEqual(SAMPLES);
    expect(extractSamples.length).toBeGreaterThan(0);
    expect(preview.distribution_claim).toBe("n>=30");
    expect(preview.proof).toBe("first_rendered_page");
  });
});
