/**
 * T25 — Explicit offline static/model cache lifecycle (TEST-25): real
 * Chromium coverage over the REAL BUILT site and the REAL service worker
 * (`apps/web/public/sw.js` + `apps/web/src/offline/`), served by a plain
 * static server with the planned deployment `_headers` (CSP included) and
 * an independent server-side access log — the same harness contract as
 * local.spec.ts. Nothing at the contract surface is mocked: the page
 * under test is the T25 mount (`apps/web/src/offline/preview.html`)
 * binding the real `InspectionSession` + `OpenWorkspace` composition and
 * the real `src/offline/` lifecycle module.
 *
 * Acceptance criteria exercised (each named test maps to one criterion):
 *
 * 1. "Cold/offline without model reports unavailable" — a fresh profile
 *    with nothing prepared honestly reports `unregistered`/`not_prepared`
 *    (never "ready"); the explicit prepare action fails closed offline;
 *    the real Tesseract model path ends in the typed `unavailable_offline`
 *    state; an own-file open attempt fails with a real typed rejection,
 *    not a crash and not a fake success.
 * 2. "Prepared offline own-file works without requests" — after the
 *    explicit "Prepare for offline use" action, the page RELOADS while
 *    `context.setOffline(true)` (the app shell itself is served by the
 *    worker), then opens a real PDF and completes the full own-file run
 *    (native text + render + OCR through the worker-served model/worker/
 *    wasm + alignment) with literally zero requests reaching the server
 *    and zero failed requests. CacheStorage is census-checked to hold
 *    only allowlisted manifest paths — never document bytes.
 * 3. "Model update cannot reuse wrong hash" — a manifest declaring the
 *    wrong sha256 for the model is refused at store time
 *    (`integrity_mismatch`; the generation id is manifest-bound so the
 *    refused update can never collide with the good cache), the previous
 *    good generation stays intact; and a corrupted stored entry is
 *    refused at serve time (evicted + reported + fail-closed offline) —
 *    never a silent stale reuse.
 * 4. "Clear terminates workers/revokes URLs/removes requested caches,
 *    with no forensic erasure promise" — the real Clear control tears
 *    down the pdf.js document handle (worker destroyed — proven by the
 *    closed-handle probe), revokes a coordinator-owned object URL and
 *    terminates a coordinator-owned Worker through the real
 *    `CleanupRegistry` channel; document clear deliberately leaves the
 *    offline caches alone (reset ≠ remove); the explicit "Remove offline
 *    assets" action deletes every `inkflip-offline-*` cache while
 *    honestly carrying the OFFLINE_LIMITATIONS wording — present both in
 *    the DOM and the result — and the SW registration itself is
 *    untouched (removal deletes caches, it does not lie about
 *    unregistering).
 *
 * Also asserted: loading a page caches NOTHING silently — no caches and
 * no registration exist before the explicit action (offline is opt-in,
 * never ambient).
 */
import { createHash } from "node:crypto";
import { existsSync, mkdirSync, readFileSync, rmSync } from "node:fs";
import { createServer, type Server } from "node:http";
import { dirname, join, normalize, resolve, sep } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

import { expect, test, type BrowserContext, type Page } from "@playwright/test";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..", "..");
const WEB = join(ROOT, "apps", "web");
// Task-private build output — `.private/` is gitignored repo-wide and
// deliberately disjoint from local.spec.ts's own dist/capture trees so
// the two suites can never corrupt each other's artifacts.
const DIST = join(ROOT, "tests", "privacy", ".private", "t25-dist");
const MOUNT = "/src/offline/preview.html";
const CACHE_PREFIX = "inkflip-offline-";
const INDEX_CACHE = "inkflip-offline-index";
const MODEL_SHA256 = "7d4322bd2a7749724879683fc3912cb542f19906c83bcc1a52132556427170b2";

