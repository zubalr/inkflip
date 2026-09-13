/**
 * G2 — "Complete public investigation surface" (T51)
 *
 * planning/execution/gates.json → G2:
 *   "All six real examples, advanced occurrence/ambiguity UI, supported
 *    large/mobile profiles, import/export/privacy and explicit offline
 *    model behavior work without native."
 *
 * Scenario (executed verbatim by scripts/gate.py, adapted to):
 *   pnpm exec playwright test tests/gates/g2.spec.ts
 *   → bun x --no-install playwright test tests/gates/g2.spec.ts
 *
 * What "the built artifact" means here: `test.beforeAll` runs the pinned
 * Vite production build — the same pipeline `bun run build`
 * (config/acceptance-commands.json → build:web → `vite build` in
 * apps/web) executes — into a task-private dist directory, with two
 * rollup inputs the spec controls:
 *   - index.html                    — the shipped public application
 *     (Home + ExamplesGallery + Workspace + OpenWorkspace + ViewerStage +
 *     CoveragePanel + ExportPanel), and
 *   - src/offline/preview.html      — the T25 mount binding the real
 *     `InspectionSession` + `OpenWorkspace` composition and the real
 *     `src/offline/` lifecycle module. The production app deliberately
 *     ships no ambient service-worker registration; the explicit offline
 *     surface lives on this mount, so the offline leg exercises it here —
 *     the identical contract tests/privacy/cache.spec.ts covers.
 * INKFLIP_TEST_HOOKS=1 is set for this build (the same opt-in G1 uses):
 * it exposes only the read-only `window.__inspect` session handle for
 * assertions/polling. Shipped builds omit it. `__t25` on the offline
 * mount is unconditional mount code, not a build-time hook.
 *
 * The dist tree is served over loopback by a plain static server carrying
 * the planned deployment headers verbatim (CSP included) plus an
 * independent server-side access log — the same harness contract as
 * tests/privacy/local.spec.ts and cache.spec.ts.
 *
 * Composition, honestly stated: every leg drives shipped surfaces — the
 * real index.html shell, the real workspace session
 * (apps/web/src/features/inspect/session.ts) wiring OpenController →
 * ImportController → RunCoordinator → real pdf.js/Tesseract readers →
 * sealed report → viewer → export, and the real offline lifecycle
 * (src/offline + public/sw.js). No collaborator is mocked, no response
 * is stubbed, no fetch is rerouted: file inputs receive real bytes,
 * IndexedDB/CacheStorage are real, and the offline leg's ground truth is
 * the server's own access log.
 *
 * Legs (one test each):
 *   1. Gallery: all six real example cards on Home; every card's
 *      manifest.json + sealed report.json + source PDF fetched
 *      same-origin from the built dist and digest-verified against the
 *      committed index; one card opened through the real UI (detail →
 *      "Open this report in the workspace" → real import gate → viewer);
 *      a second example deep-linked via `#/workspace?example=<id>`.
 *   2. Own-file journey on the built app: open a real fixture PDF
 *      (F01 mapping-amount) through the workspace file input, draw a
 *      canonical region around the real extracted $1,000 token, run the
 *      full pipeline (native_text + render + real Tesseract OCR +
 *      alignment) to a sealed report, then drive the normal viewer
 *      controls (finding select → aria-current + highlight, zoom).
 *   3. Repeated + ambiguous occurrence UI on the bundled example
 *      (?example=true): the ambiguous finding lists all three candidates
 *      with identical-text labelling and none pre-picked; a candidate
 *      pick sticks (aria-pressed + selected highlight, never
 *      first-match); the page-level finding keeps its page-level notice;
 *      finding cycling via the viewer's own shortcuts.
 *   4. Import/export/privacy: import the sealed contract example
 *      (planning/contracts/examples/valid/native-evidence.inkflip.json)
 *      through the real report input; the T16 export panel renders its
 *      privacy preview with every opt-in off; deselection excludes the
 *      finding and discloses it; portable JSON + readable HTML downloads
 *      are real browser downloads; replay state is honest ("not
 *      embedded", attach offered).
 *   5. Explicit offline behavior on the built artifact: plain loads of
 *      the public app register no service worker and create no caches;
 *      the mount's explicit "Prepare for offline use" prepares a
 *      manifest-bound generation and reports readiness; a reload while
 *      the context is offline still serves the shell, and a full own-file
 *      run (model, worker and wasm all worker-served) completes with zero
 *      requests reaching the server.
 *   6. Supported mobile/large profile at 360px: a real multi-page PDF
 *      opens under the low-memory profile (explicit OCR consent,
 *      on-demand preview, capped select-all, windowed page list), the
 *      bundled-example viewer stays usable with stacked compare panes,
 *      and no surface overflows horizontally.
 */
import { createHash } from "node:crypto";
import { existsSync, mkdirSync, readFileSync, rmSync } from "node:fs";
import { createServer, type Server } from "node:http";
import { dirname, join, normalize, resolve, sep } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

import { expect, test, type Page } from "@playwright/test";

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "../..");
const WEB = join(ROOT, "apps/web");
const FIX = join(ROOT, "fixtures");
// Task-private build output — `.private/` is gitignored repo-wide, the
// same convention tests/privacy uses for its dist tree.
const DIST = join(ROOT, "tests", "gates", ".private", "g2-dist");
const OFFLINE_MOUNT = "/src/offline/preview.html";
const CACHE_PREFIX = "inkflip-offline-";

const F01 = join(FIX, "public", "mapping-amount.pdf");
const F01_BYTES = readFileSync(F01);
const F01_SHA256 = createHash("sha256").update(F01_BYTES).digest("hex");
const SEALED_REPORT = join(
  ROOT,
  "planning",
  "contracts",
  "examples",
  "valid",
  "native-evidence.inkflip.json",
);
const EXAMPLE_IDS = [
  "amount",
  "covered",
  "scan",
  "geometry",
  "reading-order",
  "duplicates",
] as const;

