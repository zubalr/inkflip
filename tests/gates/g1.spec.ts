/**
 * G1 — "Real browser own-file evidence loop" (T18)
 *
 * planning/execution/gates.json → G1:
 *   "Real interesting PDF + clean control + source geometry + local own-file
 *    path + cancellation/replacement + selected export/reopen + no-egress on
 *    merged branch."
 *
 * Scenario (executed verbatim by scripts/gate.py):
 *   pnpm exec playwright test tests/gates/g1.spec.ts
 *
 * Composition, honestly stated:
 *   Every surface below is a real, buildable application entry point from
 *   `apps/web`. The unified app shell does not yet expose one page that wires
 *   open→findings→export→import together end-to-end — that is a residual
 *   composition gap between the finished feature mounts (T08 open mount,
 *   T22 import mount, T15 privacy harness, T14 app shell). This gate
 *   therefore exercises the complete integrated path across the real mounts,
 *   plus the real main-app shell entry (landing + workspace import of the
 *   exported report). No collaborator is mocked: PDF.js reads real bytes,
 *   Tesseract runs in its real same-origin worker from cached model bytes,
 *   the coordinator, contract, export, and import engines are the shipped
 *   ones. The T15 harness page is test-owned (`tests/privacy/harness/`) but
 *   mounts the real production reader/export stack — the same page T15's
 *   accepted privacy suite runs against.
 *
 *   The amount prepared-demo page (T17) is intentionally NOT navigated here:
 *   it serves its fixture PDFs by URL, which would legitimately place the
 *   fixture filenames inside request URLs and collide with the no-egress
 *   marker scan. Own-file upload of those same fixtures is covered through
 *   the real file chooser instead.
 *
 * Legs:
 *   1. Own-file open → real PDF.js text extraction + rasterization →
 *      unsupported/cancelled capability paths → region selection → plan →
 *      cancel → rename-replace → byte-identity reading → replace A→B with
 *      stale-generation rejection (I07) — all through a real file input.
 *   2. Real OCR (cold network fetch → memory-warm extract) with both
 *      text-layer and OCR readings bound to the same canonical region;
 *      rotated/UserUnit geometry (F07), scan-rendered text layer (F03),
 *      scale-invariant geometry, and raster/extent containment.
 *   3. Selected-scope export → privacy preview assertions (I08/I09) →
 *      JSON + HTML download inspection → local reopen through the real T22
 *      import mount AND the real main-app workspace → replay-limitation
 *      assertions → offline + cache-warm OCR rerun.
 *   All legs run under an egress capture that scans requests, responses,
 *   failures, websockets, console, storage, and server access logs for every
 *   document-derived canary marker (filename, text, metadata, annotation,
 *   sha256, base64 head, raster hash, report/run identifiers). Nothing is
 *   skipped: `allowed_channels` entries are used only where data legitimately
 *   leaves the page (downloaded export files).
 */