// ---------------------------------------------------------------------------
// Canary PDF — real xref/PDF-1.4 bytes (same minimal builder family as
// local.spec.ts); filename + visible text + document hash are markers that
// must never appear in a request URL or a cache entry.
// ---------------------------------------------------------------------------
const CANARY_NAME = "inkflip-t25-cache-canary.pdf";
const CANARY_VISIBLE = "INKFLIP-T25-OFFLINE-CANARY-7KQ9";

function buildCanaryPdf(visible = CANARY_VISIBLE): Uint8Array {
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
  const stream =
    `BT /F1 20 Tf 48 700 Td (${visible}) Tj ET\n` +
    `BT /F1 10 Tf 48 640 Td (inkflip local inspection only) Tj ET`;
  push("%PDF-1.4\n");
  obj(1, "<< /Type /Catalog /Pages 2 0 R >>");
  obj(2, "<< /Type /Pages /Kids [5 0 R] /Count 1 >>");
  obj(3, "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>");
  obj(4, `<< /Length ${stream.length} >>\nstream\n${stream}\nendstream`);
  obj(
    5,
    "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] " +
      "/Resources << /Font << /F1 3 0 R >> >> /Contents 4 0 R >>",
  );
  const xrefPos = len;
  push(
    "xref\n0 6\n0000000000 65535 f \n" +
      [1, 2, 3, 4, 5].map((i) => `${String(offsets[i]).padStart(10, "0")} 00000 n \n`).join("") +
      `trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n${xrefPos}\n%%EOF\n`,
  );
  const out = new Uint8Array(len);
  let o = 0;
  for (const c of chunks) {
    out.set(c, o);
    o += c.length;
  }
  return out;
}

const CANARY_BYTES = buildCanaryPdf();
const CANARY_SHA256 = createHash("sha256").update(CANARY_BYTES).digest("hex");

// ---------------------------------------------------------------------------
// Static server — identical contract to local.spec.ts: the planned
// deployment headers verbatim plus a server-side access log that is the
// independent ground truth for "zero requests reached the network".
// ---------------------------------------------------------------------------
const MIME: Record<string, string> = {
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".mjs": "text/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".json": "application/json",
  ".wasm": "application/wasm",
  ".bcmap": "application/octet-stream",
  ".traineddata": "application/octet-stream",
  ".pfb": "application/octet-stream",
  ".ttf": "font/ttf",
  ".icc": "application/vnd.iccprofile",
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
    pathname === "/index.html" ||
    pathname === "/" ||
    pathname === "/release.json" ||
    pathname === "/sw.js"
  ) {
    // index.html and the worker script always revalidate — a stale worker
    // is a stale manifest-generation boundary.
    return "no-cache";
  }
  if (pathname.startsWith("/assets/") || pathname.startsWith("/models/")) {
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

interface Harness {
  base: string;
  accessLog: AccessEntry[];
  server: Server;
}

let harness: Harness;

function startStaticServer(): Promise<Harness> {
  const accessLog: AccessEntry[] = [];
  const distRoot = resolve(DIST) + sep;
  const server = createServer((req, res) => {
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
    if (!file.startsWith(distRoot) || !existsSync(file)) {
      entry.status = 404;
      res.writeHead(404, headers).end("not found");
      return;
    }
    const dot = pathname.lastIndexOf(".");
    const mime = (dot >= 0 && MIME[pathname.slice(dot)]) || "application/octet-stream";
    entry.status = 200;
    res.writeHead(200, { ...headers, "Content-Type": mime }).end(readFileSync(file));
  });
  return new Promise((resolvePromise) => {
    server.listen(0, "127.0.0.1", () => {
      const address = server.address();
      const port = typeof address === "object" && address !== null ? address.port : 0;
      resolvePromise({ base: `http://127.0.0.1:${port}`, accessLog, server });
    });
  });
}

// ---------------------------------------------------------------------------
// Build the real artifacts once: shipped index + the T25 mount, plus
// public/ (sw.js, staged readers, model, examples) copied verbatim.
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
  harness = await startStaticServer();
});