// ---------------------------------------------------------------------------
// Static server — identical contract to tests/privacy: the planned
// deployment headers verbatim plus a server-side access log that is the
// independent ground truth for "zero requests reached the network".
// ---------------------------------------------------------------------------
const MIME: Record<string, string> = {
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".mjs": "text/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".json": "application/json",
  ".pdf": "application/pdf",
  ".wasm": "application/wasm",
  ".bcmap": "application/octet-stream",
  ".traineddata": "application/octet-stream",
  ".pfb": "application/octet-stream",
  ".ttf": "font/ttf",
  ".icc": "application/vnd.iccprofile",
  ".png": "image/png",
  ".txt": "text/plain; charset=utf-8",
  ".md": "text/plain; charset=utf-8",
};

const SECURITY_HEADERS: Record<string, string> = {
  "Content-Security-Policy":
    "default-src 'none'; script-src 'self' 'wasm-unsafe-eval'; " +
    "worker-src 'self'; connect-src 'self'; img-src 'self' blob: data:; " +
    "font-src 'self' blob:; style-src 'self'; style-src-attr 'unsafe-inline'; " +
    "object-src 'none'; frame-src 'none'; base-uri 'none'; form-action 'none'; " +
    "frame-ancestors 'none'; manifest-src 'self'",
  "Referrer-Policy": "no-referrer",
  "X-Content-Type-Options": "nosniff",
  "Permissions-Policy": "camera=(), microphone=(), geolocation=(), payment=(), usb=()",
  "Cross-Origin-Resource-Policy": "same-origin",
};

function cacheControl(pathname: string): string {
  if (
    pathname === "/" ||
    pathname === "/index.html" ||
    pathname === "/sw.js" ||
    pathname.endsWith(".html")
  ) {
    // Navigations and the worker script always revalidate — a stale
    // worker is a stale manifest-generation boundary.
    return "no-cache";
  }
  if (pathname.startsWith("/assets/") || pathname.startsWith("/models/")) {
    // Fingerprinted staged assets are immutable — the production posture
    // that also makes them reusable fully offline.
    return "public, max-age=31536000, immutable";
  }
  return "no-cache";
}

interface AccessEntry {
  method: string;
  path: string;
  query: string | null;
  status: number;
}

let server: Server;
let baseURL = "";
const accessLog: AccessEntry[] = [];

function startStaticServer(): Promise<void> {
  const distRoot = resolve(DIST) + sep;
  server = createServer((req, res) => {
    const url = new URL(req.url ?? "/", "http://static.invalid");
    const pathname = decodeURIComponent(url.pathname);
    const entry: AccessEntry = {
      method: req.method ?? "GET",
      path: pathname === "/" ? "/index.html" : pathname,
      query: url.search ? url.search.slice(1) : null,
      status: 200,
    };
    accessLog.push(entry);
    const headers: Record<string, string> = {
      ...SECURITY_HEADERS,
      "Cache-Control": cacheControl(pathname),
    };
    if (pathname === "/favicon.ico") {
      entry.status = 204;
      res.writeHead(204, headers).end();
      return;
    }
    const file = normalize(join(DIST, pathname === "/" ? "/index.html" : pathname));
    if (!file.startsWith(distRoot) || !existsSync(file) || file.endsWith(sep)) {
      entry.status = 404;
      res.writeHead(404, headers).end("not found");
      return;
    }
    const dot = file.lastIndexOf(".");
    const mime = (dot >= 0 && MIME[file.slice(dot)]) || "application/octet-stream";
    res.writeHead(200, { ...headers, "Content-Type": mime }).end(readFileSync(file));
  });
  return new Promise((resolvePromise) => {
    server.listen(0, "127.0.0.1", () => {
      const address = server.address();
      const port = typeof address === "object" && address !== null ? address.port : 0;
      baseURL = `http://127.0.0.1:${port}`;
      resolvePromise();
    });
  });
}

// ---------------------------------------------------------------------------
// Build the real artifacts once: the shipped index plus the T25 offline
// mount, with public/ (sw.js, staged readers, model, examples) verbatim.
// ---------------------------------------------------------------------------
test.beforeAll(async () => {
  rmSync(DIST, { recursive: true, force: true });
  mkdirSync(DIST, { recursive: true });
  const viteEntry = pathToFileURL(
    join(WEB, "node_modules", "vite", "dist", "node", "index.js"),
  ).href;
  const vite = (await import(viteEntry)) as {
    build: (opts: Record<string, unknown>) => Promise<unknown>;
  };
  // Read-only `__inspect` session handle — enabled only via this
  // build-time opt-in (the same one G1's gate build uses; shipped
  // production builds omit it).
  process.env.INKFLIP_TEST_HOOKS = "1";
  // Vite derives import.meta.env.DEV from process.env.NODE_ENV at resolve
  // time; a dev-server spec earlier in this worker process leaves it set
  // to "development". Pin production so the gate exercises the real
  // production artifact regardless of worker-process pollution.
  const savedNodeEnv = process.env.NODE_ENV;
  process.env.NODE_ENV = "production";
  try {
    await vite.build({
      root: WEB,
      configFile: join(WEB, "vite.config.ts"),
      logLevel: "warn",
      build: {
        outDir: DIST,
        emptyOutDir: true,
        rollupOptions: {
          input: {
            index: join(WEB, "index.html"),
            offline: join(WEB, "src", "offline", "preview.html"),
          },
        },
      },
    });
  } finally {
    if (savedNodeEnv === undefined) delete process.env.NODE_ENV;
    else process.env.NODE_ENV = savedNodeEnv;
  }
  await startStaticServer();
});

test.afterAll(async () => {
  await new Promise((r) => server?.close(r));
});

test.setTimeout(300_000);
// Six legs, one context each; serial keeps the shared access log
// boundaries unambiguous.
test.describe.configure({ mode: "serial" });

// ---------------------------------------------------------------------------
// Shared helpers
// ---------------------------------------------------------------------------
interface NetCapture {
  failures: { url: string; error: string | null }[];
  consoleErrors: string[];
  pageErrors: string[];
}

