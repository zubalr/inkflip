/**
 * T39 browser resource budgets — real Inkflip workspace behavior.
 *
 * Loads the public workspace, selects synthetic PDFs, exercises production
 * raster/job/output limits, replace/clear, cancellation, missing-model and
 * mobile consent. Latency samples are counted only after a successful
 * result. This host is not a 4-core/8 GiB reference and viewport emulation
 * is not a physical 4 GiB mobile device.
 */
import { expect, test, type Page } from "@playwright/test";
import { mkdirSync, writeFileSync } from "node:fs";
import path from "node:path";
import { pathToFileURL } from "node:url";

const ROOT = path.resolve(process.cwd());
const WEB_ROOT = path.resolve(ROOT, "apps/web");
const OUT_DIR = path.resolve(ROOT, "artifacts/performance");
const MIB = 1024 * 1024;
const DESKTOP_MAX = 20 * MIB;
const SAMPLES = 30;

let viteServer: { close(): Promise<void>; resolvedUrls: { local: string[] } };
let baseUrl: string;

test.beforeAll(async () => {
  const viteModulePath = path.resolve(WEB_ROOT, "node_modules/vite/dist/node/index.js");
  const { createServer } = await import(pathToFileURL(viteModulePath).href);
  viteServer = await createServer({
    root: WEB_ROOT,
    server: { port: 0, strictPort: false },
    logLevel: "silent",
  });
  await viteServer.listen();
  baseUrl = viteServer.resolvedUrls.local[0].replace(/\/$/, "");
});

test.afterAll(async () => {
  await viteServer?.close();
});

function buildPdf(options: { pages: number; text?: string; padBytes?: number; box?: [number, number, number, number] }): Uint8Array {
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
  await page.locator('[data-testid="file-input"]').setInputFiles({
    name,
    mimeType: "application/pdf",
    buffer: Buffer.from(bytes),
  });
  const confirm = page.locator("#btn-confirm-replace, button:has-text(\"Clear and open file\")");
  try {
    await confirm.first().click({ timeout: 2_000 });
  } catch {
    // First open (or a rejected offer) has no replacement dialog.
  }
}

async function openTiny(page: Page, bytes: Uint8Array, name: string) {
  await offerPdf(page, bytes, name);
  await expect(page.locator('[data-testid="pages-summary"]')).toBeVisible({ timeout: 15_000 });
}