test.afterAll(async () => {
  harness?.server.close();
});

test.setTimeout(300_000);
// The four legs share one prepared context — order is the evidence.
test.describe.configure({ mode: "serial" });

// ---------------------------------------------------------------------------
// Capture + page helpers
// ---------------------------------------------------------------------------
interface NetCapture {
  requests: { url: string; method: string; resourceType: string; nav: boolean }[];
  failures: { url: string; error: string | null }[];
  consoleErrors: string[];
  pageErrors: string[];
}

function captureNet(page: Page): NetCapture {
  const cap: NetCapture = {
    requests: [],
    failures: [],
    consoleErrors: [],
    pageErrors: [],
  };
  page.on("request", (req) => {
    cap.requests.push({
      url: req.url(),
      method: req.method(),
      resourceType: req.resourceType(),
      nav: req.isNavigationRequest(),
    });
  });
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

/** The typed `window.__t25` surface the T25 mount exposes. */
interface T25 {
  modelPath: string;
  register(): Promise<{
    registered: boolean;
    reason: string | null;
    detail: string | null;
  }>;
  prepare(options?: { manifest?: unknown }): Promise<{
    ok: boolean;
    generation: string | null;
    stored: number;
    bytes: number;
    failed: { path: string; error: string }[];
    controlled: boolean;
    error: string | null;
  }>;
  status(): Promise<{
    readiness: string;
    generation: string | null;
    entries: number;
    missing: string[];
    controlled: boolean;
    limitations: string[];
  }>;
  remove(): Promise<{ ok: boolean; removed: string[]; limitations: string[] }>;
  isControlled(): boolean;
  buildManifest(): {
    schema: string;
    release: string;
    entries: { path: string; sha256: string | null; kind: string }[];
  };
  snapshot(): {
    fileState: string;
    generation: number;
    run: null | {
      status: string | null;
      checks: {
        id: string;
        capability: string;
        status: string | null;
        reason: string | null;
        producedOccurrences: number;
      }[];
    };
    occurrences: unknown[];
  };
  events: { type: string; label?: string; generation?: number }[];
  swEvents: { type: string; generation?: string; path?: string; reason?: string }[];
  ocrPrepareProbe(): Promise<
    | {
        ok: true;
        preparation: { state: string; provenance: string | null; sha256: string };
        modelState: string;
      }
    | {
        ok: false;
        error: { name: string; reason: string | null; message: string };
        modelState: string;
      }
  >;
  makeDocumentUrl(bytes: number[]): { url: string };
  makeProbeWorker(): { url: string };
  probeLastHandle(): Promise<{ ok: true } | { ok: false; message: string }>;
  cacheDump(): Promise<{ names: string[]; entries: Record<string, string[]> }>;
  corruptCachedEntry(path: string): Promise<{ cache: string; path: string } | null>;
}

/**
 * Ambient handle to the mount's live API — used only inside
 * `page.evaluate` bodies, where `__t25` resolves against the page's
 * global. In the Node-side spec scope it must never be dereferenced.
 */
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

async function offerCanary(page: Page): Promise<void> {
  await page.locator("[data-testid=file-input]").setInputFiles({
    name: CANARY_NAME,
    mimeType: "application/pdf",
    buffer: Buffer.from(CANARY_BYTES),
  });
  await expect(page.locator("[data-testid=doc-label]")).toHaveText(CANARY_NAME, {
    timeout: 30_000,
  });
}

/**
 * Every request the page emitted inside [from, ∞) must be a same-origin
 * allowlisted GET — a document-derived value in a URL fails here, as does
 * any foreign origin or write method. blob:/data: pseudo-URLs are local
 * by construction and skipped (they are not network requests).
 */
function assertWireClean(
  cap: NetCapture,
  from: number,
  allowedPaths: ReadonlySet<string>,
  label: string,
): void {
  for (const req of cap.requests.slice(from)) {
    const url = new URL(req.url);
    if (url.protocol === "blob:" || url.protocol === "data:") continue;
    expect(url.origin === harness.base, `${label}: foreign request ${req.url}`).toBe(true);
    expect(req.method, `${label}: ${req.method} ${url.pathname}`).toBe("GET");
    expect(url.search, `${label}: query on ${url.pathname}`).toBe("");
    expect(
      allowedPaths.has(url.pathname) || url.pathname === "/sw.js",
      `${label}: request outside allowlist: ${url.pathname}`,
    ).toBe(true);
  }
}

// ---------------------------------------------------------------------------
// TEST 1 — cold/offline without prepared assets: honest "unavailable".
// ---------------------------------------------------------------------------
test("cold offline: nothing caches silently; unprepared profile reports unavailable", async ({
  browser,
}) => {
  const ctx = await browser.newContext();
  try {
    const page = await ctx.newPage();
    const cap = captureNet(page);
    const wireStart = cap.requests.length;
    const logStart = harness.accessLog.length;

    await page.goto(`${harness.base}${MOUNT}`);
    await waitMounted(page);

    // Loading the page caches NOTHING and registers NOTHING — offline
    // capability is an explicit action, never ambient.
    const dump0 = await page.evaluate(() => __t25.cacheDump());
    expect(
      dump0.names.filter((n) => n.startsWith(CACHE_PREFIX)),
      "page load must not create offline caches",
    ).toHaveLength(0);
    const status0 = await page.evaluate(() => __t25.status());
    expect(status0.readiness).toBe("unregistered");
    expect(status0.controlled).toBe(false);

    // Explicit registration alone still prepares nothing.
    const reg = await page.evaluate(() => __t25.register());
    expect(reg.registered).toBe(true);
    const status1 = await page.evaluate(() => __t25.status());
    expect(status1.readiness).toBe("not_prepared");

    // --- now fully offline ---
    await ctx.setOffline(true);
    try {
      // The explicit prepare action fails closed — it cannot fetch, so it
      // reports failure instead of claiming readiness.
      const prep = await page.evaluate(() => __t25.prepare());
      expect(prep.ok).toBe(false);
      expect(prep.error).not.toBeNull();
      const statusOff = await page.evaluate(() => __t25.status());
      expect(statusOff.readiness).not.toBe("ready");

      // The model asset reports its typed state — unavailable_offline,
      // never a fabricated success and never an untyped crash.
      const probe = await page.evaluate(() => __t25.ocrPrepareProbe());
      expect(probe.ok).toBe(false);
      if (!probe.ok) {
        expect(probe.error.reason).toBe("unavailable_offline");
        expect(probe.modelState).toBe("unavailable_offline");
      }

      // An own-file open attempt fails honestly: a typed rejection in the
      // real controller event stream, an error notice in the UI, and no
      // document panel — not a hang, not a silent drop.
      await page.locator("[data-testid=file-input]").setInputFiles({
        name: CANARY_NAME,
        mimeType: "application/pdf",
        buffer: Buffer.from(CANARY_BYTES),
      });
      await expect
        .poll(async () => page.evaluate(() => __t25.events.some((e) => e.type === "rejected")))
        .toBe(true);
      await expect(page.locator("[data-testid=doc-label]")).toHaveCount(0);
      await expect(page.locator('[id^="open-error"]')).toBeVisible();
    } finally {
      await ctx.setOffline(false);
    }

    // The cold leg's wire record: same-origin allowlisted GETs only; the
    // failed requests were the honest asset misses.
    const allowed = new Set<string>(["/favicon.ico"]);
    for (const entry of (await page.evaluate(() => __t25.buildManifest())).entries) {
      allowed.add(entry.path);
    }
    assertWireClean(cap, wireStart, allowed, "cold-offline");
    for (const entry of harness.accessLog.slice(logStart)) {
      expect(entry.method, `server saw ${entry.method} ${entry.path}`).toBe("GET");
      expect(entry.query, `server saw query on ${entry.path}`).toBeNull();
    }
    expect(cap.pageErrors, "cold offline produced page errors").toHaveLength(0);
  } finally {
    await ctx.close();
  }
});

// ---------------------------------------------------------------------------
// Shared prepared context for tests 2–4 (serial: each stage depends on
// the previous one's real state).
// ---------------------------------------------------------------------------
let ctxMain: BrowserContext;
let pageMain: Page;
let capMain: NetCapture;
let manifestPaths: Set<string>;
let generationA: string;

// ---------------------------------------------------------------------------
// TEST 2 — prepared offline: the own-file workflow runs with zero network.
// ---------------------------------------------------------------------------
test("prepared offline: shell reload + own-file run completes with zero requests", async ({
  browser,
}) => {
  ctxMain = await browser.newContext();
  pageMain = await ctxMain.newPage();
  capMain = captureNet(pageMain);

  await pageMain.goto(`${harness.base}${MOUNT}`);
  await waitMounted(pageMain);

  // Nothing is cached until the explicit user action.
  const dump0 = await pageMain.evaluate(() => __t25.cacheDump());
  expect(dump0.names.filter((n) => n.startsWith(CACHE_PREFIX))).toHaveLength(0);

  // The real "Prepare for offline use" control — a full fetch + verify +
  // store pass over the versioned allowlist (~200 pinned assets).
  await pageMain.locator("[data-testid=prepare-offline]").click();
  await expect(pageMain.locator("[data-testid=prepare-result]")).toContainText("prepared ·", {
    timeout: 240_000,
  });

  const status = await pageMain.evaluate(() => __t25.status());
  expect(status.readiness).toBe("ready");
  expect(status.controlled).toBe(true);
  expect(status.missing).toHaveLength(0);
  expect(status.entries).toBeGreaterThan(100);
  generationA = status.generation!;
  expect(generationA).toMatch(/^[0-9a-f]{16}$/);

  manifestPaths = new Set(
    (await pageMain.evaluate(() => __t25.buildManifest())).entries.map((e) => e.path),
  );
  // The manifest must name the mount page itself — the offline reload is
  // the shell-load proof.
  expect(manifestPaths.has(MOUNT)).toBe(true);

  // Cache census: only owned caches, only allowlisted same-origin paths.
  const dump1 = await pageMain.evaluate(() => __t25.cacheDump());
  expect(dump1.names).toContain(INDEX_CACHE);
  expect(dump1.names.some((n) => n.startsWith(`${CACHE_PREFIX}gen-`))).toBe(true);
  for (const name of dump1.names) {
    expect(name.startsWith(CACHE_PREFIX), `unexpected cache present: ${name}`).toBe(true);
  }
  for (const [name, urls] of Object.entries(dump1.entries)) {
    for (const url of urls) {
      const parsed = new URL(url);
      expect(parsed.origin === harness.base, `foreign URL in ${name}: ${url}`).toBe(true);
      expect(
        manifestPaths.has(parsed.pathname) || parsed.pathname.startsWith("/__inkflip_sw__/"),
        `non-manifest path in ${name}: ${parsed.pathname}`,
      ).toBe(true);
      expect(url.includes(CANARY_NAME) || url.includes(CANARY_SHA256)).toBe(false);
    }
  }

  // A same-origin path NOT in the manifest is a plain network request —
  // the worker never invents coverage for unlisted paths (the server
  // returns its honest 404).
  const unlisted = await pageMain.evaluate(async () => {
    const res = await fetch("/examples/amount/report.json.unlisted", {
      cache: "no-store",
    });
    return res.status;
  });
  expect(unlisted).toBe(404);

  // ---------------- fully offline boundary ----------------
  const wireStart = capMain.requests.length;
  const logStart = harness.accessLog.length;
  const failStart = capMain.failures.length;
  await ctxMain.setOffline(true);
  try {
    // The app shell itself reloads from the prepared cache — navigation +
    // module graph + worker scripts all answered by the worker.
    const response = await pageMain.goto(`${harness.base}${MOUNT}`);
    expect(response !== null && response.ok(), "offline shell load failed").toBe(true);
    await waitMounted(pageMain);

    // Real own-file open through the real UI.
    await offerCanary(pageMain);
    await expect(pageMain.locator("[data-testid=doc-meta]")).toContainText(CANARY_SHA256.slice(-8));

    // The real run: native text + render + OCR (worker-served model,
    // worker script and wasm) + alignment — the complete offline
    // own-file workflow.
    await pageMain.locator("[data-testid=start-run]").click();
    await expect
      .poll(async () => (await pageMain.evaluate(() => __t25.snapshot())).run?.status ?? "none", {
        timeout: 180_000,
        intervals: [500, 1_000, 2_000],
      })
      .toBe("complete");
    const snap = await pageMain.evaluate(() => __t25.snapshot());
    const checks = snap.run!.checks;
    for (const capability of ["native_text", "render", "ocr", "alignment"]) {
      const found = checks.filter((c) => c.capability === capability);
      expect(found.length, `no ${capability} check ran offline`).toBeGreaterThan(0);
      for (const check of found) {
        expect(check.status, `offline ${capability} check ${check.id}`).toBe("completed");
      }
    }
    expect(snap.occurrences.length).toBeGreaterThan(0);
    const ocrCheck = checks.find((c) => c.capability === "ocr")!;
    expect(ocrCheck.producedOccurrences).toBeGreaterThan(0);

    // The model path itself resolves through the prepared cache — the
    // probe fetches + verifies the real pinned bytes with no network.
    const probe = await pageMain.evaluate(() => __t25.ocrPrepareProbe());
    expect(probe.ok).toBe(true);
    if (probe.ok) {
      expect(probe.preparation.sha256).toBe(MODEL_SHA256);
    }

    // An unlisted path offline fails honestly — the worker passes it
    // through and the dead network answers, never a fabricated response.
    const missed = await pageMain.evaluate(async () => {
      try {
        const res = await fetch("/examples/amount/report.json.unlisted", {
          cache: "no-store",
        });
        return { reached: true, status: res.status };
      } catch {
        return { reached: false, status: 0 };
      }
    });
    expect(missed.reached).toBe(false);
  } finally {
    await ctxMain.setOffline(false);
  }

  // Zero requests reached the server; the only failed request was the
  // deliberate unlisted-path probe; every emitted request stayed inside
  // the manifest allowlist plus that one named probe path.
  expect(harness.accessLog.slice(logStart), "offline requests reached the server").toHaveLength(0);
  const offlineFailures = capMain.failures.slice(failStart);
  for (const failure of offlineFailures) {
    expect(new URL(failure.url).pathname, `unexpected offline failure ${failure.url}`).toBe(
      "/examples/amount/report.json.unlisted",
    );
  }
  const allowedPlusProbe = new Set(manifestPaths);
  allowedPlusProbe.add("/examples/amount/report.json.unlisted");
  assertWireClean(capMain, wireStart, allowedPlusProbe, "prepared-offline");
  expect(capMain.pageErrors, "offline run produced page errors").toHaveLength(0);

  // No document material persisted: the cache census after a full
  // own-file run still contains only manifest paths.
  const dump2 = await pageMain.evaluate(() => __t25.cacheDump());
  for (const [name, urls] of Object.entries(dump2.entries)) {
    for (const url of urls) {
      const parsed = new URL(url);
      expect(
        manifestPaths.has(parsed.pathname) || parsed.pathname.startsWith("/__inkflip_sw__/"),
        `document material persisted in ${name}: ${parsed.pathname}`,
      ).toBe(true);
    }
  }
});

// ---------------------------------------------------------------------------
// TEST 3 — wrong-hash assets are refused, never silently reused.
// ---------------------------------------------------------------------------
test("model update cannot reuse a wrong hash — store-time and serve-time", async () => {
  const modelPath = await pageMain.evaluate(() => __t25.modelPath);

  // (a) Store-time: a manifest declaring the wrong sha256 for the model —
  //     the "update announced vs. real bytes" case — is refused with
  //     integrity_mismatch. The generation id is a digest of the manifest
  //     itself, so the refused update produces a different generation and
  //     the previous good generation stays active and intact.
  const tampered = {
    schema: "inkflip-offline-manifest/1",
    release: "t25-tampered",
    entries: [{ path: modelPath, sha256: "f".repeat(64), kind: "model" }],
  };
  const refused = await pageMain.evaluate((m) => __t25.prepare({ manifest: m }), tampered);
  expect(refused.ok).toBe(false);
  expect(refused.generation).not.toBeNull();
  expect(refused.generation).not.toBe(generationA);
  expect(
    refused.failed.some((f) => f.path === modelPath && f.error === "integrity_mismatch"),
    `expected integrity_mismatch for ${modelPath}`,
  ).toBe(true);
  const intact = await pageMain.evaluate(() => __t25.status());
  expect(intact.readiness).toBe("ready");
  expect(intact.generation).toBe(generationA);

  // (b) Serve-time: corrupt the stored model entry in the active
  //     generation while KEEPING its recorded digest header — the exact
  //     shape of a stale/wrong-body cache slot. The worker must verify,
  //     evict, report and fall through to the network — which is blocked
  //     offline, so the fetch fails closed instead of serving bad bytes.
  const corrupted = await pageMain.evaluate((path) => __t25.corruptCachedEntry(path), modelPath);
  expect(corrupted, "model entry was not in the active generation").not.toBeNull();
  await pageMain.evaluate(() => {
    __t25.swEvents.length = 0;
  });

  await ctxMain.setOffline(true);
  try {
    const fetched = await pageMain.evaluate(async (path) => {
      try {
        const res = await fetch(path, { cache: "no-store" });
        return { ok: true as const, status: res.status, body: (await res.text()).length };
      } catch (error) {
        return { ok: false as const, message: String(error) };
      }
    }, modelPath);
    expect(fetched.ok, "corrupted entry was served or silently reused").toBe(false);
  } finally {
    await ctxMain.setOffline(false);
  }

  const evicted = await pageMain.evaluate(() => __t25.swEvents);
  expect(
    evicted.some(
      (e) =>
        e.type === "inkflip:cache-evicted" &&
        e.path === modelPath &&
        e.reason === "declared_digest_mismatch",
    ),
    "no declared_digest_mismatch eviction reported",
  ).toBe(true);
  const dumpAfter = await pageMain.evaluate(() => __t25.cacheDump());
  expect(
    Object.values(dumpAfter.entries)
      .flat()
      .some((u) => u.endsWith(modelPath)),
    "evicted model entry still cached",
  ).toBe(false);

  // Status reports the degradation honestly — the missing entry surfaces.
  const degraded = await pageMain.evaluate(() => __t25.status());
  expect(degraded.readiness).toBe("degraded");
  expect(degraded.missing).toContain(modelPath);
});

// ---------------------------------------------------------------------------
// TEST 4 — clear + remove lifecycle, honestly bounded. Runs while offline:
// the lifecycle is all-local, and proving it under setOffline doubles as
// evidence that no hidden network step exists inside it.
// ---------------------------------------------------------------------------
test("clear tears down workers/URLs; remove deletes owned caches without a forensic promise", async () => {
  await ctxMain.setOffline(true);
  try {
    // A document must be open for clear to have something to tear down.
    if ((await pageMain.locator("[data-testid=doc-label]").count()) === 0) {
      await offerCanary(pageMain);
    }
    // A real object URL + a real Worker owned by the coordinator's
    // file-scoped CleanupRegistry — the same ownership channel the
    // pdf.js handle uses, so the spec observes the production revoke and
    // terminate verbs firing.
    const docUrl = await pageMain.evaluate(
      (bytes) => __t25.makeDocumentUrl(bytes),
      Array.from(CANARY_BYTES),
    );
    expect(docUrl.url.startsWith("blob:")).toBe(true);
    await pageMain.evaluate(() => __t25.makeProbeWorker());
    const eventMark = await pageMain.evaluate(() => __t25.events.length);

    // The real Clear control.
    await pageMain.locator("[data-testid=clear-file]").click();
    await expect
      .poll(async () => (await pageMain.evaluate(() => __t25.snapshot())).fileState)
      .toBe("idle");

    const events = await pageMain.evaluate(() => __t25.events.slice(0));
    const tail = events.slice(eventMark);
    expect(tail.some((e) => e.type === "clear")).toBe(true);
    expect(
      tail.some((e) => e.type === "teardown" && e.label === "pdfjs-document"),
      "pdf.js document/worker teardown never ran",
    ).toBe(true);
    expect(
      tail.some((e) => e.type === "teardown" && e.label === "document-object-url"),
      "owned object URL was never revoked",
    ).toBe(true);
    expect(
      tail.some((e) => e.type === "teardown" && e.label === "probe-worker"),
      "owned worker was never terminated",
    ).toBe(true);

    // The destroyed handle proves the pdf.js worker is gone.
    const probe = await pageMain.evaluate(() => __t25.probeLastHandle());
    expect(probe.ok).toBe(false);
    if (!probe.ok) expect(probe.message).toContain("closed");
    await expect(pageMain.locator("[data-testid=doc-label]")).toHaveCount(0);

    // Document clear is NOT offline-asset removal — the prepared caches
    // stay, honestly reported (degraded here because test 3 evicted the
    // model entry).
    const afterClear = await pageMain.evaluate(() => __t25.status());
    expect(["ready", "degraded"]).toContain(afterClear.readiness);
    const stillThere = await pageMain.evaluate(() => __t25.cacheDump());
    expect(
      stillThere.names.some((n) => n.startsWith(`${CACHE_PREFIX}gen-`)),
      "document clear removed offline caches — actions must be distinct",
    ).toBe(true);

    // The explicit "Remove offline assets" action.
    const removal = await pageMain.evaluate(() => __t25.remove());
    expect(removal.ok).toBe(true);
    expect(removal.removed).toContain(INDEX_CACHE);
    expect(removal.removed.some((n) => n.startsWith(`${CACHE_PREFIX}gen-`))).toBe(true);
    const dumpAfter = await pageMain.evaluate(() => __t25.cacheDump());
    expect(
      dumpAfter.names.filter((n) => n.startsWith(CACHE_PREFIX)),
      "offline caches remained after removal",
    ).toHaveLength(0);

    // Honest limits: the result carries the no-forensic-erasure wording
    // and never claims the opposite.
    const wording = removal.limitations.join(" ").toLowerCase();
    expect(wording).toContain("cannot be forensically erased");
    for (const claim of [
      "completely erased",
      "securely erased",
      "forensically erased all",
      "permanently deleted",
      "unrecoverable",
      "all traces removed",
      "no trace",
    ]) {
      expect(wording, `removal claims "${claim}"`).not.toContain(claim);
    }
    // …and the wording is user-visible, not just a return field.
    await expect(pageMain.locator("[data-testid=offline-limitations]")).toContainText(
      "cannot be forensically erased",
    );

    // Status after removal is honest: registered, nothing cached.
    const finalStatus = await pageMain.evaluate(() => __t25.status());
    expect(finalStatus.readiness).toBe("not_prepared");
    // Removal deleted caches — it did not unregister the worker (the
    // action is scoped to exactly what it names).
    const registrations = await pageMain.evaluate(() =>
      navigator.serviceWorker.getRegistrations().then((r) => r.length),
    );
    expect(registrations).toBeGreaterThan(0);
  } finally {
    await ctxMain.setOffline(false);
    await ctxMain.close();
  }
});