function captureNet(page: Page): NetCapture {
  const cap: NetCapture = { failures: [], consoleErrors: [], pageErrors: [] };
  page.on("requestfailed", (req) => {
    cap.failures.push({ url: req.url(), error: req.failure()?.errorText ?? null });
  });
  page.on("console", (msg) => {
    if (msg.type() === "error") cap.consoleErrors.push(msg.text().slice(0, 500));
  });
  page.on("pageerror", (error) => {
    cap.pageErrors.push(String(error).slice(0, 500));
  });
  return cap;
}

interface SessionSnapshot {
  fileState: string;
  doc: { label: string; sha256: string; pageCount: number } | null;
  report: {
    report_id: string;
    document: { sha256: string; display_name: string | null };
    readers: { id: string }[];
    plan: {
      selected_pages: number[];
      regions: { id: string; page_index: number }[];
      checks: { id: string; capability: string; region_id: string | null }[];
    };
    checks: {
      id: string;
      status: string;
      reason: string | null;
      produced_occurrence_count: number;
    }[];
    occurrences: {
      id: string;
      reader_id: string;
      raw_text: string;
      geometry: { polygon: [number, number][] | null };
    }[];
    findings: { id: string; title: string; occurrence_ids: string[] }[];
    execution: { status: string; errors: string[] };
  } | null;
  reportSource: "run" | "import" | null;
  importedReplay: { source: string; ready: boolean; readersMissing: string[] } | null;
  error: { message: string; detail: string | null } | null;
}

const inspect = (page: Page): Promise<SessionSnapshot> =>
  page.evaluate(
    () =>
      (window as never as { __inspect: { getState(): unknown } }).__inspect.getState(),
  ) as Promise<SessionSnapshot>;

/** Land on the workspace's empty state through the real app shell. */
async function gotoWorkspace(page: Page): Promise<void> {
  await page.goto(baseURL);
  await expect(page.locator("h1")).toContainText("Your PDF can look right");
  await page.locator("#btn-open-report").click();
  await expect(page).toHaveURL(/#\/workspace/);
  await page.waitForFunction(
    () => (window as never as Record<string, unknown>).__inspect !== undefined,
  );
}

/** Offer a local PDF through the app's real file input; confirm replace when asked. */
async function offerPdf(page: Page, name: string, bytes: Uint8Array): Promise<void> {
  const snap = await inspect(page);
  const occupied = snap.doc !== null || snap.report !== null;
  await page
    .locator("#input-open-pdf")
    .setInputFiles({ name, mimeType: "application/pdf", buffer: Buffer.from(bytes) });
  if (occupied) {
    const dlg = page.locator("[role=dialog]");
    await expect(dlg).toBeVisible();
    await expect(dlg).toContainText("Open a different PDF?");
    await dlg.getByRole("button", { name: "Clear and open file" }).click();
  }
  await expect(page.locator("[data-testid=doc-label]")).toHaveText(name, {
    timeout: 30_000,
  });
}

/** Start the run through the real selection UI and wait for the sealed report. */
async function runInspection(page: Page, timeoutMs = 240_000): Promise<SessionSnapshot> {
  await page.locator("[data-testid=start-run]").click();
  const t0 = Date.now();
  for (;;) {
    const snap = await inspect(page);
    if (snap.report !== null && snap.reportSource === "run") return snap;
    if (["complete", "partial", "failed", "cancelled"].includes(snap.fileState) && snap.error) {
      throw new Error(
        `run settled without a report: ${snap.error.message} — ${snap.error.detail ?? ""}`,
      );
    }
    if (Date.now() - t0 > timeoutMs) {
      throw new Error(`run did not settle in ${timeoutMs}ms — fileState=${snap.fileState}`);
    }
    await new Promise((r) => setTimeout(r, 500));
  }
}

// ---------------------------------------------------------------------------
// Minimal multi-page PDF — real xref tables; pdf.js parses it genuinely
// (same builder family tests/browser/large-mobile.spec.ts uses).
// ---------------------------------------------------------------------------
function buildPdf(options: { pages: number; text?: string }): Uint8Array {
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
      `<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] ` +
        `/Resources << /Font << /F1 ${fontObj} 0 R >> >> /Contents ${contentObj} 0 R >>`,
    );
  }
  const xrefPos = len;
  const count = firstPage + nPages;
  let xref = `xref\n0 ${count}\n0000000000 65535 f \n`;
  for (let i = 1; i < count; i++) {
    const off = offsets[i];
    xref +=
      off !== undefined ? `${String(off).padStart(10, "0")} 00000 n \n` : "0000000000 65535 f \n";
  }
  push(xref);
  push(`trailer\n<< /Size ${count} /Root 1 0 R >>\nstartxref\n${xrefPos}\n%%EOF\n`);
  const out = new Uint8Array(len);
  let o = 0;
  for (const c of chunks) {
    out.set(c, o);
    o += c.length;
  }
  return out;
}

// ---------------------------------------------------------------------------
// Offline mount surface — the real `__t25` API the mount exposes (subset
// used here; identical to tests/privacy/cache.spec.ts).
// ---------------------------------------------------------------------------
interface T25 {
  status(): Promise<{
    readiness: string;
    generation: string | null;
    entries: number;
    missing: string[];
    controlled: boolean;
    limitations: string[];
  }>;
  snapshot(): {
    fileState: string;
    run: null | {
      status: string | null;
      checks: {
        id: string;
        capability: string;
        status: string | null;
        producedOccurrences: number;
      }[];
    };
    occurrences: unknown[];
  };
}

declare const __t25: T25;

async function waitMounted(page: Page): Promise<void> {
  await page.waitForFunction(
    () => (globalThis as { __t25?: unknown }).__t25 !== undefined,
    undefined,
    { timeout: 30_000 },
  );
  await expect(page.locator("[data-testid=file-drop]")).toBeVisible();
  await expect(page.locator("[data-testid=offline-panel]")).toBeVisible();
}

async function offerOnMount(page: Page): Promise<void> {
  await page.locator("[data-testid=file-input]").setInputFiles({
    name: "mapping-amount.pdf",
    mimeType: "application/pdf",
    buffer: Buffer.from(F01_BYTES),
  });
  await expect(page.locator("[data-testid=doc-label]")).toHaveText("mapping-amount.pdf", {
    timeout: 30_000,
  });
}