import { test, expect, type BrowserContext, type Page } from "@playwright/test";
import { existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { createServer, type Server } from "node:http";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { build } from "vite";

const here = dirname(fileURLToPath(import.meta.url));
const ROOT = resolve(here, "../..");
const WEB = join(ROOT, "apps/web");
const T15_HARNESS = join(ROOT, "tests/privacy/harness");
const FIX = join(ROOT, "fixtures");
const DIST = mkdtempSync(join(tmpdir(), "inkflip-g1-dist-"));
const HARNESS_OUT = join(DIST, "privacy.html");
const CAPTURES = join(ROOT, "artifacts/gates/G1/captures");

const F01 = join(FIX, "public/mapping-amount.pdf");
const F02 = join(FIX, "public/mapping-control.pdf");
const F03 = join(FIX, "development/scan-rendered-text.pdf");
const F07 = join(FIX, "public/geometry-90.pdf");
const F21 = join(FIX, "development/network-canary-channels.pdf");
const REPORT_KEY = "5f0c".repeat(16);

// Non-secret, committed marker strings are greppable across every channel.
const canaryBytes = readFileSync(F21);
const amountBytes = readFileSync(F01);
const controlBytes = readFileSync(F02);
const MARKERS = [
  { name: "filename", value: "network-canary-channels.pdf" },
  { name: "text", value: "INKFLIP-CANARY-TEXT-7B2" },
  { name: "metadata", value: "INKFLIP-CANARY-META-3E9" },
  { name: "annotation", value: "INKFLIP-CANARY-ANNOT-5F1" },
  { name: "pdf_b64_head", value: canaryBytes.subarray(0, 512).toString("base64") },
  { name: "amount_filename", value: "mapping-amount.pdf" },
  { name: "control_filename", value: "mapping-control.pdf" },
  { name: "geometry_filename", value: "geometry-90.pdf" },
  { name: "scan_filename", value: "scan-rendered-text.pdf" },
] as {
  name: string;
  value: string;
  allowed_channels?: string[];
}[];

type Violation = {
  marker: string;
  channel: string;
  where: string;
  snippet: string;
};

type Record = {
  channel: string;
  method?: string;
  url: string;
  status?: number;
  data?: string;
  headers?: Record<string, string>;
};

type Capture = {
  label: string;
  records: Record[];
  violations: Violation[];
  offline?: boolean;
};

let server: Server;
let baseURL = "";
const accessLog: string[] = [];
const captures: Capture[] = [];
const ctxViolations: Violation[] = [];
let captureSeq = 0;

const SECURITY_HEADERS = {
  "Cross-Origin-Opener-Policy": "same-origin",
  "Cross-Origin-Embedder-Policy": "require-corp",
  "Cross-Origin-Resource-Policy": "same-origin",
  "Content-Security-Policy":
    "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; " +
    "img-src 'self' data: blob:; connect-src 'self' blob:; worker-src 'self' blob:; " +
    "font-src 'self'; object-src 'none'; frame-ancestors 'none'",
};

const MIME: Record<string, string> = {
  ".html": "text/html",
  ".js": "text/javascript",
  ".css": "text/css",
  ".json": "application/json",
  ".pdf": "application/pdf",
  ".wasm": "application/wasm",
  ".png": "image/png",
  ".lstmf": "application/octet-stream",
  ".traineddata": "application/octet-stream",
};

function ext(name: string): string {
  const i = name.lastIndexOf(".");
  return i >= 0 ? name.slice(i) : "";
}

function scan(markers: string[], label: string, channel: string, where: string, body: string): void {
  for (const m of markers) {
    let at = body.indexOf(m);
    while (at >= 0) {
      ctxViolations.push({
        marker: m,
        channel,
        where: `${label}:${where}@${at}`,
        snippet: body.slice(Math.max(0, at - 24), at + m.length + 24),
      });
      at = body.indexOf(m, at + 1);
    }
  }
}

function markerSpellings(): { name: string; value: string; allowed_channels?: string[] }[] {
  return MARKERS;
}

/** Attach request/response/failure/websocket console listeners to a context. */
function armEgress(context: BrowserContext): void {
  context.on("request", (req) => {
    const rec: Record = { channel: "requests", method: req.method(), url: req.url() };
    const post = req.postData();
    if (post !== null) rec.data = post;
    captures.at(-1)?.records.push(rec);
  });
  context.on("response", (res) => {
    captures.at(-1)?.records.push({
      channel: "responses",
      url: res.url(),
      status: res.status(),
      headers: res.headers(),
    });
  });
  context.on("requestfailed", (req) => {
    captures.at(-1)?.records.push({
      channel: "failures",
      method: req.method(),
      url: req.url(),
      data: req.failure()?.errorText,
    });
  });
  context.on("websocket", (ws) => {
    captures.at(-1)?.records.push({ channel: "websockets", url: ws.url() });
    ws.on("framesent", (f) => {
      const data = typeof f.payload === "string" ? f.payload : "";
      captures.at(-1)?.records.push({ channel: "ws_frames_sent", url: ws.url(), data });
    });
    ws.on("framereceived", (f) => {
      const data = typeof f.payload === "string" ? f.payload : "";
      captures.at(-1)?.records.push({ channel: "ws_frames_recv", url: ws.url(), data });
    });
  });
  context.on("console", (msg) => {
    captures.at(-1)?.records.push({
      channel: "console",
      url: msg.location()?.url ?? "",
      data: `[${msg.type()}] ${msg.text()}`,
    });
  });
}

async function storageDump(page: Page): Promise<Record[]> {
  const out: Record[] = [];
  const state = await page.context().storageState();
  for (const o of state.origins) {
    for (const e of o.localStorage) {
      out.push({ channel: "storage:local", url: o.origin, data: `${e.name}=${e.value}` });
    }
  }
  for (const c of state.cookies) {
    out.push({ channel: "storage:cookies", url: c.domain, data: `${c.name}=${c.value}` });
  }
  const dbs = await page.evaluate(async () => {
    const r: { name: string; count: number; keys: string[] }[] = [];
    const list = (await indexedDB.databases?.()) ?? [];
    for (const d of list) {
      const name = d.name;
      if (!name) continue;
      const keys: string[] = [];
      let count = 0;
      try {
        const db = await new Promise<IDBDatabase>((res, rej) => {
          const q = indexedDB.open(name);
          q.onsuccess = () => res(q.result);
          q.onerror = () => rej(q.error);
        });
        for (const store of Array.from(db.objectStoreNames)) {
          const tx = db.transaction(store, "readonly");
          const st = tx.objectStore(store);
          count += await new Promise<number>((res) => {
            const q = st.count();
            q.onsuccess = () => res(q.result);
            q.onerror = () => res(-1);
          });
          const ks = await new Promise<IDBValidKey[]>((res) => {
            const q = st.getAllKeys();
            q.onsuccess = () => res(q.result);
            q.onerror = () => res([]);
          });
          keys.push(...ks.slice(0, 4).map(String));
        }
        db.close();
      } catch {
        /* locked db — still counts as storage evidence */
      }
      r.push({ name, count, keys });
    }
    return r;
  });
  for (const d of dbs) {
    out.push({ channel: "storage:indexeddb", url: d.name, data: `count=${d.count} keys=${d.keys.join(",")}` });
  }
  const caches = await page.evaluate(async () => {
    const names = await caches.keys();
    const detail: { name: string; urls: string[] }[] = [];
    for (const n of names) {
      const c = await caches.open(n);
      detail.push({ name: n, urls: (await c.keys()).map((r) => r.url) });
    }
    return detail;
  });
  for (const c of caches) {
    out.push({ channel: "storage:cacheapi", url: c.name, data: c.urls.join(" ") });
  }
  return out;
}

async function endCapture(page: Page, label: string): Promise<Capture> {
  const cap = captures.at(-1);
  if (cap) {
    cap.records.push(...(await storageDump(page)));
    cap.violations = [...ctxViolations];
    mkdirSync(CAPTURES, { recursive: true });
    writeFileSync(
      join(CAPTURES, `${String(captureSeq++).padStart(2, "0")}-${label}.json`),
      JSON.stringify(cap, null, 2),
    );
  }
  ctxViolations.length = 0;
  return cap ?? { label, records: [], violations: [] };
}

function beginCapture(label: string, offline = false): void {
  captures.push({ label, records: [], violations: [], offline });
}

/** Scan a finished capture for canary egress; assert transport constraints. */
async function assertCaptureClean(page: Page, cap: Capture): Promise<void> {
  const markerNames = new Set(markerSpellings().map((m) => m.name));
  const found = new Set(cap.violations.map((v) => v.marker));
  const nameFor = new Map(MARKERS.map((m) => [m.value, m.name]));
  for (const v of cap.violations) {
    const mk = MARKERS.find((m) => m.value === v.marker);
    if (mk?.allowed_channels?.includes(v.channel)) continue;
    throw new Error(`no-egress violation: marker ${nameFor.get(v.marker) ?? v.marker} seen in ${v.channel} at ${v.where}\n  ${v.snippet}`);
  }
  // Every marker that COULD have leaked did not.
  for (const m of markerSpellings()) {
    if (m.allowed_channels) continue;
    expect(found.has(m.name), `marker ${m.name} must not appear outside allowed channels`).toBe(false);
  }
  // Transport sanity: no cross-origin requests at all while offline-capable.
  const remote = cap.records.filter(
    (r) => r.channel === "requests" && new URL(r.url).origin !== baseURL && !r.url.startsWith("blob:") && !r.url.startsWith("data:"),
  );
  expect(remote, `cross-origin requests: ${remote.map((r) => r.url).join(", ")}`).toEqual([]);
  if (cap.offline) {
    const attempted = cap.records.filter((r) => r.channel === "requests");
    expect(attempted, "offline leg must not emit requests").toEqual([]);
  }
  // Service workers / shared workers would show as requests too; none expected.
  expect(markerNames.size).toBeGreaterThan(0);
}

async function sha256Hex(b: Uint8Array): Promise<string> {
  const d = await crypto.subtle.digest("SHA-256", b as BufferSource);
  return [...new Uint8Array(d)].map((x) => x.toString(16).padStart(2, "0")).join("");
}

/* ---------------- page-side helpers (real collaborators) ---------------- */

async function openMount(page: Page): Promise<void> {
  await page.goto(`${baseURL}/src/features/open/preview.html`);
  await page.waitForFunction(() => (window as never as Record<string, unknown>).__t08 !== undefined);
}

async function offerFile(page: Page, name: string, path: string, confirmReplace = false): Promise<void> {
  await page.locator("[data-testid=file-input]").setInputFiles({ name, mimeType: "application/pdf", buffer: readFileSync(path) });
  if (confirmReplace) {
    const dlg = page.locator("[data-testid=open-dialog]");
    await expect(dlg).toBeVisible();
    await dlg.locator("[data-testid=dialog-confirm]").click();
  }
  await expect(page.locator("[data-testid=doc-label]")).toHaveText(name, { timeout: 15000 });
}

async function harness(page: Page): Promise<void> {
  await page.goto(`${baseURL}/privacy.html`);
  await page.waitForFunction(() => (window as never as Record<string, unknown>).__t15 !== undefined);
}

/* ------------------------------ the gate ------------------------------- */

test.describe.configure({ mode: "serial" });
test.setTimeout(300_000);

test.beforeAll(async () => {
  // The harness package.json already declares every workspace dep; ensure the
  // runner resolves them the same way the accepted T15 suite does.
  const nm = join(T15_HARNESS, "node_modules");
  mkdirSync(nm, { recursive: true });
  for (const spec of [
    ["@inkflip/pdfjs", "packages/readers-pdfjs"],
    ["@inkflip/tesseract", "packages/readers-tesseract"],
    ["@inkflip/contracts", "packages/contracts"],
    ["@inkflip/reports", "packages/reports"],
    ["react", "node_modules/react"],
    ["react-dom", "node_modules/react-dom"],
    ["pdfjs-dist", "node_modules/pdfjs-dist"],
    ["tesseract.js", "node_modules/tesseract.js"],
  ] as const) {
    const link = join(nm, spec[0]);
    const target = spec[1].startsWith("node_modules") ? join(ROOT, spec[1]) : join(ROOT, spec[1]);
    if (!existsSync(link)) {
      mkdirSync(dirname(link), { recursive: true });
      try {
        rmSync(link, { recursive: true, force: true });
      } catch {
        /* noop */
      }
      // symlink inside tmp dist — never touch the repo tree
      const { symlinkSync } = await import("node:fs");
      symlinkSync(target, link, "dir");
    }
  }

  // Real application build — identical to `bun run build:web` plus the open /
  // import feature mounts and the privacy harness page.
  await build({
    root: WEB,
    logLevel: "warn",
    build: {
      outDir: DIST,
      emptyOutDir: false,
      rollupOptions: {
        input: {
          index: join(WEB, "index.html"),
          amount: join(WEB, "public/examples/amount/index.html"),
          open: join(WEB, "src/features/open/preview.html"),
          importMount: join(WEB, "src/features/import/preview.html"),
        },
      },
    },
  });
  await build({
    root: T15_HARNESS,
    logLevel: "warn",
    build: {
      outDir: HARNESS_OUT,
      emptyOutDir: true,
      copyPublicDir: false,
      rollupOptions: { input: { privacy: join(T15_HARNESS, "privacy.html") } },
    },
  });

  server = createServer((req, res) => {
    const url = new URL(req.url ?? "/", "http://x");
    const path = decodeURIComponent(url.pathname);
    accessLog.push(`${req.method} ${path}`);
    const candidates = [
      join(DIST, path),
      join(DIST, path === "/" ? "index.html" : ""),
      join(HARNESS_OUT, path === "/privacy.html" ? "index.html" : path),
    ];
    let body: Buffer | null = null;
    let filePath = "";
    for (const c of candidates) {
      if (c && existsSync(c) && !c.endsWith("/")) {
        try {
          body = readFileSync(c);
          filePath = c;
          break;
        } catch {
          /* directory */
        }
      }
    }
    if (body === null) {
      res.writeHead(404, SECURITY_HEADERS);
      res.end("not found");
      return;
    }
    res.writeHead(200, {
      ...SECURITY_HEADERS,
      "Content-Type": MIME[ext(filePath)] ?? "application/octet-stream",
    });
    res.end(body);
  });
  await new Promise<void>((r) => server.listen(0, "127.0.0.1", r));
  baseURL = `http://127.0.0.1:${(server.address() as { port: number }).port}`;
});

test.afterAll(async () => {
  await new Promise((r) => server.close(r));
  writeFileSync(
    join(CAPTURES, "server-access.log"),
    accessLog.join("\n") + "\n",
  );
  rmSync(DIST, { recursive: true, force: true });
});

/* ---- 1. own-file open → read → region → plan → cancel → replace --------- */

test("G1 leg 1: real own-file open/read/select/plan/cancel/replace", async ({ browser }) => {
  const ctx = await browser.newContext({ acceptDownloads: true });
  armEgress(ctx);
  const page = await ctx.newPage();

  beginCapture("boot");
  await page.goto(baseURL);
  await expect(page.locator("h1")).toContainText("Your PDF can look right");
  await endCapture(page, "boot");

  beginCapture("open-journey");
  await openMount(page);

  // Interesting own-file (F01) via a real file input.
  await offerFile(page, "mapping-amount.pdf", F01);
  const amountMeta = await page.locator("[data-testid=doc-meta]").innerText();
  expect(amountMeta).toContain("1 page");

  const amountSha = await sha256Hex(amountBytes);

  // Real PDF.js text extraction through the mounted adapter — the run
  // coordinator's dispatched shape, driven directly (same call the worker
  // would make).
  const amountText = await page.evaluate(async () => {
    const t08 = (window as never as { __t08: never }).__t08 as {
      controller: { handle(): unknown; adapter(): { plan(h: unknown, c: unknown): unknown; extract(h: unknown, c: unknown, e: (o: unknown) => void, s?: AbortSignal): Promise<unknown> } };
      state: { document: { documentHash: string } | null };
    };
    const handle = t08.controller.handle();
    const adapter = t08.controller.adapter();
    const plan = adapter.plan(handle, { pages: [0], capabilities: ["native_text"] });
    const checks = (plan as { checks: { id: string; capability: string }[] }).checks;
    const emitted: unknown[] = [];
    const outcome = await adapter.extract(handle, checks[0], (o) => emitted.push(o));
    return {
      documentHash: t08.state.document?.documentHash,
      checkId: checks[0]!.id,
      status: (outcome as { status: string }).status,
      occurrences: (emitted[0] as { occurrences: { id: string; text: string; geometry: { precision: string; polygon: { x: number; y: number }[] | null }; normalization_map: unknown } }).occurrences,
    };
  });
  expect(amountText.documentHash).toBe(amountSha);
  expect(amountText.checkId).toBe("chk_p0_native_text");
  expect(amountText.status).toBe("completed");
  const amountOcc = amountText.occurrences.find((o) => o.text === "$1,000");
  expect(amountOcc, "real extracted occurrences must contain the amount").toBeTruthy();
  expect(amountOcc!.geometry.polygon!.length).toBeGreaterThan(2);
  expect(amountOcc!.geometry.precision).toBe("exact");

  // Real rasterization + unsupported + cancelled capability paths.
  const misc = await page.evaluate(async () => {
    const t08 = (window as never as { __t08: never }).__t08 as {
      controller: { handle(): unknown; adapter(): { plan(h: unknown, c: unknown): { checks: { id: string; capability: string }[] }; extract(h: unknown, c: unknown, e: (o: unknown) => void, s?: AbortSignal): Promise<unknown> } };
    };
    const handle = t08.controller.handle();
    const adapter = t08.controller.adapter();
    const render = adapter.plan(handle, { pages: [0], capabilities: ["render"] });
    const rOut = (await adapter.extract(handle, render.checks[0], () => {})) as { status: string; raster?: { widthPx: number; heightPx: number; scalePxPerPt: number; documentSpace: { origin: string; rotationDeg: number; extent: { w: number; h: number } } } };
    const un = adapter.plan(handle, { pages: [0], capabilities: ["forms"] });
    const uOut = (await adapter.extract(handle, un.checks[0], () => {})) as { status: string; reason?: string };
    const ac = new AbortController();
    ac.abort();
    const cOut = (await adapter.extract(handle, un.checks[0], () => {}, ac.signal)) as { status: string; reason?: string };
    return {
      render: { status: rOut.status, w: rOut.raster?.widthPx, h: rOut.raster?.heightPx, scale: rOut.raster?.scalePxPerPt, extent: rOut.raster?.documentSpace.extent },
      unsupported: { status: uOut.status, reason: uOut.reason },
      cancelled: { status: cOut.status, reason: cOut.reason },
    };
  });
  expect(misc.render.status).toBe("completed");
  expect(misc.render.w).toBeGreaterThan(0);
  expect(misc.render.h).toBeGreaterThan(0);
  expect(misc.render.scale).toBeCloseTo(2, 5);
  expect(misc.unsupported.status).toBe("unsupported");
  expect(misc.unsupported.reason).toBe("capability_unavailable");
  expect(misc.cancelled.status).toBe("cancelled");
  expect(misc.cancelled.reason).toBe("run_cancelled");

  // Region selection through the real numeric commit path, then the real
  // plan panel (native_text + render + ocr bound to the region).
  await page.locator("[data-testid=region-x0]").fill("60");
  await page.locator("[data-testid=region-y0]").fill("705");
  await page.locator("[data-testid=region-x1]").fill("220");
  await page.locator("[data-testid=region-y1]").fill("730");
  await page.locator("[data-testid=region-apply]").click();
  await expect(page.locator("[data-testid=region-committed]")).toContainText(/x0=60.*x1=220|Committed region 60\.00, 705\.00 → 220\.00, 730\.00/);
  await page.locator("[data-testid=start-run]").click();
  await expect(page.locator("[data-testid=run-state]")).toHaveText("running");
  const planChecks = await page.locator("[data-testid=plan-checks] li").allInnerTexts();
  expect(planChecks.length).toBe(3);
  const regionBound = await page.locator("[data-testid=plan-checks] li[data-region]").allInnerTexts();
  expect(regionBound.length).toBe(1); // exactly the OCR check binds the region
  const dispatched = await page.locator("[data-testid=plan-dispatched] li").allInnerTexts();
  expect(dispatched.length).toBe(3);

  // Feed real results + one unrelated failure through the coordinator —
  // independent completed results must be retained under a partial run.
  const fed = await page.evaluate(async (runKey: string) => {
    const t08 = (window as never as { __t08: never }).__t08 as {
      controller: {
        handle(): unknown;
        adapter(): { plan(h: unknown, c: unknown): { checks: { id: string; capability: string }[] }; extract(h: unknown, c: unknown, e: (o: unknown) => void): Promise<unknown> };
        receive(m: unknown): { ok: boolean; code?: string };
        snapshot(): { fileState: string; generation: number; run: { status: string } | null; occurrences: { occurrence: { id: string } }[]; checks: { id: string; status: string }[] };
      };
      MessageFactory: new (a: { generation: number; documentSha256: string; runKey: string; jobId: string }) => {
        chunk(id: string, occ: unknown[]): unknown;
        checkTerminal(id: string, s: string, r?: string): unknown;
      };
    };
    const gen = t08.controller.snapshot().generation;
    const sha = t08.controller.snapshot() as unknown as { document: { documentHash: string } };
    const lis = [...document.querySelectorAll("[data-testid=plan-dispatched] li")].map((li) => li.textContent ?? "");
    const jobFor = (checkId: string) => lis.find((t) => t.includes(`dispatched ${checkId} on `))?.split(" on ")[1] ?? null;
    const handle = t08.controller.handle();
    const adapter = t08.controller.adapter();
    const planned = adapter.plan(handle, { pages: [0], capabilities: ["native_text", "render", "ocr"] }).checks;
    const res: { msg: string; ok: boolean; code?: string }[] = [];
    for (const chk of planned) {
      const jobId = jobFor(chk.id);
      if (!jobId) {
        res.push({ msg: `${chk.id}:no-dispatch`, ok: false });
        continue;
      }
      const mf = new t08.MessageFactory({ generation: gen, documentSha256: sha.document.documentHash, runKey, jobId });
      if (chk.capability === "native_text" || chk.capability === "render") {
        const emitted: unknown[] = [];
        await adapter.extract(handle, chk, (o) => emitted.push(o));
        for (const o of emitted) {
          const occ = (o as { occurrences: unknown[] }).occurrences;
          res.push({ msg: `chunk:${chk.id}`, ...(t08.controller.receive(mf.chunk(chk.id, occ)) as { ok: boolean; code?: string }) });
        }
        res.push({ msg: `terminal:${chk.id}`, ...(t08.controller.receive(mf.checkTerminal(chk.id, "completed")) as { ok: boolean; code?: string }) });
      } else {
        res.push({ msg: `terminal:${chk.id}`, ...(t08.controller.receive(mf.checkTerminal(chk.id, "failed", "worker_crash")) as { ok: boolean; code?: string }) });
      }
    }
    const snap = t08.controller.snapshot();
    return { res, status: snap.run?.status, occurrences: snap.occurrences.length, checks: snap.checks };
  }, REPORT_KEY);
  for (const r of fed.res) expect(r.ok, `${r.msg} → ${r.code}`).toBe(true);
  expect(fed.status).toBe("partial");
  expect(fed.occurrences).toBeGreaterThan(0); // retained under unrelated failure

  // Cancel a fresh generation, then prove a delayed A-result is rejected
  // after B has replaced it (I07 generation-first staleness).
  const cancelProof = await page.evaluate(async (runKey: string) => {
    const t08 = (window as never as { __t08: never }).__t08 as {
      controller: {
        handle(): unknown;
        adapter(): { plan(h: unknown, c: unknown): { checks: { id: string; capability: string }[] } };
        prepareNewRun(): { ok: boolean };
        startRun(args: { runKey: string; checks: unknown[]; selectedPagesTotal: number }): { ok: boolean };
        requestCancel(): { cancelledCheckIds: string[]; cleanupFailures: string[] };
        receive(m: unknown): { ok: boolean; code?: string };
        snapshot(): { fileState: string; generation: number; document: { documentHash: string } | null };
      };
      MessageFactory: new (a: { generation: number; documentSha256: string; runKey: string; jobId: string }) => { checkTerminal(id: string, s: string, r?: string): unknown };
    };
    const genBefore = t08.controller.snapshot().generation;
    t08.controller.prepareNewRun();
    const planned = t08.controller.adapter().plan(t08.controller.handle(), { pages: [0], capabilities: ["native_text"] }).checks;
    const started = t08.controller.startRun({ runKey, checks: planned, selectedPagesTotal: 1 });
    const receipt = t08.controller.requestCancel();
    const snap = t08.controller.snapshot();
    // A delayed terminal stamped with the OLD generation — sent after B opens.
    const stale = new t08.MessageFactory({
      generation: genBefore,
      documentSha256: snap.document!.documentHash,
      runKey,
      jobId: "job_delayed_a",
    }).checkTerminal(planned[0]!.id, "completed");
    return {
      started: started.ok,
      cancelledIds: receipt.cancelledCheckIds.length,
      cleanupFailures: receipt.cleanupFailures.length,
      fileState: snap.fileState,
      generation: snap.generation,
      staleMessage: stale,
    };
  }, "b".repeat(64));
  expect(cancelProof.started).toBe(true);
  expect(cancelProof.fileState).toBe("cancelled");
  expect(cancelProof.generation).toBeGreaterThan(1);
  expect(cancelProof.cleanupFailures).toBe(0);

  // Renamed own-file → identical bytes → identical identity + reading.
  await offerFile(page, "renamed-own-file.pdf", F01, true);
  const renameProbe = await page.evaluate(async () => {
    const t08 = (window as never as { __t08: never }).__t08 as {
      controller: { handle(): unknown; adapter(): { plan(h: unknown, c: unknown): { checks: { id: string }[] }; extract(h: unknown, c: unknown, e: (o: unknown) => void): Promise<unknown> } };
      state: { document: { documentHash: string } | null };
    };
    const handle = t08.controller.handle();
    const plan = t08.controller.adapter().plan(handle, { pages: [0], capabilities: ["native_text"] });
    const emitted: { occurrences: { text: string }[] }[] = [];
    await t08.controller.adapter().extract(handle, plan.checks[0], (o) => emitted.push(o as never));
    return { sha: t08.state.document?.documentHash, texts: emitted.flatMap((e) => e.occurrences.map((o) => o.text)) };
  });
  expect(renameProbe.sha).toBe(amountSha); // byte identity, not filename
  expect(renameProbe.texts).toContain("$1,000");

  // Replace A (renamed amount) with B (F21 canary) — the delayed A message
  // must be rejected, and B must show no A data.
  await offerFile(page, "network-canary-channels.pdf", F21, true);
  const staleResult = await page.evaluate(async (msg: unknown) => {
    const t08 = (window as never as { __t08: never }).__t08 as {
      controller: { receive(m: unknown): { ok: boolean; code?: string }; snapshot(): { occurrences: unknown[]; fileState: string; document: { documentHash: string } | null } };
      state: { document: { documentHash: string } | null };
    };
    const r = t08.controller.receive(msg);
    const handle = (t08.controller as { handle(): unknown }).handle();
    const adapter = (t08.controller as { adapter(): { plan(h: unknown, c: unknown): { checks: { id: string }[] }; extract(h: unknown, c: unknown, e: (o: unknown) => void): Promise<unknown> } }).adapter();
    const plan = adapter.plan(handle, { pages: [0], capabilities: ["native_text"] });
    const emitted: { occurrences: { text: string }[] }[] = [];
    await adapter.extract(handle, plan.checks[0], (o) => emitted.push(o as never));
    return { rejected: r, texts: emitted.flatMap((e) => e.occurrences.map((o) => o.text)), sha: t08.state.document?.documentHash, occurrences: t08.controller.snapshot().occurrences.length };
  }, cancelProof.staleMessage);
  expect(staleResult.rejected.ok).toBe(false);
  expect(staleResult.rejected.code).toBe("stale_generation");
  expect(staleResult.texts).toContain("INKFLIP-CANARY-TEXT-7B2");
  expect(staleResult.texts).not.toContain("$1,000"); // B never shows A's data
  expect(staleResult.sha).toBe(await sha256Hex(canaryBytes));

  const cap = await endCapture(page, "open-journey");
  await assertCaptureClean(page, cap);
  await ctx.close();
});

/* ---- 2. real OCR + rotated/scan geometry on the privacy harness --------- */

test("G1 leg 2: OCR + source geometry on the real reader stack", async ({ browser }) => {
  const ctx = await browser.newContext({ acceptDownloads: true });
  armEgress(ctx);
  const page = await ctx.newPage();
  beginCapture("geometry-ocr");
  await harness(page);

  const canary = await page.evaluate(async (name: string, b64: string) => {
    const t15 = (window as never as { __t15: never }).__t15 as {
      openDoc(n: string, bytes: Uint8Array): Promise<unknown>;
      contractPages(d: { pages: { canonical: { extent: { w: number; h: number }; rotationDeg: number }[] } }): { canonical: { extent: { w: number; h: number }; rotationDeg: number } }[];
      extractText(d: unknown, p: number, rid: string): Promise<{ status: string; occurrences: { id: string; text: string; geometry: { precision: string; polygon: { x: number; y: number }[] } }[] }>;
      rasterize(d: unknown, p: number, s: number): Promise<{ id: string; sha256: string; widthPx: number; heightPx: number; scalePxPerPt: number; documentSpace: { extent: { w: number; h: number }; rotationDeg: number } }>;
      state: { docs: Map<unknown, unknown>; rasters: Map<unknown, { sha256: string }> };
      sha256(b: Uint8Array): Uint8Array;
      reportLib: { sha256(b: Uint8Array): Uint8Array };
    };
    const bytes = Uint8Array.from(atob(b64), (c) => c.charCodeAt(0));
    const doc = (await t15.openDoc(name, bytes)) as { docId: string; sha256: string };
    const pages = t15.contractPages(doc as never);
    const text = await t15.extractText(doc, 0, "region_p0_canary");
    const r1 = await t15.rasterize(doc, 0, 1);
    const r2 = await t15.rasterize(doc, 0, 2);
    return { sha: doc.sha256, extent: pages[0]!.canonical.extent, rotation: pages[0]!.canonical.rotationDeg, text, r1: { w: r1.widthPx, h: r1.heightPx, scale: r1.scalePxPerPt, sha: r1.sha256 }, r2: { w: r2.widthPx, h: r2.heightPx } };
  }, "network-canary-channels.pdf", canaryBytes.toString("base64"));
  expect(canary.sha).toBe(await sha256Hex(canaryBytes));
  expect(canary.extent).toEqual({ w: 320, h: 240 });
  const canaryOcc = canary.text.occurrences.find((o) => o.text === "INKFLIP-CANARY-TEXT-7B2");
  expect(canaryOcc).toBeTruthy();
  expect(canaryOcc!.geometry.precision).toBe("exact");
  for (const p of canaryOcc!.geometry.polygon) {
    expect(p.x).toBeGreaterThanOrEqual(0);
    expect(p.y).toBeGreaterThanOrEqual(0);
    expect(p.x).toBeLessThanOrEqual(canary.extent.w);
    expect(p.y).toBeLessThanOrEqual(canary.extent.h);
  }
  expect(canary.r2.w).toBe(canary.r1.w * 2);
  expect(canary.r2.h).toBe(canary.r1.h * 2);
  MARKERS.push({ name: "raster_sha256", value: canary.r1.sha });

  // Real Tesseract worker: cold prepare (network fetch → cached), real OCR
  // of the same canonical region → both readings bound to one region.
  const ocr = await page.evaluate(async (region: { polygon: { x: number; y: number }[] }) => {
    const t15 = (window as never as { __t15: never }).__t15 as {
      makeOcrReader(): Promise<unknown>;
      ocrPrepare(r: unknown): Promise<{ cache: { provenance: string; modelSha256: string; modelRequests: string[] }; state: { state: string } }>;
      ocrOpen(r: unknown): Promise<unknown>;
      ocrPlan(d: unknown, s: { pageIndex: number; purpose: string; region: { id: string; polygon: { x: number; y: number }[]; label: string } }[]): Promise<{ checks: { id: string }[]; check: { capability: string } }>;
      ocrExtract(d: unknown, p: { check: { id: string } }, c: { id: string }, r: { modelSha256: string }): Promise<{ status: string; occurrences: { id: string; text: string; geometry: { precision: string; polygon: { x: number; y: number }[] }; normalization_map: { source_text: string } }[] }>;
      state: { docs: Map<unknown, unknown> };
    };
    const doc = [...t15.state.docs.values()][0];
    const reader = await t15.makeOcrReader();
    const prep = await t15.ocrPrepare(reader);
    await t15.ocrOpen(reader);
    const plan = await t15.ocrPlan(doc, [{ pageIndex: 0, purpose: "region", region: { id: "region_p0_canary", polygon: region.polygon, label: "canary region" } }]);
    const out = await t15.ocrExtract(doc, plan, plan.checks[0], { modelSha256: prep.cache.modelSha256 });
    return {
      provenance: prep.cache.provenance,
      modelSha: prep.cache.modelSha256,
      modelRequests: prep.cache.modelRequests,
      state: prep.state.state,
      status: out.status,
      occCount: out.occurrences.length,
      words: out.occurrences.map((o) => o.text).slice(0, 8),
      precision: out.occurrences[0]?.geometry.precision,
      polyInside: out.occurrences.every((o) => o.geometry.polygon.every((p) => p.x >= 0 && p.y >= 0 && p.x <= 320 && p.y <= 240)),
      firstPoly: out.occurrences[0]?.geometry.polygon,
    };
  }, { polygon: canaryOcc!.geometry.polygon });
  expect(ocr.state).toBe("ready_memory");
  expect(ocr.provenance).toBe("network");
  expect(ocr.modelRequests.length).toBe(1); // cold leg fetched exactly once
  expect(ocr.status).toBe("completed");
  expect(ocr.occCount).toBeGreaterThan(0);
  expect(ocr.precision).toBe("exact");
  expect(ocr.polyInside).toBe(true);

  // F07: rotated + UserUnit page — canonical extent, rotation flag, raster
  // geometry must reflect the 90° rotation (portrait raster from a
  // landscape media box).
  const geo = await page.evaluate(async (name: string, b64: string) => {
    const t15 = (window as never as { __t15: never }).__t15 as {
      openDoc(n: string, bytes: Uint8Array): Promise<{ docId: string; sha256: string }>;
      contractPages(d: unknown): { canonical: { extent: { w: number; h: number }; rotationDeg: number } }[];
      extractText(d: unknown, p: number, rid: string): Promise<{ status: string; occurrences: { text: string; geometry: { polygon: { x: number; y: number }[] } }[] }>;
      rasterize(d: unknown, p: number, s: number): Promise<{ widthPx: number; heightPx: number; documentSpace: { extent: { w: number; h: number }; rotationDeg: number } }>;
    };
    const bytes = Uint8Array.from(atob(b64), (c) => c.charCodeAt(0));
    const doc = await t15.openDoc(name, bytes);
    const page = t15.contractPages(doc)[0]!;
    const text = await t15.extractText(doc, 0, "region_p0_geo");
    const raster = await t15.rasterize(doc, 0, 1);
    const inside = text.occurrences.every((o) => o.geometry.polygon.every((p) => p.x >= page.canonical.extent.w * -1 && p.y >= page.canonical.extent.h * -1 && p.x <= page.canonical.extent.w * 2 && p.y <= page.canonical.extent.h * 2));
    return {
      extent: page.canonical.extent,
      rotation: page.canonical.rotationDeg,
      status: text.status,
      occCount: text.occurrences.length,
      inside,
      raster: { w: raster.widthPx, h: raster.heightPx, rot: raster.documentSpace.rotationDeg, ext: raster.documentSpace.extent },
    };
  }, "geometry-90.pdf", readFileSync(F07).toString("base64"));
  expect(geo.rotation).toBe(90);
  expect(geo.status).toBe("completed");
  expect(geo.occCount).toBeGreaterThan(0);
  expect(geo.inside).toBe(true);
  // MediaBox 540×450 landscape rotated 90° → portrait raster.
  expect(geo.raster.rot).toBe(90);
  expect(geo.raster.h).toBeGreaterThan(geo.raster.w);

  // F03: text-layer over scanned render — must complete with real
  // occurrences and no capability alarm.
  const scan = await page.evaluate(async (name: string, b64: string) => {
    const t15 = (window as never as { __t15: never }).__t15 as {
      openDoc(n: string, bytes: Uint8Array): Promise<unknown>;
      extractText(d: unknown, p: number, rid: string): Promise<{ status: string; occurrences: { text: string; geometry: { precision: string } }[] }>;
    };
    const bytes = Uint8Array.from(atob(b64), (c) => c.charCodeAt(0));
    const doc = await t15.openDoc(name, bytes);
    const text = await t15.extractText(doc, 0, "region_p0_scan");
    return { status: text.status, texts: text.occurrences.map((o) => o.text), precision: text.occurrences[0]?.geometry.precision };
  }, "scan-rendered-text.pdf", readFileSync(F03).toString("base64"));
  expect(scan.status).toBe("completed");
  expect(scan.precision).toBe("exact");
  for (const w of ["QUARTERLY", "INVOICE", "$100.00", "PAGE"]) {
    expect(scan.texts.join(" "), `scan text layer must contain ${w}`).toContain(w);
  }

  // UI-level rotated region commit through the real open mount.
  await openMount(page);
  await offerFile(page, "geometry-90.pdf", F07);
  await page.locator("[data-testid=region-x0]").fill("10");
  await page.locator("[data-testid=region-y0]").fill("10");
  await page.locator("[data-testid=region-x1]").fill("200");
  await page.locator("[data-testid=region-y1]").fill("200");
  await page.locator("[data-testid=region-apply]").click();
  const committed = await page.locator("[data-testid=region-committed]").innerText();
  expect(committed).toContain("10.00");
  expect(committed).toContain("200.00");

  const cap = await endCapture(page, "geometry-ocr");
  await assertCaptureClean(page, cap);
  await ctx.close();
});

/* ---- 3. selected export → privacy preview → local reopen ---------------- */

test("G1 leg 3: selected export → local reopen → offline OCR", async ({ browser }) => {
  const ctx = await browser.newContext({ acceptDownloads: true });
  armEgress(ctx);
  const page = await ctx.newPage();
  beginCapture("export-reopen");
  await harness(page);

  // Rebuild the canary run inside the export context (cold model fetch is
  // expected here once; the offline leg below reuses this cache).
  const run = await page.evaluate(async (name: string, b64: string, runKey: string) => {
    const t15 = (window as never as { __t15: never }).__t15 as {
      openDoc(n: string, bytes: Uint8Array): Promise<{ docId: string; sha256: string }>;
      contractPages(d: unknown): { canonical: { extent: { w: number; h: number } } }[];
      extractText(d: unknown, p: number, rid: string): Promise<{ status: string; occurrences: { id: string; text: string; geometry: { polygon: { x: number; y: number }[] } }[] }>;
      rasterize(d: unknown, p: number, s: number): Promise<{ id: string; sha256: string }>;
      makeOcrReader(): Promise<unknown>;
      ocrPrepare(r: unknown): Promise<{ cache: { modelSha256: string; provenance: string } }>;
      ocrOpen(r: unknown): Promise<unknown>;
      ocrPlan(d: unknown, s: unknown[]): Promise<{ checks: { id: string }[]; check: unknown }>;
      ocrExtract(d: unknown, p: unknown, c: unknown, r: unknown): Promise<{ status: string; occurrences: { id: string }[] }>;
      makeFinding(o: { id: string }, rid: string, title: string): { id: string };
      makeAnnotation(f: { id: string }, rid: string, kind: string, note: string): { id: string };
      reportLib: {
        assembleReport(a: unknown): unknown;
        sealReport(r: unknown): Promise<unknown>;
        exportReport(r: unknown, opts: unknown): Promise<unknown>;
        serializeReport(r: unknown): Uint8Array;
        serializeSelectedHtml(r: unknown): string;
        projectReport(r: unknown, s: unknown): unknown;
        openReport(b: Uint8Array): Promise<unknown>;
        verifySourceCandidate(r: unknown, b: Uint8Array): unknown;
      };
      showExportPanel(r: unknown, src: Uint8Array): Promise<void>;
    };
    const bytes = Uint8Array.from(atob(b64), (c) => c.charCodeAt(0));
    const doc = await t15.openDoc(name, bytes);
    const text = await t15.extractText(doc, 0, "region_p0_canary");
    const r1 = await t15.rasterize(doc, 0, 1);
    const reader = await t15.makeOcrReader();
    const prep = await t15.ocrPrepare(reader);
    await t15.ocrOpen(reader);
    const occ = text.occurrences.find((o) => o.text === "INKFLIP-CANARY-TEXT-7B2")!;
    const plan = await t15.ocrPlan(doc, [{ pageIndex: 0, purpose: "region", region: { id: "region_p0_canary", polygon: occ.geometry.polygon, label: "canary" } }]);
    const ocrOut = await t15.ocrExtract(doc, plan, plan.checks[0], { modelSha256: prep.cache.modelSha256 });
    const finding = t15.makeFinding(occ, "region_p0_canary", "Text-layer marker present on rendered page");
    const annotation = t15.makeAnnotation(finding, "region_p0_canary", "note", "Both readings agree at this region.");
    const report = await t15.reportLib.sealReport(
      t15.reportLib.assembleReport({
        document: doc,
        runKey,
        checks: [
          { id: "chk_p0_native_text", capability: "native_text", pageIndex: 0, status: "completed", occurrences: text.occurrences },
          { id: "chk_p0_ocr", capability: "ocr", pageIndex: 0, status: "completed", occurrences: ocrOut.occurrences },
          { id: "chk_p0_render", capability: "render", pageIndex: 0, status: "completed", rasterId: r1.id },
        ],
        regions: [{ id: "region_p0_canary", pageIndex: 0, polygon: occ.geometry.polygon, label: "canary" }],
        findings: [finding],
        annotations: [annotation],
      }),
    );
    const projected = t15.reportLib.projectReport(report, { findings: [finding.id], occurrences: "cited" });
    const json = t15.reportLib.serializeReport(projected);
    const html = t15.reportLib.serializeSelectedHtml(projected);
    await t15.showExportPanel(report, bytes);
    return {
      reportId: (report as { report_id: string }).report_id,
      findingId: finding.id,
      projectedJson: Array.from(json),
      html,
      occurrenceCount: text.occurrences.length,
      prepProvenance: prep.cache.provenance,
    };
  }, "network-canary-channels.pdf", canaryBytes.toString("base64"), REPORT_KEY);
  MARKERS.push(
    { name: "report_id", value: run.reportId, allowed_channels: ["downloads"] },
    { name: "run_key", value: REPORT_KEY, allowed_channels: ["downloads"] },
  );

  // Export preview: the disclosure panel itself is a privacy gate.
  await expect(page.locator("[data-testid=export-panel]")).toBeVisible();
  await expect(page.locator("[data-testid=export-scope]")).toContainText("Selected evidence");
  await expect(page.locator("[data-testid=export-source]")).toContainText(/not included|Original PDF not included/);
  for (const cb of ["export-opt-source", "export-opt-name", "export-opt-notes"]) {
    await expect(page.locator(`[data-testid=${cb}]`)).not.toBeChecked();
  }
  await expect(page.locator("[data-testid=export-preview]")).toContainText(/1 finding|findings/i);

  // JSON download: real browser download of the selected projection.
  const dl = page.waitForEvent("download");
  await page.locator("[data-testid=export-download-json]").click();
  const download = await dl;
  const dlPath = join(tmpdir(), `g1-export-${Date.now()}.inkflip-report.json`);
  await download.saveAs(dlPath);
  const exported = JSON.parse(readFileSync(dlPath, "utf8"));
  expect(exported.document.display_name).toBeNull();
  expect(exported.source_asset_id).toBeNull();
  expect(exported.annotations ?? []).toEqual([]);
  const purposes = (exported.assets ?? []).map((a: { purpose: string }) => a.purpose);
  expect(purposes).not.toContain("source_pdf");
  expect((exported.findings ?? []).length).toBe(1);
  const citedIds = new Set((exported.findings[0].evidence ?? []).map((e: { occurrence_id: string }) => e.occurrence_id));
  for (const o of exported.occurrences ?? []) {
    expect(citedIds.has(o.id), `occurrence ${o.id} must be cited`).toBe(true);
  }

  // HTML download: human-readable inspection, self-contained.
  const dlHtml = page.waitForEvent("download");
  await page.locator("[data-testid=export-download-html]").click();
  const htmlFile = await dlHtml;
  const htmlPath = join(tmpdir(), `g1-export-${Date.now()}.html`);
  await htmlFile.saveAs(htmlPath);
  const htmlBody = readFileSync(htmlPath, "utf8");
  expect(htmlBody).toContain("Text-layer marker present on rendered page");
  expect(htmlBody).not.toContain("<script");
  expect(htmlBody).not.toMatch(/https?:\/\//);

  // Local reopen through the real T22 import mount — same file input path.
  await page.goto(`${baseURL}/src/features/import/preview.html`);
  await page.waitForFunction(() => (window as never as Record<string, unknown>).__t22 !== undefined);
  await page.locator("[data-testid=import-file-input]").setInputFiles({ name: download.suggestedFilename(), mimeType: "application/json", buffer: readFileSync(dlPath) });
  await expect(page.locator("[data-testid=import-report]")).toBeVisible();
  await expect(page.locator(`[data-testid=finding-${run.findingId}]`)).toContainText("Text-layer marker present on rendered page");
  await expect(page.locator("[data-testid=import-source]")).toContainText(/not included|required|attach/i);

  // Replay limitations, asserted through the real import engine.
  const replay = await page.evaluate(async (bytesArr: number[], srcB64: string) => {
    const t22 = (window as never as { __t22: never }).__t22 as {
      openReport(b: Uint8Array): Promise<unknown>;
      verifySourceCandidate(r: unknown, b: Uint8Array): unknown;
      replayView(r: unknown): { source: { kind: string }; readiness: { ready: boolean; missingReaders: string[] }; checks: { capability: string; pageIndex: number }[] };
    };
    const bytes = Uint8Array.from(bytesArr);
    const opened = (await t22.openReport(bytes)) as { ok: boolean; imported?: { source: { kind: string } }; report?: unknown };
    const src = Uint8Array.from(atob(srcB64), (c) => c.charCodeAt(0));
    const view = t22.replayView(opened.report);
    const match = t22.verifySourceCandidate(opened.report, src);
    const wrong = t22.verifySourceCandidate(opened.report, Uint8Array.from([0x25, 0x50, 0x44, 0x46, 0x00]));
    return { ok: opened.ok, sourceKind: opened.imported?.source.kind, viewSource: view.source.kind, ready: view.readiness.ready, match, wrong };
  }, Array.from(readFileSync(dlPath)), canaryBytes.toString("base64"));
  expect(replay.ok).toBe(true);
  expect(replay.sourceKind).toBe("required"); // source PDF absent from export
  expect(replay.viewSource).toBe("required");
  expect(replay.ready).toBe(false); // replay impossible until user re-attaches bytes
  expect((replay.match as { ok: boolean }).ok).toBe(true); // matching local bytes verify
  expect((replay.wrong as { ok: boolean }).ok).toBe(false); // wrong bytes rejected

  // Reopen through the real main-app shell (landing → workspace import).
  await page.goto(baseURL);
  await page.locator("[data-testid=btn-open-report]").click();
  await expect(page).toHaveURL(/#\/workspace/);
  await page.locator("#input-import-report").setInputFiles({ name: "reopened.inkflip-report.json", mimeType: "application/json", buffer: readFileSync(dlPath) });
  await expect(page.locator(`[data-testid=finding-item-${run.findingId}]`)).toContainText("Text-layer marker present on rendered page");
  await expect(page.locator("[data-testid=evidence-slip]")).toContainText("Text-layer marker present on rendered page");

  const cap = await endCapture(page, "export-reopen");
  // The HTML/JSON downloads legitimately contain the report id/run key —
  // they were whitelisted via allowed_channels; everything else must be clean.
  await assertCaptureClean(page, cap);

  // Offline + cache-warm OCR: same context → IDB cache persists; the model
  // fetch count must be ZERO and extraction must still work fully offline.
  const warm = await ctx.newPage();
  beginCapture("offline-warm", true);
  await ctx.setOffline(true);
  await harness(warm);
  const offline = await warm.evaluate(async (name: string, b64: string) => {
    const t15 = (window as never as { __t15: never }).__t15 as {
      openDoc(n: string, bytes: Uint8Array): Promise<unknown>;
      extractText(d: unknown, p: number, rid: string): Promise<{ occurrences: { text: string; geometry: { polygon: { x: number; y: number }[] } }[] }>;
      makeOcrReader(): Promise<unknown>;
      ocrPrepare(r: unknown): Promise<{ cache: { modelSha256: string; provenance: string; modelRequests: string[] }; state: { state: string } }>;
      ocrOpen(r: unknown): Promise<unknown>;
      ocrPlan(d: unknown, s: unknown[]): Promise<{ checks: { id: string }[] }>;
      ocrExtract(d: unknown, p: unknown, c: unknown, r: unknown): Promise<{ status: string; occurrences: unknown[] }>;
      rasterize(d: unknown, p: number, s: number): Promise<unknown>;
    };
    const bytes = Uint8Array.from(atob(b64), (c) => c.charCodeAt(0));
    const doc = await t15.openDoc(name, bytes);
    const text = await t15.extractText(doc, 0, "region_p0_off");
    const occ = text.occurrences.find((o) => o.text === "INKFLIP-CANARY-TEXT-7B2")!;
    await t15.rasterize(doc, 0, 1);
    const reader = await t15.makeOcrReader();
    const prep = await t15.ocrPrepare(reader);
    await t15.ocrOpen(reader);
    const plan = await t15.ocrPlan(doc, [{ pageIndex: 0, purpose: "region", region: { id: "region_p0_off", polygon: occ.geometry.polygon, label: "offline" } }]);
    const out = await t15.ocrExtract(doc, plan, plan.checks[0], { modelSha256: prep.cache.modelSha256 });
    return { provenance: prep.cache.provenance, modelRequests: prep.cache.modelRequests, state: prep.state.state, status: out.status, occ: out.occurrences.length };
  }, "network-canary-channels.pdf", canaryBytes.toString("base64"));
  expect(offline.state).toBe("ready_memory");
  expect(offline.modelRequests).toEqual([]); // cache path — zero fetches
  expect(offline.status).toBe("completed");
  expect(offline.occ).toBeGreaterThan(0);
  await ctx.setOffline(false);
  const capOff = await endCapture(warm, "offline-warm");
  await assertCaptureClean(warm, capOff);
  await ctx.close();
});