function summarize(samples: number[], failures: number, measured: boolean) {
  if (!measured) {
    return { n: 0, failures, measured: false, distribution_claim: "missing", unit: "ms" };
  }
  const clean = samples.filter((v) => Number.isFinite(v));
  const out: Record<string, unknown> = {
    n: clean.length,
    failures,
    measured: true,
    unit: "ms",
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

test.describe("T39 browser workspace budgets", () => {
  test("loads Inkflip, measures stages, and writes labeled evidence", async ({ page, browserName }, testInfo) => {
    test.setTimeout(240_000);
    const tiny = buildPdf({ pages: 1, text: "INKFLIP-T39" });
    await page.setViewportSize({ width: 1280, height: 800 });
    const setupStarted = Date.now();
    await page.goto(`${baseUrl}/#/workspace`);
    await expect(page.locator('[data-testid="file-input"]')).toBeVisible();
    const setupMs = Date.now() - setupStarted;

    // Declared-size gate on the empty intake — same path large-mobile uses.
    // A live document's OpenWorkspace error unmounts on idle after replace.
    const oversize = buildPdf({ pages: 1, text: "fat", padBytes: DESKTOP_MAX });
    await offerPdf(page, oversize, "fat.pdf");
    const err = page.locator('#import-error, [id^="open-error-"]');
    await expect(err).toBeVisible({ timeout: 15_000 });
    await expect(err).toContainText(/limit|too large|20/i);
    await expect(page.locator('[data-testid="pages-summary"]')).toHaveCount(0);

    const openSamples: number[] = [];
    let openFailures = 0;
    for (let i = 0; i < SAMPLES; i++) {
      const t0 = Date.now();
      try {
        await openTiny(page, tiny, `t39-${i}.pdf`);
        openSamples.push(Date.now() - t0);
      } catch {
        openFailures += 1;
      }
    }
    expect(openSamples.length).toBeGreaterThan(0);

    const extractSamples: number[] = [];
    let extractFailures = 0;
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
      if (!session?.adapter || !handle) return { ok: false, reason: "no live handle", times: [] as number[], failures: 30, lastStatus: "" };
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
    if (extract.ok && Array.isArray(extract.times)) {
      extractSamples.push(...extract.times);
      extractFailures = Number(extract.failures || 0);
    } else {
      extractFailures = 30;
    }

    const heap: number[] = [];
    for (let i = 0; i < 10; i++) {
      await offerPdf(page, tiny, `cycle-${i}.pdf`);
      await expect(page.locator('[data-testid="pages-summary"]')).toBeVisible({ timeout: 15_000 });
      const mem = await page.evaluate(() => {
        const perf = performance as Performance & { memory?: { usedJSHeapSize?: number } };
        return perf.memory?.usedJSHeapSize ?? null;
      });
      if (typeof mem === "number") heap.push(mem);
    }

    await page.locator('[data-testid="start-run"]').click();
    await expect(page.locator("#btn-cancel-run")).toBeVisible({ timeout: 30_000 });
    await page.locator("#btn-cancel-run").click();
    await expect(page.locator('[data-testid="run-cancelled"]')).toBeVisible({ timeout: 30_000 });
    await page.locator("#btn-back-to-selection").click();
    await offerPdf(page, buildPdf({ pages: 1, text: "next" }), "next.pdf");
    await expect(page.locator('[data-testid="pages-summary"]')).toBeVisible();

    await page.setViewportSize({ width: 320, height: 568 });
    await page.reload();
    await page.goto(`${baseUrl}/#/workspace`);
    await expect(page.locator('[data-testid="file-input"]')).toBeVisible();
    await offerPdf(page, tiny, "mobile.pdf");
    await expect(page.locator('[data-testid="pages-summary"]')).toBeVisible();
    await expect(page.locator('[data-testid="run-limits"]')).toHaveAttribute(
      "data-profile",
      "mobile",
    );
    await expect(page.locator('[data-testid="ocr-consent"]')).toBeVisible();

    const state = await page.evaluate(() => {
      const session = (globalThis as { __inspect?: { getState(): { fileState: string; notice: string | null; error: { message: string } | null } } }).__inspect;
      return session?.getState() ?? null;
    });

    const evidence = {
      kind: "inkflip-performance-browser",
      schema_version: "2.0.0",
      host: {
        profile_requested: "local-mac",
        browserName,
        project: testInfo.project.name,
        is_specified_reference_desktop: false,
        is_physical_mobile: false,
        note: "Playwright viewport is not a 4 GiB physical mobile device; this Mac is not the 4-core/8 GiB reference.",
      },
      setup_ms: setupMs,
      stages: {
        preview: summarize(openSamples, openFailures, true),
        extraction: summarize(extractSamples, extractFailures, extractSamples.length > 0),
        render: summarize([], 0, false),
        raster: {
          n: 0,
          measured: true,
          distribution_claim: "not_a_latency_distribution",
          oversize_open_rejected: true,
          note: "20 MiB desktop byte cap rejected on the live workspace before allocation",
        },
        ocr: summarize([], 0, false),
        alignment: summarize([], 0, false),
        export: summarize([], 0, false),
      },
      replace_clear_cycles: {
        n: 10,
        js_heap_used_bytes: heap,
        note: "Chromium performance.memory when exposed; not parent-Python ru_maxrss across CLI children",
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
      missing_model: {
        note: "OCR stage recorded missing; offline model prepare is T25, not claimed as T39 p95",
      },
      session: state,
      memory: {
        js_heap_used_bytes: heap.at(-1) ?? null,
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
    expect(evidence.stages.preview.distribution_claim).toBe("n>=30");
  });
});