// ===========================================================================
// LEG 1 — all six real examples on the built artifact.
// ===========================================================================
test("G2 leg 1: six real examples — gallery cards, verified dist artifacts, real opens", async ({
  browser,
}) => {
  const ctx = await browser.newContext();
  try {
    const page = await ctx.newPage();
    const cap = captureNet(page);
    await page.goto(baseURL);
    await expect(page.locator("h1")).toContainText("Your PDF can look right");

    // The gallery is the shipped surface: all six cards render from the
    // real /examples/index.json the built dist serves.
    const gallery = page.getByTestId("examples-gallery");
    await expect(gallery).toBeVisible({ timeout: 15_000 });
    for (const id of EXAMPLE_IDS) {
      await expect(
        page.getByTestId(`example-card-${id}`),
        `gallery card ${id}`,
      ).toBeVisible();
    }
    await expect(gallery.getByRole("button")).toHaveCount(6);

    // Every card's manifest + sealed report + source bytes must be
    // fetchable from the built dist — fetched same-origin inside the real
    // app page, digests checked against the committed index values.
    const checks = await page.evaluate(async () => {
      const sha256 = async (buf: ArrayBuffer): Promise<string> => {
        const digest = await crypto.subtle.digest("SHA-256", buf);
        return [...new Uint8Array(digest)]
          .map((b) => b.toString(16).padStart(2, "0"))
          .join("");
      };
      const indexRes = await fetch("examples/index.json", { credentials: "same-origin" });
      const index = (await indexRes.json()) as {
        cards: {
          example_id: string;
          manifest_url: string;
          report_url: string;
          finding_count: number;
          source: { sha256: string; download_url: string; filename: string };
        }[];
      };
      const out: Record<string, unknown>[] = [];
      for (const card of index.cards) {
        const [manifestRes, reportRes, sourceRes] = await Promise.all([
          fetch(card.manifest_url, { credentials: "same-origin" }),
          fetch(card.report_url, { credentials: "same-origin" }),
          fetch(card.source.download_url, { credentials: "same-origin" }),
        ]);
        const manifest = manifestRes.ok
          ? ((await manifestRes.json()) as { example_id?: string })
          : null;
        const report = reportRes.ok
          ? ((await reportRes.json()) as {
              document?: { sha256?: string };
              findings?: unknown[];
            })
          : null;
        out.push({
          id: card.example_id,
          manifestStatus: manifestRes.status,
          reportStatus: reportRes.status,
          sourceStatus: sourceRes.status,
          manifestId: manifest?.example_id ?? null,
          reportSha: report?.document?.sha256 ?? null,
          reportFindings: Array.isArray(report?.findings) ? report.findings.length : -1,
          cardSha: card.source.sha256,
          cardFindings: card.finding_count,
          pdfSha: sourceRes.ok ? await sha256(await sourceRes.arrayBuffer()) : null,
        });
      }
      return out;
    });
    expect(checks).toHaveLength(6);
    for (const c of checks as {
      id: string;
      manifestStatus: number;
      reportStatus: number;
      sourceStatus: number;
      manifestId: string | null;
      reportSha: string | null;
      reportFindings: number;
      cardSha: string;
      cardFindings: number;
      pdfSha: string | null;
    }[]) {
      expect(c.manifestStatus, `${c.id} manifest status`).toBe(200);
      expect(c.reportStatus, `${c.id} report status`).toBe(200);
      expect(c.sourceStatus, `${c.id} source status`).toBe(200);
      expect(c.manifestId, `${c.id} manifest id`).toBe(c.id);
      // The sealed report's recorded document IS the card's source —
      // digest-verified end to end, never a placeholder.
      expect(c.reportSha, `${c.id} report document sha`).toBe(c.cardSha);
      expect(c.pdfSha, `${c.id} source bytes sha`).toBe(c.cardSha);
      expect(c.reportFindings, `${c.id} finding count`).toBe(c.cardFindings);
    }

    // The UI open path: card → detail (real manifest files/readers) →
    // "Open this report in the workspace" → the real import gate → viewer.
    await page.getByTestId("example-card-duplicates").click();
    const detail = page.getByTestId("example-detail-duplicates");
    await expect(detail).toBeVisible();
    await expect(detail.getByText("duplicates-four.pdf")).toBeVisible();
    await expect(detail.getByText("tesseract.js 7.0.0")).toBeVisible();
    await page.getByTestId("open-example-duplicates").click();
    await expect(page).toHaveURL(/#\/workspace\?example=duplicates/);
    await expect(
      page.getByRole("region", { name: "PDF reading inspector viewer stage" }),
    ).toBeVisible({ timeout: 30_000 });
    await expect(page.locator("[data-testid=doc-stats]")).toContainText(
      "1 pages · 1 findings",
    );
    await expect(page.locator("[id^=finding-item-]").first()).toBeVisible();
    await expect(
      page.getByRole("heading", { name: "Preview what you will export" }),
    ).toBeVisible();

    // The deep-link path on a cold load: #/workspace?example=scan fetches
    // the sealed report through the same import gate (5 findings).
    const page2 = await ctx.newPage();
    await page2.goto(`${baseURL}/#/workspace?example=scan`);
    await expect(
      page2.getByRole("region", { name: "PDF reading inspector viewer stage" }),
    ).toBeVisible({ timeout: 30_000 });
    await expect(page2.locator("[id^=finding-item-]")).toHaveCount(5);
    await expect(page2.locator("[data-testid=doc-stats]")).toContainText(
      "1 pages · 5 findings",
    );

    expect(cap.pageErrors, "gallery leg produced page errors").toHaveLength(0);
    expect(cap.failures, "gallery leg produced failed requests").toHaveLength(0);
  } finally {
    await ctx.close();
  }
});

// ===========================================================================
// LEG 2 — own-file journey on the built app: open → region → real run →
// sealed report → normal controls.
// ===========================================================================
test("G2 leg 2: own-file open, region selection, full run, viewer controls", async ({
  browser,
}) => {
  const ctx = await browser.newContext({ acceptDownloads: true });
  try {
    const page = await ctx.newPage();
    const cap = captureNet(page);
    await gotoWorkspace(page);

    // F01 mapping-amount: the text layer reads $1,000 while the raster
    // paints $100 — offered through the real workspace file input.
    await offerPdf(page, "mapping-amount.pdf", F01_BYTES);
    await expect(page.locator("[data-testid=doc-meta]")).toContainText("1 page");
    expect((await inspect(page)).doc?.sha256).toBe(F01_SHA256);
    // Page selection surface: the only page toggle is engaged by default.
    await expect(page.locator("[data-testid=page-toggle-1]")).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    await expect(page.locator("[data-testid=pages-summary]")).toContainText(
      "1 of 1 pages",
    );

    // Region selection in canonical space — bounds derived from the real
    // pdf.js extraction of the $1,000 token (the same adapter the run
    // uses), so the region genuinely contains the finding.
    const amountOcc = await page.evaluate(async () => {
      const s = (
        window as never as {
          __inspect: {
            adapter: {
              plan(h: unknown, sel: unknown): { id: string }[];
              extract(
                ...a: unknown[]
              ): Promise<{ result: { status: string } }>;
            };
            openController: { currentHandle: unknown };
          };
        }
      ).__inspect;
      const handle = s.openController.currentHandle;
      const checks = s.adapter.plan(handle, {
        pages: [0],
        capabilities: ["native_text"],
      });
      const emitted: {
        raw_text: string;
        geometry: { polygon: [number, number][] | null };
      }[] = [];
      await s.adapter.extract(handle, checks[0], (chunk: never[]) =>
        emitted.push(...chunk),
      );
      return (
        emitted.find(
          (o) => o.raw_text === "$1,000" || o.raw_text.includes("$1,000"),
        ) ?? null
      );
    });
    expect(amountOcc, "the real text layer must contain the mapped amount").toBeTruthy();
    const xs = amountOcc!.geometry.polygon!.map((p) => p[0]);
    const ys = amountOcc!.geometry.polygon!.map((p) => p[1]);
    const region = {
      x0: Math.max(0, Math.floor(Math.min(...xs)) - 10),
      y0: Math.max(0, Math.floor(Math.min(...ys)) - 10),
      x1: Math.ceil(Math.max(...xs)) + 10,
      y1: Math.ceil(Math.max(...ys)) + 10,
    };
    await page.locator("[data-testid=region-x0]").fill(String(region.x0));
    await page.locator("[data-testid=region-y0]").fill(String(region.y0));
    await page.locator("[data-testid=region-x1]").fill(String(region.x1));
    await page.locator("[data-testid=region-y1]").fill(String(region.y1));
    await page.locator("[data-testid=region-apply]").click();
    await expect(page.locator("[data-testid=region-committed]")).toContainText(
      `Region on page 1: ${region.x0}, ${region.y0}, ${region.x1}, ${region.y1} pt`,
    );

    // The real run: coordinator-driven native_text + render + real
    // Tesseract OCR + alignment; the region binds to the OCR check.
    const run = await runInspection(page);
    expect(run.report!.document.sha256).toBe(F01_SHA256);
    const planCaps = run.report!.plan.checks.map((c) => c.capability).sort();
    expect(planCaps).toEqual(["alignment", "native_text", "ocr", "render"].sort());
    const ocrPlan = run.report!.plan.checks.find((c) => c.capability === "ocr")!;
    expect(ocrPlan.region_id).not.toBeNull();
    expect(run.report!.plan.regions.map((r) => r.id)).toContain(ocrPlan.region_id);
    for (const c of run.report!.checks) {
      expect(
        ["completed", "unsupported", "skipped"],
        `check ${c.id} → ${c.status} (${c.reason})`,
      ).toContain(c.status);
    }
    expect(run.report!.execution.status).toBe("complete");
    // Both reader families landed real readings — the text layer's $1,000
    // and OCR's raster reading; the report never declares one correct.
    const textOccs = run.report!.occurrences.filter((o) => o.reader_id.includes("text"));
    const ocrOccs = run.report!.occurrences.filter((o) =>
      o.reader_id.includes("tesseract"),
    );
    expect(textOccs.length).toBeGreaterThan(0);
    expect(ocrOccs.length).toBeGreaterThan(0);
    expect(textOccs.map((o) => o.raw_text)).toContain("$1,000");
    expect(run.report!.findings.length).toBeGreaterThan(0);

    // The sealed report renders in the real viewer; the finding card is
    // the listitem+button activator carrying aria-current/aria-expanded.
    await expect(page.locator("#viewer-stage")).toBeVisible();
    await expect(page.locator("#evidence-slip")).toBeVisible();
    const firstFinding = run.report!.findings[0]!;
    const card = page.locator(`#finding-item-${firstFinding.id}`);
    await expect(card).toBeVisible();
    await card.click();
    await expect(card).toHaveAttribute("aria-current", "true");
    await expect(card).toHaveAttribute("aria-expanded", "true");
    // The named occurrence's highlight follows the selection.
    const cited = firstFinding.occurrence_ids[0];
    if (cited) {
      await expect(page.locator(`#highlight-${cited}`)).toHaveClass(/highlightSelected/);
    }

    // Normal controls: zoom through the toolbar, coverage panel and the
    // export surface are all live on the built app.
    await page.locator("#btn-zoom-in").click();
    await expect(page.locator("#label-zoom")).toHaveText("125%");
    await expect(page.getByText("What was checked").first()).toBeVisible();
    await expect(
      page.getByRole("heading", { name: "Preview what you will export" }),
    ).toBeVisible();
    await expect(page.locator("[data-testid=export-findings]")).toBeVisible();

    expect(cap.pageErrors, "own-file leg produced page errors").toHaveLength(0);
  } finally {
    await ctx.close();
  }
});

// ===========================================================================
// LEG 3 — repeated + ambiguous occurrence UI on the bundled example.
// ===========================================================================
test("G2 leg 3: ambiguous candidates, repeated occurrences, page-level notice", async ({
  browser,
}) => {
  const ctx = await browser.newContext();
  try {
    const page = await ctx.newPage();
    const cap = captureNet(page);
    await page.setViewportSize({ width: 1280, height: 900 });
    // The bundled example document mounts through the public
    // ?example=true workspace entry — no fetch, no run.
    await page.goto(`${baseURL}/#/workspace?example=true`);
    await page.waitForSelector("#viewer-stage");

    // Repeated identical strings stay individually addressable: the
    // example carries two "$1,000.00" occurrences at distinct positions.
    await page.locator("#finding-item-finding-dup2").click();
    await expect(page.locator("#finding-item-finding-dup2")).toHaveAttribute(
      "aria-current",
      "true",
    );
    await expect(page.locator("#highlight-occ-p0-dup2")).toHaveClass(
      /highlightSelected/,
    );
    await expect(page.locator("#highlight-occ-p0-dup1")).not.toHaveClass(
      /highlightSelected/,
    );

    // The ambiguous finding: expanded card, ambiguous class, every named
    // candidate listed and none pre-picked.
    const ambig = page.locator("#finding-item-finding-ambig-amounts");
    await ambig.click();
    await expect(ambig).toHaveAttribute("aria-current", "true");
    await expect(ambig).toHaveAttribute("aria-expanded", "true");
    const detail = page.locator('[data-testid="alignment-detail"]');
    await expect(detail).toHaveAttribute("data-alignment-class", "ambiguous");
    for (const id of ["occ-p0-dup1", "occ-p0-dup2", "occ-p0-pypdf1"]) {
      await expect(page.locator(`[data-testid="occ-candidate-${id}"]`)).toBeVisible();
    }
    await expect(
      page.locator('[data-testid="occ-identical-occ-p0-dup1"]'),
    ).toContainText("identical text");
    await expect(
      page.locator('[data-candidate-id][aria-pressed="true"]'),
    ).toHaveCount(0);

    // Picking a candidate sticks — by identity, never by string match.
    const dup2 = page.locator('[data-testid="occ-candidate-occ-p0-dup2"]');
    await dup2.click();
    await expect(dup2).toHaveAttribute("aria-pressed", "true");
    await expect(page.locator("#highlight-occ-p0-dup2")).toHaveClass(
      /highlightSelected/,
    );
    await expect(page.locator("#highlight-occ-p0-dup1")).not.toHaveClass(
      /highlightSelected/,
    );

    // The page-level finding keeps its honest page-level notice and draws
    // no false coordinate box.
    await page.locator("#finding-item-finding-page1-unknown").click();
    const paper = page.locator("#document-paper");
    await expect(paper).toHaveAttribute("data-page-index", "1");
    const notice = page.locator("#page-level-geometry-notice");
    await expect(notice).toBeVisible();
    await expect(notice).toContainText("applies to Page 2 as a whole");
    await expect(page.locator("#highlight-occ-p1-pagelevel")).toHaveCount(0);

    // The viewer's own finding navigation cycles by identity: previous
    // from the page-2 finding lands on the preceding card (finding-dup2),
    // next returns to it — no selection is ever resolved by text.
    await page.keyboard.press("p");
    await expect(page.locator("#finding-item-finding-dup2")).toHaveAttribute(
      "aria-current",
      "true",
    );
    await page.keyboard.press("n");
    await expect(
      page.locator("#finding-item-finding-page1-unknown"),
    ).toHaveAttribute("aria-current", "true");

    expect(cap.pageErrors, "ambiguity leg produced page errors").toHaveLength(0);
  } finally {
    await ctx.close();
  }
});

// ===========================================================================
// LEG 4 — import the sealed example, export with privacy defaults.
// ===========================================================================
test("G2 leg 4: sealed report import → privacy preview → selection → JSON/HTML export", async ({
  browser,
}) => {
  const ctx = await browser.newContext({ acceptDownloads: true });
  try {
    const page = await ctx.newPage();
    const cap = captureNet(page);
    await gotoWorkspace(page);

    // The sealed contract example through the real report input — the
    // strict import gate, identical to a user-supplied file.
    await page.locator("#input-import-report").setInputFiles(SEALED_REPORT);
    await page.waitForSelector("#viewer-stage", { timeout: 30_000 });
    const snap = await inspect(page);
    expect(snap.reportSource).toBe("import");
    expect(snap.report!.document.sha256).toBe(
      "04898afc314b708f66e64171bf10073589cca634c3f40f93f1c2de6c8e658a80",
    );
    await expect(page.locator("#finding-item-f_amount")).toBeVisible();

    // Honest replay state: the original is not embedded, attach is
    // offered, nothing pretends readiness.
    const replay = page.locator("[data-testid=replay-status]");
    await expect(replay).toBeVisible();
    await expect(replay).toContainText(/not embedded|Attach the matching file/i);
    await expect(page.locator("#btn-attach-source")).toBeVisible();

    // The export panel's privacy preview: every inclusion opt-in off —
    // no source bytes, no filename, no notes — and the real crop pixels
    // are shown with the not-a-redaction disclosure.
    await expect(
      page.getByRole("heading", { name: "Preview what you will export" }),
    ).toBeVisible();
    for (const label of [
      "Include the original PDF",
      "Include original filename",
      "Include my notes",
    ]) {
      await expect(page.getByLabel(label)).not.toBeChecked();
    }
    await expect(
      page.getByText("Original PDF not included.", { exact: false }).first(),
    ).toBeVisible();
    const cropImg = page.getByTestId("crop-image-a_crop");
    await expect(cropImg).toBeVisible();
    await expect(cropImg).toHaveAttribute("src", /^data:image\/png;base64,/);
    await expect(
      page.getByText(/Cropping is not a redaction guarantee/i),
    ).toBeVisible();

    // Deselection excludes the finding AND discloses it — count-level in
    // the payload, named in the panel.
    const findingBox = page.getByTestId("finding-check-f_amount");
    await expect(findingBox).toBeChecked();
    await findingBox.uncheck();
    await expect(page.getByTestId("deselected-findings")).toContainText("f_amount");

    let download = page.waitForEvent("download");
    await page.getByRole("button", { name: "Download portable JSON" }).click();
    let text = await (await download).createReadStream().then(async (s) => {
      const chunks: Buffer[] = [];
      for await (const c of s) chunks.push(c as Buffer);
      return Buffer.concat(chunks).toString("utf8");
    });
    let exported = JSON.parse(text) as {
      findings: { id: string }[];
      occurrences: { id: string }[];
      annotations: unknown[];
      assets: { purpose: string }[];
      export: { omissions: string[] };
      document: { display_name: string | null; sha256: string };
    };
    expect(exported.findings.map((f) => f.id)).not.toContain("f_amount");
    expect(exported.occurrences.map((o) => o.id)).not.toContain("o_pdfium_amount");
    expect(exported.occurrences.map((o) => o.id)).not.toContain("o_tess_amount");
    expect(exported.export.omissions.join(" ")).toContain(
      "1 finding(s) excluded by selection",
    );

    // Re-selection restores the finding; defaults keep notes/source/name
    // out of the portable JSON.
    await findingBox.check();
    download = page.waitForEvent("download");
    await page.getByRole("button", { name: "Download portable JSON" }).click();
    text = await (await download).createReadStream().then(async (s) => {
      const chunks: Buffer[] = [];
      for await (const c of s) chunks.push(c as Buffer);
      return Buffer.concat(chunks).toString("utf8");
    });
    exported = JSON.parse(text);
    expect(exported.findings.map((f) => f.id)).toContain("f_amount");
    expect(exported.document.sha256).toBe(
      "04898afc314b708f66e64171bf10073589cca634c3f40f93f1c2de6c8e658a80",
    );
    expect(exported.document.display_name).toBeNull();
    expect(exported.annotations).toEqual([]);
    expect(exported.assets.some((a) => a.purpose === "source_pdf")).toBe(false);

    // The readable HTML export is a real, self-contained download.
    download = page.waitForEvent("download");
    await page.getByRole("button", { name: "Download readable HTML" }).click();
    const html = await (await download).createReadStream().then(async (s) => {
      const chunks: Buffer[] = [];
      for await (const c of s) chunks.push(c as Buffer);
      return Buffer.concat(chunks).toString("utf8");
    });
    expect(html).toContain(
      "04898afc314b708f66e64171bf10073589cca634c3f40f93f1c2de6c8e658a80",
    );
    expect(html).not.toContain("<script");
    expect(html).not.toMatch(/https?:\/\//);

    expect(cap.pageErrors, "import/export leg produced page errors").toHaveLength(0);
    expect(cap.failures, "import/export leg produced failed requests").toHaveLength(0);
  } finally {
    await ctx.close();
  }
});

// ===========================================================================
// LEG 5 — explicit offline model behavior on the built artifact.
// ===========================================================================
test("G2 leg 5: offline is explicit — nothing ambient, explicit prepare, offline shell + run", async ({
  browser,
}) => {
  const ctx = await browser.newContext();
  try {
    const page = await ctx.newPage();
    const cap = captureNet(page);

    // Plain loads of the shipped app register NOTHING and cache NOTHING —
    // offline capability is an explicit action, never ambient.
    await page.goto(baseURL);
    await expect(page.locator("h1")).toContainText("Your PDF can look right");
    const surface0 = await page.evaluate(async (prefix) => ({
      registrations: (await navigator.serviceWorker.getRegistrations()).length,
      caches: (await caches.keys()).filter((n) => n.startsWith(prefix))
        .length,
    }), CACHE_PREFIX);
    expect(surface0.registrations, "app load must not register a worker").toBe(0);
    expect(surface0.caches, "app load must not create offline caches").toBe(0);

    // The workspace route is just as inert.
    await page.goto(`${baseURL}/#/workspace`);
    await page.waitForSelector("[data-testid=file-drop]");
    const surface1 = await page.evaluate(async (prefix) => ({
      registrations: (await navigator.serviceWorker.getRegistrations()).length,
      caches: (await caches.keys()).filter((n) => n.startsWith(prefix))
        .length,
    }), CACHE_PREFIX);
    expect(surface1.registrations).toBe(0);
    expect(surface1.caches).toBe(0);

    // The explicit-offline mount (part of this build): still nothing
    // until the user's own action — honest "unregistered" state.
    await page.goto(`${baseURL}${OFFLINE_MOUNT}`);
    await waitMounted(page);
    await expect(page.locator("[data-testid=offline-status]")).toContainText(
      "status: unregistered",
    );
    const surface2 = await page.evaluate(async (prefix) => ({
      registrations: (await navigator.serviceWorker.getRegistrations()).length,
      caches: (await caches.keys()).filter((n) => n.startsWith(prefix))
        .length,
    }), CACHE_PREFIX);
    expect(surface2.registrations).toBe(0);
    expect(surface2.caches).toBe(0);

    // The explicit "Prepare for offline use" action: registers the worker,
    // builds the versioned manifest, and the worker fetches + verifies +
    // stores every entry under a manifest-bound generation.
    await page.locator("[data-testid=prepare-offline]").click();
    await expect(page.locator("[data-testid=prepare-result]")).toContainText(
      "prepared ·",
      { timeout: 240_000 },
    );
    const status = await page.evaluate(() => __t25.status());
    expect(status.readiness).toBe("ready");
    expect(status.controlled).toBe(true);
    expect(status.missing).toHaveLength(0);
    expect(status.entries).toBeGreaterThan(100);
    await expect(page.locator("[data-testid=offline-status]")).toContainText(
      "status: ready",
    );

    // Reload while the context is offline: the app shell itself is served
    // by the worker — navigation, module graph and staged readers all
    // resolve without the network.
    const logStart = accessLog.length;
    const failStart = cap.failures.length;
    await ctx.setOffline(true);
    try {
      const response = await page.goto(`${baseURL}${OFFLINE_MOUNT}`);
      expect(response !== null && response.ok(), "offline shell load failed").toBe(true);
      await waitMounted(page);
      await expect(page.locator("[data-testid=offline-status]")).toContainText(
        "status: ready",
      );

      // A full own-file run with zero network: open the real fixture and
      // run native text + render + OCR (worker-served model/worker/wasm) +
      // alignment through the real session.
      await offerOnMount(page);
      await page.locator("[data-testid=start-run]").click();
      await expect
        .poll(
          async () =>
            (await page.evaluate(() => __t25.snapshot())).run?.status ?? "none",
          { timeout: 180_000, intervals: [500, 1_000, 2_000] },
        )
        .toBe("complete");
      const snap = await page.evaluate(() => __t25.snapshot());
      for (const capability of ["native_text", "render", "ocr", "alignment"]) {
        const found = snap.run!.checks.filter((c) => c.capability === capability);
        expect(found.length, `no ${capability} check ran offline`).toBeGreaterThan(0);
        for (const check of found) {
          expect(check.status, `offline ${capability} check ${check.id}`).toBe(
            "completed",
          );
        }
      }
      expect(snap.occurrences.length).toBeGreaterThan(0);
      const ocrCheck = snap.run!.checks.find((c) => c.capability === "ocr")!;
      expect(ocrCheck.producedOccurrences).toBeGreaterThan(0);
    } finally {
      await ctx.setOffline(false);
    }

    // Ground truth: the server observed literally zero requests during
    // the offline leg, and the page saw zero failed requests.
    expect(
      accessLog.slice(logStart),
      "offline leg: requests reached the server",
    ).toHaveLength(0);
    expect(
      cap.failures.slice(failStart),
      "offline leg: failed requests",
    ).toHaveLength(0);
    expect(cap.pageErrors, "offline leg produced page errors").toHaveLength(0);
  } finally {
    await ctx.close();
  }
});

// ===========================================================================
// LEG 6 — supported mobile/large profiles at 360px on the built app.
// ===========================================================================
test("G2 leg 6: 360px mobile profile — limits, consent, windowed list, no overflow", async ({
  browser,
}) => {
  const ctx = await browser.newContext({
    viewport: { width: 360, height: 740 },
  });
  try {
    const page = await ctx.newPage();
    const cap = captureNet(page);
    await page.goto(`${baseURL}/#/workspace`);
    await page.waitForSelector("[data-testid=file-drop]");

    // A real multi-page PDF (54 pages — past the 48-row window) opens
    // under the low-memory profile.
    await page.locator("#input-open-pdf").setInputFiles({
      name: "many-pages.pdf",
      mimeType: "application/pdf",
      buffer: Buffer.from(buildPdf({ pages: 54, text: "bulk" })),
    });
    await expect(page.locator("[data-testid=doc-label]")).toHaveText(
      "many-pages.pdf",
      { timeout: 30_000 },
    );
    await expect(page.locator("[data-testid=pages-summary]")).toContainText(
      "of 54 pages",
    );

    // The mobile profile is honestly surfaced: tighter limits, explicit
    // OCR consent (off by default), preview on demand.
    const limits = page.locator("[data-testid=run-limits]");
    await expect(limits).toHaveAttribute("data-profile", "mobile");
    await expect(limits).toContainText("low-memory mode");
    await expect(page.locator("[data-testid=ocr-consent-row]")).toBeVisible();
    await expect(page.locator("[data-testid=ocr-consent]")).not.toBeChecked();
    await expect(page.locator("[data-testid=render-preview]")).toBeVisible();
    await page.locator("[data-testid=render-preview]").click();
    await expect
      .poll(() =>
        page
          .locator("[data-testid=region-canvas]")
          .evaluate((node: HTMLCanvasElement) => node.width),
      )
      .toBeGreaterThan(0);

    // The page list windows the metadata plan — never all 54 rows — and
    // every page toggle meets the 44px touch floor.
    const rows = page.locator('[data-testid="page-list"] li');
    expect(await rows.count()).toBeLessThanOrEqual(48);
    const box = await page.locator('[data-testid="page-toggle-1"]').boundingBox();
    expect(box).not.toBeNull();
    expect(box!.height).toBeGreaterThanOrEqual(44);
    // Select-all is honestly capped at the mobile limit.
    await page.locator('[data-testid="select-all"]').click();
    await expect(page.locator('[data-testid="pages-summary"]')).toContainText(
      "5 of 54 pages selected",
    );
    await expect(page.locator("#pages-limit-notice")).toBeVisible();
    // A far page stays reachable through the jump control.
    await page.locator('[data-testid="page-jump"]').fill("50");
    await page.locator('[data-testid="page-jump"]').press("Enter");
    await expect(page.locator('[data-testid="page-toggle-50"]')).toBeVisible();
    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
    );
    expect(overflow).toBeLessThanOrEqual(0);
    await expect(page.locator('[data-testid="start-run"]')).toBeVisible();

    // The bundled-example viewer at 360px on a cold load — a same-tab
    // hash change cannot remount the example, so this is a fresh page on
    // the same mobile-profiled context: finding cards are usable and
    // compare mode stacks panes instead of squeezing.
    const viewerPage = await ctx.newPage();
    await viewerPage.goto(`${baseURL}/#/workspace?example=true`);
    await viewerPage.waitForSelector("#viewer-stage");
    const finding = viewerPage.locator("[id^=finding-item-]").first();
    await expect(finding).toBeVisible();
    await finding.click();
    await expect(finding).toHaveAttribute("aria-current", "true");
    await viewerPage.locator("#tab-mode-compare").click();
    await expect(viewerPage.locator("#compare-panes-container")).toBeVisible();
    const leftBox = await viewerPage.locator("#compare-pane-left").boundingBox();
    const rightBox = await viewerPage.locator("#compare-pane-right").boundingBox();
    expect(leftBox).not.toBeNull();
    expect(rightBox).not.toBeNull();
    if (leftBox && rightBox) {
      // Stacked, not squeezed side-by-side.
      expect(rightBox.y).toBeGreaterThanOrEqual(leftBox.y + leftBox.height - 5);
      expect(leftBox.width).toBeGreaterThanOrEqual(280);
      expect(rightBox.width).toBeGreaterThanOrEqual(280);
    }
    const viewerOverflow = await viewerPage.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
    );
    expect(viewerOverflow).toBeLessThanOrEqual(1);

    expect(cap.pageErrors, "mobile leg produced page errors").toHaveLength(0);
  } finally {
    await ctx.close();
  }
});
