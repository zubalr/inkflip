/**
 * G1 — "Real browser own-file evidence loop" (T18)
 *
 * planning/execution/gates.json → G1:
 *   "Real interesting PDF + clean control + source geometry + local own-file
 *    path + cancellation/replacement + selected export/reopen + no-egress on
 *    merged branch."
 *
 * Scenario (executed verbatim by scripts/gate.py, adapted to):
 *   pnpm exec playwright test tests/gates/g1.spec.ts
 *   → bun x --no-install playwright test tests/gates/g1.spec.ts --reporter=junit
 *
 * Composition, honestly stated:
 *   Every surface below is a real, buildable application entry point from
 *   `apps/web`. The unified app shell does not yet expose one page that wires
 *   open→findings→export→import together end-to-end — that is a residual
 *   composition gap between the finished feature mounts (T08 open mount,
 *   T22 import mount, T15 privacy harness, T16 export panel, T14 app shell).
 *   This gate therefore exercises the complete integrated path across the
 *   real mounts plus the real main-app shell (landing → workspace import of
 *   the exported report). No collaborator is mocked: PDF.js reads real
 *   bytes, Tesseract runs in its real same-origin worker from staged model
 *   bytes, and the coordinator, contracts, export and import engines are the
 *   shipped ones. The T15 harness page is test-owned
 *   (`tests/privacy/harness/`) but mounts the real production reader/export
 *   stack — the same page T15's accepted privacy suite runs against.
 *
 *   The amount prepared-demo page (T17) is intentionally NOT navigated here:
 *   it serves its fixture PDFs by URL, which would legitimately place the
 *   fixture filenames inside request URLs and collide with the no-egress
 *   marker scan. Own-file upload of those same fixtures is covered through
 *   the real file chooser instead.
 *
 * Legs:
 *   1. Own-file open → real PDF.js text extraction + rasterization →
 *      unsupported/cancelled capability paths → region selection → real
 *      run plan → coordinator-fed real results under an unrelated failure →
 *      cancel → rename-replace byte identity → clean control → replace A→B
 *      with stale-generation rejection (I07) — all through a real file
 *      input on the T08 mount.
 *   2. Real OCR (cold staged fetch → in-memory extract) with both
 *      text-layer and OCR readings bound to the same canonical region;
 *      rotated/UserUnit geometry (F07), scan-rendered text layer (F03),
 *      scale-invariant rasterization, raster/extent containment — on the
 *      T15 harness.
 *   3. Selected-scope export → real T16 ExportPanel privacy preview →
 *      JSON + HTML download inspection → local reopen through the real T22
 *      import mount AND the real main-app workspace → replay-limitation
 *      assertions → cache-warm + fully-offline OCR rerun on the live page.
 *
 *   All legs run under an egress capture that records requests, responses,
 *   failures, websockets, console, downloads and storage, scans every
 *   captured byte for every document-derived canary marker (filenames,
 *   visible text, metadata, annotation, doc sha256, pdf base64 head, raster
 *   hash, report/run identifiers) and cross-checks the server-side access
 *   log. Nothing is skipped: `allowed_channels` entries are used only where
 *   data legitimately leaves the page (the local export downloads).
 */
import { test, expect, type BrowserContext, type Page, type Download } from "@playwright/test";
import {
  existsSync,
  mkdirSync,
  mkdtempSync,
  readFileSync,
  rmSync,
  symlinkSync,
  writeFileSync,
} from "node:fs";
import { createHash } from "node:crypto";
import { createServer, type Server } from "node:http";
import { tmpdir } from "node:os";
import { dirname, join, normalize, resolve, sep } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const ROOT = resolve(here, "../..");
const WEB = join(ROOT, "apps/web");
const T15_HARNESS = join(ROOT, "tests/privacy/harness");
const FIX = join(ROOT, "fixtures");
const DIST = mkdtempSync(join(tmpdir(), "inkflip-g1-dist-"));
const CAPTURES = join(ROOT, "artifacts/gates/G1/captures");

const F01 = join(FIX, "public/mapping-amount.pdf");
const F01_CONTROL = join(FIX, "public/mapping-control.pdf");
const F03 = join(FIX, "development/scan-correct.pdf");
const F07 = join(FIX, "public/geometry-90.pdf");
const F21 = join(FIX, "development/network-canary-channels.pdf");

const canaryBytes = readFileSync(F21);
const amountBytes = readFileSync(F01);
const controlBytes = readFileSync(F01_CONTROL);
const geoBytes = readFileSync(F07);
const scanBytes = readFileSync(F03);
const CANARY_SHA256 = createHash("sha256").update(canaryBytes).digest("hex");
const AMOUNT_SHA256 = createHash("sha256").update(amountBytes).digest("hex");
const CONTROL_SHA256 = createHash("sha256").update(controlBytes).digest("hex");

type Marker = {
  name: string;
  value: string;
  /** Channels where this marker may legitimately appear (local downloads). */
  allowed_channels?: string[];
};

// Non-secret, committed marker strings — greppable across every channel.
// Values are the REAL strings inside the generated fixtures (see
// scripts/make_fixtures.py canary_entries / mapping-amount recipes).
const MARKERS: Marker[] = [
  { name: "canary_filename", value: "network-canary-channels.pdf" },
  { name: "canary_text", value: "INKFLIP-CANARY-TEXT-7B2", allowed_channels: ["downloads"] },
  { name: "canary_metadata", value: "INKFLIP-CANARY-METADATA-8C3" },
  { name: "canary_annotation", value: "INKFLIP-CANARY-ANNOTATION-9D4" },
  { name: "canary_doc_sha256", value: CANARY_SHA256, allowed_channels: ["downloads"] },
  { name: "pdf_b64_head", value: canaryBytes.subarray(0, 512).toString("base64") },
  { name: "amount_filename", value: "mapping-amount.pdf" },
  { name: "control_filename", value: "mapping-control.pdf" },
  { name: "amount_doc_sha256", value: AMOUNT_SHA256 },
  { name: "control_doc_sha256", value: CONTROL_SHA256 },
  { name: "geometry_filename", value: "geometry-90.pdf" },
  { name: "scan_filename", value: "scan-correct.pdf" },
];

type Violation = {
  marker: string;
  channel: string;
  where: string;
  snippet: string;
};

type Rec = {
  channel: string;
  method?: string;
  url: string;
  status?: number;
  data?: string;
  headers?: Record<string, string>;
};

type Capture = {
  label: string;
  records: Rec[];
  violations: Violation[];
  offline?: boolean;
  serverLogStart: number;
  serverLog: string[];
};

let server: Server;
let baseURL = "";
const accessLog: string[] = [];
let activeCapture: Capture | null = null;
let captureSeq = 0;

const SECURITY_HEADERS = {
  "Content-Security-Policy":
    "default-src 'none'; script-src 'self' 'wasm-unsafe-eval'; " +
    "worker-src 'self'; connect-src 'self'; img-src 'self' blob: data:; " +
    "font-src 'self' blob:; style-src 'self'; style-src-attr 'unsafe-inline'; " +
    "object-src 'none'; frame-src 'none'; base-uri 'none'; form-action 'none'; " +
    "frame-ancestors 'none'; manifest-src 'self'",
  "Referrer-Policy": "no-referrer",
  "X-Content-Type-Options": "nosniff",
  "Cross-Origin-Resource-Policy": "same-origin",
};

const MIME: Record<string, string> = {
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".mjs": "text/javascript; charset=utf-8",
  ".css": "text/css",
  ".json": "application/json",
  ".pdf": "application/pdf",
  ".wasm": "application/wasm",
  ".bcmap": "application/octet-stream",
  ".traineddata": "application/octet-stream",
  ".pfb": "application/octet-stream",
  ".ttf": "font/ttf",
  ".icc": "application/vnd.iccprofile",
  ".png": "image/png",
};

function ext(name: string): string {
  const i = name.lastIndexOf(".");
  return i >= 0 ? name.slice(i) : "";
}

/** Every spelling a marker could take on the wire (raw, percent, base64). */
function spellings(m: Marker): string[] {
  const out = [
    m.value,
    encodeURIComponent(m.value),
    Buffer.from(m.value, "utf8").toString("base64"),
  ];
  if (/^[0-9a-f]{64}$/.test(m.value)) {
    out.push(Buffer.from(m.value, "hex").toString("base64"));
  }
  return out.filter((v) => v.length >= 8);
}

/** Scan one captured carrier for every marker spelling. */
function scanInto(
  cap: Capture,
  channel: string,
  where: string,
  body: string | undefined | null,
): void {
  if (!body) return;
  for (const m of MARKERS) {
    for (const s of spellings(m)) {
      let at = body.indexOf(s);
      while (at >= 0) {
        cap.violations.push({
          marker: m.value,
          channel,
          where: `${where}@${at}`,
          snippet: body.slice(Math.max(0, at - 24), at + s.length + 24),
        });
        at = body.indexOf(s, at + 1);
      }
    }
  }
}

/** Attach request/response/failure/websocket/console listeners to a context. */
function armEgress(context: BrowserContext): void {
  context.on("request", (req) => {
    const rec: Rec = { channel: "requests", method: req.method(), url: req.url() };
    const post = req.postData();
    if (post !== null) rec.data = post;
    activeCapture?.records.push(rec);
  });
  context.on("response", (res) => {
    activeCapture?.records.push({
      channel: "responses",
      url: res.url(),
      status: res.status(),
      headers: res.headers(),
    });
  });
  context.on("requestfailed", (req) => {
    activeCapture?.records.push({
      channel: "failures",
      method: req.method(),
      url: req.url(),
      data: req.failure()?.errorText,
    });
  });
  context.on("websocket", (ws) => {
    activeCapture?.records.push({ channel: "websockets", url: ws.url() });
    ws.on("framesent", (f) => {
      const data = typeof f.payload === "string" ? f.payload : "";
      activeCapture?.records.push({ channel: "ws_frames_sent", url: ws.url(), data });
    });
    ws.on("framereceived", (f) => {
      const data = typeof f.payload === "string" ? f.payload : "";
      activeCapture?.records.push({ channel: "ws_frames_recv", url: ws.url(), data });
    });
  });
  context.on("console", (msg) => {
    activeCapture?.records.push({
      channel: "console",
      url: msg.location()?.url ?? "",
      data: `[${msg.type()}] ${msg.text()}`.slice(0, 4000),
    });
  });
  context.on("pageerror", (err) => {
    activeCapture?.records.push({
      channel: "page_errors",
      url: "",
      data: String(err).slice(0, 4000),
    });
  });
  context.on("dialog", (dlg) => {
    activeCapture?.records.push({
      channel: "dialogs",
      url: "",
      data: `${dlg.type()}:${dlg.message()}`,
    });
    void dlg.dismiss();
  });
}

/** Persist a downloaded artifact into the capture for scanning + evidence. */
async function recordDownload(cap: Capture, download: Download, destName: string): Promise<string> {
  const dir = join(CAPTURES, "downloads");
  mkdirSync(dir, { recursive: true });
  const dest = join(dir, `${String(captureSeq).padStart(2, "0")}-${destName}`);
  await download.saveAs(dest);
  const bytes = readFileSync(dest);
  cap.records.push({
    channel: "downloads",
    url: `download:${download.suggestedFilename()}`,
    data: bytes.toString("utf8").slice(0, 400_000),
    headers: {
      sha256: createHash("sha256").update(bytes).digest("hex"),
      bytes: String(bytes.length),
    },
  });
  return dest;
}

async function storageDump(page: Page): Promise<Rec[]> {
  const out: Rec[] = [];
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
    out.push({
      channel: "storage:indexeddb",
      url: d.name,
      data: `count=${d.count} keys=${d.keys.join(",")}`,
    });
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

function beginCapture(label: string, offline = false): Capture {
  const cap: Capture = {
    label,
    records: [],
    violations: [],
    offline,
    serverLogStart: accessLog.length,
    serverLog: [],
  };
  activeCapture = cap;
  return cap;
}

/** End the capture: storage dump, server log slice, then the marker scan. */
async function endCapture(
  page: Page,
  cap: Capture,
  opts: { skipStorage?: boolean } = {},
): Promise<Capture> {
  try {
    if (!opts.skipStorage) cap.records.push(...(await storageDump(page)));
  } catch {
    /* a destroyed execution context still leaves the network evidence */
  }
  cap.serverLog = accessLog.slice(cap.serverLogStart);
  // The actual scan — every record carrier plus the server-observed log.
  for (const rec of cap.records) {
    scanInto(cap, rec.channel, "url", rec.url);
    scanInto(cap, rec.channel, "data", rec.data);
    for (const [k, v] of Object.entries(rec.headers ?? {})) {
      scanInto(cap, rec.channel, `header:${k}`, v);
    }
  }
  scanInto(cap, "server_access_log", "line", cap.serverLog.join("\n"));
  mkdirSync(CAPTURES, { recursive: true });
  writeFileSync(
    join(CAPTURES, `${String(captureSeq++).padStart(2, "0")}-${cap.label}.json`),
    JSON.stringify(
      { ...cap, records: cap.records.map((r) => ({ ...r, data: r.data?.slice(0, 4000) })) },
      null,
      2,
    ),
  );
  if (activeCapture === cap) activeCapture = null;
  return cap;
}

/** Assert a finished capture carries zero disallowed canary material. */
function assertCaptureClean(cap: Capture): void {
  const nameFor = new Map(MARKERS.map((m) => [m.value, m.name]));
  for (const v of cap.violations) {
    const mk = MARKERS.find((m) => m.value === v.marker);
    if (mk?.allowed_channels?.includes(v.channel)) continue;
    expect.unreachable(
      `no-egress violation: marker ${nameFor.get(v.marker) ?? v.marker} seen in ${v.channel} at ${v.where}\n  ${v.snippet}`,
    );
  }
  // Transport sanity: no cross-origin request ever left the page.
  const remote = cap.records.filter(
    (r) =>
      r.channel === "requests" &&
      !r.url.startsWith("blob:") &&
      !r.url.startsWith("data:") &&
      new URL(r.url).origin !== baseURL,
  );
  expect(remote, `cross-origin requests: ${remote.map((r) => r.url).join(", ")}`).toEqual([]);
  if (cap.offline) {
    // The honest offline bound: the SERVER observed zero requests during the
    // leg. Browser HTTP cache may satisfy fixed same-origin assets — those
    // still produce request events but never reach the wire, so assert on
    // the access log plus zero failures plus the fixed-asset allowlist.
    expect(cap.serverLog, "offline leg: requests reached the server").toEqual([]);
    expect(
      cap.records.filter((r) => r.channel === "failures"),
      "offline leg: failed requests",
    ).toEqual([]);
    for (const r of cap.records.filter((r) => r.channel === "requests")) {
      const p = new URL(r.url).pathname;
      expect(
        p.startsWith("/assets/") || p.startsWith("/models/"),
        `offline request outside fixed assets: ${r.url}`,
      ).toBe(true);
    }
  }
}

/* ---------------- page-side helpers (real collaborators) ---------------- */

async function openMount(page: Page): Promise<void> {
  await page.goto(`${baseURL}/src/features/open/preview.html`);
  await page.waitForFunction(
    () => (window as never as Record<string, unknown>).__t08 !== undefined,
  );
}

/** Offer a real file through the T08 mount's real <input type=file>. */
async function offerFile(
  page: Page,
  name: string,
  bytes: Uint8Array,
  confirmReplace = false,
): Promise<void> {
  await page
    .locator("[data-testid=file-input]")
    .setInputFiles({ name, mimeType: "application/pdf", buffer: Buffer.from(bytes) });
  if (confirmReplace) {
    const dlg = page.locator("[role=dialog]");
    await expect(dlg).toBeVisible();
    await expect(dlg).toContainText("Open a different PDF?");
    await dlg.getByRole("button", { name: "Clear and open file" }).click();
  }
  await expect(page.locator("[data-testid=doc-label]")).toHaveText(name, { timeout: 30_000 });
}

async function harness(page: Page): Promise<void> {
  await page.goto(`${baseURL}/privacy.html`);
  await page.waitForFunction(
    () => (window as never as Record<string, unknown>).__t15 !== undefined,
    undefined,
    { timeout: 30_000 },
  );
}

/* ------------------------------ the gate ------------------------------- */

test.describe.configure({ mode: "serial" });
test.setTimeout(300_000);

test.beforeAll(async () => {
  rmSync(CAPTURES, { recursive: true, force: true });
  mkdirSync(CAPTURES, { recursive: true });

  // The harness lives outside apps/web and bun's isolated linker keeps app
  // deps under apps/web/node_modules — give plain node resolution a
  // gitignored node_modules of symlinks, exactly like the accepted T15
  // suite does, so imports resolve to the same realpaths the app uses.
  const shim = join(T15_HARNESS, "node_modules");
  rmSync(shim, { recursive: true, force: true });
  mkdirSync(shim, { recursive: true });
  for (const pkg of ["react", "react-dom", "pdfjs-dist", "tesseract.js"]) {
    symlinkSync(join(WEB, "node_modules", pkg), join(shim, pkg), "dir");
  }

  // Real application build — the pinned Vite production build, identical to
  // `bun run build:web`, plus the real T08 open / T22 import feature mounts.
  // Vite is resolved through its installed file URL (it is not resolvable
  // as a bare specifier from tests/, same approach as tests/privacy).
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
          open: join(WEB, "src", "features", "open", "preview.html"),
          import_: join(WEB, "src", "features", "import", "preview.html"),
        },
      },
    },
  });
  // Pass 2 — the test-owned privacy harness page, bundling the same
  // production packages through the same build pipeline.
  await vite.build({
    root: T15_HARNESS,
    configFile: join(WEB, "vite.config.ts"),
    logLevel: "warn",
    publicDir: false,
    build: {
      outDir: DIST,
      emptyOutDir: false,
      rollupOptions: { input: { privacy: join(T15_HARNESS, "privacy.html") } },
    },
  });

  const distRoot = resolve(DIST) + sep;
  server = createServer((req, res) => {
    const url = new URL(req.url ?? "/", "http://static.invalid");
    let pathname = decodeURIComponent(url.pathname);
    if (pathname === "/") pathname = "/index.html";
    accessLog.push(`${req.method} ${pathname}`);
    const headers = { ...SECURITY_HEADERS, "Cache-Control": "no-cache" };
    if (pathname === "/favicon.ico") {
      res.writeHead(204, headers).end();
      return;
    }
    const file = normalize(join(DIST, pathname));
    if (!file.startsWith(distRoot) || !existsSync(file) || file.endsWith(sep)) {
      res.writeHead(404, headers).end("not found");
      return;
    }
    let body: Buffer;
    try {
      body = readFileSync(file);
    } catch {
      res.writeHead(404, headers).end("not found");
      return;
    }
    res
      .writeHead(200, { ...headers, "Content-Type": MIME[ext(file)] ?? "application/octet-stream" })
      .end(body);
  });
  await new Promise<void>((r) => server.listen(0, "127.0.0.1", r));
  baseURL = `http://127.0.0.1:${(server.address() as { port: number }).port}`;
});

test.afterAll(async () => {
  await new Promise((r) => server.close(r));
  writeFileSync(join(CAPTURES, "server-access.log"), accessLog.join("\n") + "\n");
  // Marker digests only — never marker material (same rule as T15).
  writeFileSync(
    join(CAPTURES, "canary-manifest.json"),
    JSON.stringify(
      {
        documents: {
          canary: {
            filename: "network-canary-channels.pdf",
            sha256: CANARY_SHA256,
            byte_length: canaryBytes.length,
          },
          amount: {
            filename: "mapping-amount.pdf",
            sha256: AMOUNT_SHA256,
            byte_length: amountBytes.length,
          },
          control: {
            filename: "mapping-control.pdf",
            sha256: CONTROL_SHA256,
            byte_length: controlBytes.length,
          },
        },
        markers: MARKERS.map((m) => ({
          name: m.name,
          sha256: createHash("sha256").update(m.value, "utf8").digest("hex"),
          allowed_channels: m.allowed_channels ?? [],
        })),
        model_sha256: "7d4322bd2a7749724879683fc3912cb542f19906c83bcc1a52132556427170b2",
        limitations: [
          "App composition (T13) has not landed a unified own-file page: the gate drives the real built feature mounts (open/import), the test-owned T15 harness page, and the real app shell in sequence — the same production code paths the composed page calls.",
          "Browser automation cannot see every OS/browser channel; the release profile additionally needs a proxy/firewall capture per planning.",
          "Offline coverage means an already-loaded page with prepared assets; the site ships no service worker, so cold offline navigation is out of scope (asserted as a boundary, not a feature).",
        ],
      },
      null,
      2,
    ) + "\n",
  );
  rmSync(DIST, { recursive: true, force: true });
});

/* ---- 1. own-file open → read → region → plan → feed → cancel → replace -- */

test("G1 leg 1: real own-file open/read/select/plan/cancel/replace", async ({ browser }) => {
  const ctx = await browser.newContext({ acceptDownloads: true });
  armEgress(ctx);
  const page = await ctx.newPage();

  const cap = beginCapture("open-journey");

  // The real app shell landing — the shipped index, not a demo page.
  await page.goto(baseURL);
  await expect(page.locator("h1")).toContainText("Your PDF can look right");

  await openMount(page);

  // Interesting own-file (F01): text layer reads $1,000 while the raster
  // paints $100 — the family's whole point.
  await offerFile(page, "mapping-amount.pdf", amountBytes);
  const amountMeta = await page.locator("[data-testid=doc-meta]").innerText();
  expect(amountMeta).toContain("1 page");
  expect(await page.evaluate(() => (window as any).__t08.controller.currentDocument.sha256)).toBe(
    AMOUNT_SHA256,
  );

  // Real PDF.js native-text extraction through the mounted adapter — the
  // same plan/extract calls a dispatched worker makes.
  const amountText = await page.evaluate(async () => {
    const t08 = (window as any).__t08;
    const handle = t08.controller.currentHandle;
    const checks = t08.adapter.plan(handle, { pages: [0], capabilities: ["native_text"] });
    const emitted: unknown[] = [];
    const outcome = await t08.adapter.extract(handle, checks[0], (chunk: unknown[]) =>
      emitted.push(...chunk),
    );
    return {
      checkId: checks[0].id,
      status: outcome.result.status,
      occurrences: emitted as {
        id: string;
        raw_text: string;
        normalized_text: string;
        geometry: { precision: string; polygon: [number, number][] | null };
      }[],
    };
  });
  expect(amountText.checkId).toBe("chk_p0_native_text");
  expect(amountText.status).toBe("completed");
  const amountOcc = amountText.occurrences.find(
    (o) => o.normalized_text === "$1,000" || o.raw_text === "$1,000",
  );
  expect(amountOcc, "real extracted occurrences must contain the amount").toBeTruthy();
  expect(amountOcc!.geometry.polygon!.length).toBeGreaterThan(2);
  // pdf.js TextItem extents are honestly marked `estimated` — the adapter
  // never claims `exact` for font-derived boxes.
  expect(amountOcc!.geometry.precision).toBe("estimated");

  // Real rasterization + unsupported + cancelled capability paths.
  const misc = await page.evaluate(async () => {
    const t08 = (window as any).__t08;
    const handle = t08.controller.currentHandle;
    const adapter = t08.adapter;
    const render = adapter.plan(handle, { pages: [0], capabilities: ["render"] });
    const rOut = await adapter.extract(
      handle,
      render[0],
      () => undefined,
      {},
      { renderScalePxPerPt: 2 },
    );
    const un = adapter.plan(handle, { pages: [0], capabilities: ["forms"] });
    const uOut = await adapter.extract(handle, un[0], () => undefined);
    const ac = new AbortController();
    ac.abort();
    const text = adapter.plan(handle, { pages: [0], capabilities: ["native_text"] });
    const cOut = await adapter.extract(handle, text[0], () => undefined, { signal: ac.signal });
    return {
      render: {
        status: rOut.result.status,
        w: rOut.raster?.widthPx,
        h: rOut.raster?.heightPx,
        scale: rOut.raster?.scalePxPerPt,
        verified: rOut.raster?.viewportVerified,
      },
      unsupported: { status: uOut.result.status, reason: uOut.result.reason },
      cancelled: { status: cOut.result.status, reason: cOut.result.reason },
    };
  });
  expect(misc.render.status).toBe("completed");
  expect(misc.render.w).toBeGreaterThan(0);
  expect(misc.render.h).toBeGreaterThan(0);
  expect(misc.render.scale).toBeCloseTo(2, 5);
  expect(misc.render.verified).toBe(true);
  expect(misc.unsupported.status).toBe("unsupported");
  expect(misc.unsupported.reason).toContain("unsupported");
  expect(misc.cancelled.status).toBe("cancelled");
  expect(misc.cancelled.reason).toBe("user_cancel");

  // Region selection through the real numeric commit path — bounds derived
  // from the REAL extracted $1,000 polygon so the region genuinely contains
  // the finding (canonical page space, top-left origin, 520×400 pt page).
  const xs = amountOcc!.geometry.polygon!.map((p) => p[0]);
  const ys = amountOcc!.geometry.polygon!.map((p) => p[1]);
  const region = {
    x0: Math.max(0, Math.floor(Math.min(...xs)) - 10),
    y0: Math.max(0, Math.floor(Math.min(...ys)) - 10),
    x1: Math.min(520, Math.ceil(Math.max(...xs)) + 10),
    y1: Math.min(400, Math.ceil(Math.max(...ys)) + 10),
  };
  await page.locator("[data-testid=region-x0]").fill(String(region.x0));
  await page.locator("[data-testid=region-y0]").fill(String(region.y0));
  await page.locator("[data-testid=region-x1]").fill(String(region.x1));
  await page.locator("[data-testid=region-y1]").fill(String(region.y1));
  await page.locator("[data-testid=region-apply]").click();
  await expect(page.locator("[data-testid=region-committed]")).toContainText(
    `Region on page 1: ${region.x0}, ${region.y0}, ${region.x1}, ${region.y1} pt`,
  );

  // The real run plan: native_text + render + ocr, with the committed
  // region bound to exactly the OCR check.
  await page.locator("[data-testid=start-run]").click();
  await expect(page.locator("[data-testid=plan]")).toBeVisible();
  expect(await page.evaluate(() => (window as any).__t08.coordinator.snapshot().fileState)).toBe(
    "running",
  );
  const planChecks = await page.locator("[data-testid=plan-checks] li").evaluateAll((els) =>
    els.map((el) => ({
      id: el.getAttribute("data-check-id"),
      capability: el.getAttribute("data-capability"),
      region: el.getAttribute("data-region"),
    })),
  );
  expect(planChecks.map((c) => c.capability).sort()).toEqual(
    ["native_text", "ocr", "render"].sort(),
  );
  const regionBound = planChecks.filter((c) => c.region);
  expect(regionBound.length).toBe(1); // exactly the OCR check binds the region
  expect(regionBound[0]!.capability).toBe("ocr");
  expect(regionBound[0]!.region).toMatch(/^region_p0_\d+$/);
  // Only dependency-free checks dispatch immediately: native_text and render.
  // The OCR check is gated on the render check for the same page
  // (deriveDependencies) and dispatches once that raster settles.
  const dispatched = await page.locator("[data-testid=plan-dispatched] li").allInnerTexts();
  expect(dispatched.length).toBe(2);
  expect(dispatched.join(" ")).toContain("chk_p0_native_text");
  expect(dispatched.join(" ")).toContain("chk_p0_render");

  // Feed the run's REAL results through the coordinator's admission path —
  // real pdf.js output for native_text + render, and one unrelated failure
  // on OCR: independent completed results must be retained under a partial.
  const fed = await page.evaluate(async () => {
    const t08 = (window as any).__t08;
    const { coordinator, adapter, MessageFactory } = t08;
    const snap = coordinator.snapshot();
    const gen = snap.generation;
    const sha = snap.documentSha256;
    const runKey = snap.run.runKey;
    const lis = [...document.querySelectorAll("[data-testid=plan-dispatched] li")].map(
      (li) => li.textContent ?? "",
    );
    const jobFor = (checkId: string) =>
      lis
        .find((t) => t.includes(`dispatched ${checkId} on `))
        ?.split(" on ")[1]
        ?.trim() ??
      coordinator
        .drainOutbox()
        .find(
          (i: { type: string; checkId?: string }) => i.type === "dispatch" && i.checkId === checkId,
        )?.jobId ??
      null;
    const handle = t08.controller.currentHandle;
    const res: { msg: string; ok: boolean; code?: string }[] = [];
    for (const chk of snap.run.checks) {
      const jobId = jobFor(chk.id);
      if (!jobId) {
        res.push({ msg: `${chk.id}:no-dispatch`, ok: false });
        continue;
      }
      const mf = new MessageFactory({ generation: gen, documentSha256: sha, runKey, jobId });
      if (chk.capability === "native_text" || chk.capability === "render") {
        // Re-plan the same check id through the adapter so the plan carries
        // the real reader bindings (reader_ids) the extract path requires.
        const real = adapter.plan(handle, {
          pages: [chk.pageIndex],
          capabilities: [chk.capability],
        })[0];
        const emitted: unknown[] = [];
        await adapter.extract(handle, real, (chunk: unknown[]) => emitted.push(...chunk));
        for (let i = 0; i < emitted.length; i += 256) {
          res.push({
            msg: `chunk:${chk.id}:${i}`,
            ...coordinator.receive(mf.chunk(chk.id, emitted.slice(i, i + 256))),
          });
        }
        res.push({
          msg: `terminal:${chk.id}`,
          ...coordinator.receive(mf.checkTerminal(chk.id, "completed")),
        });
      } else {
        // `unsupported` is a never-retry reason — the check settles
        // terminally in one step (a transient reason would redispatch).
        res.push({
          msg: `terminal:${chk.id}`,
          ...coordinator.receive(mf.checkTerminal(chk.id, "failed", "unsupported")),
        });
      }
    }
    const after = coordinator.snapshot();
    return {
      res,
      status: after.run?.status,
      occurrences: after.occurrences.length,
      checks: after.run?.checks.map((c) => ({ id: c.id, status: c.status })),
    };
  });
  for (const r of fed.res) expect(r.ok, `${r.msg} → ${r.code}`).toBe(true);
  expect(fed.status).toBe("partial");
  expect(fed.occurrences).toBeGreaterThan(0); // retained under unrelated failure

  // Cancel a fresh generation: start a second run on the same document,
  // cancel it, and capture a delayed terminal stamped with THAT run's
  // generation — it would have been admitted during the run.
  const cancelProof = await page.evaluate(async () => {
    const t08 = (window as any).__t08;
    const { coordinator, adapter, MessageFactory } = t08;
    coordinator.prepareNewRun();
    const runKey = "b".repeat(64);
    const checks = adapter.plan(t08.controller.currentHandle, {
      pages: [0],
      capabilities: ["native_text"],
    });
    coordinator.startRun({ runKey, checks, selectedPagesTotal: 1 });
    const liveGen = coordinator.snapshot().generation;
    const receipt = coordinator.requestCancel();
    const snap = coordinator.snapshot();
    const stale = new MessageFactory({
      generation: liveGen,
      documentSha256: snap.documentSha256,
      runKey,
      jobId: "j_delayed_a",
    }).checkTerminal(checks[0].id, "completed");
    return {
      fileState: snap.fileState,
      generation: snap.generation,
      liveGen,
      cleanupFailures: receipt.cleanupFailures.length,
      cancelledChecks: snap.run?.checks.filter(
        (c: { status: string | null }) => c.status === "cancelled",
      ).length,
      staleMessage: stale,
    };
  });
  expect(cancelProof.fileState).toBe("cancelled");
  expect(cancelProof.generation).toBe(cancelProof.liveGen + 1);
  expect(cancelProof.cleanupFailures).toBe(0);
  expect(cancelProof.cancelledChecks).toBe(1);

  // Renamed own-file → identical bytes → identical identity + reading.
  await offerFile(page, "renamed-own-file.pdf", amountBytes, true);
  const renameProbe = await page.evaluate(async () => {
    const t08 = (window as any).__t08;
    const handle = t08.controller.currentHandle;
    const checks = t08.adapter.plan(handle, { pages: [0], capabilities: ["native_text"] });
    const emitted: { raw_text: string }[] = [];
    await t08.adapter.extract(handle, checks[0], (chunk: { raw_text: string }[]) =>
      emitted.push(...chunk),
    );
    return { sha: t08.controller.currentDocument.sha256, texts: emitted.map((o) => o.raw_text) };
  });
  expect(renameProbe.sha).toBe(AMOUNT_SHA256); // byte identity, not filename
  expect(renameProbe.texts).toContain("$1,000");

  // Clean control (F01 sibling): the same painted $100 with an honest text
  // layer — extraction reads $100, and never the mapped $1,000.
  await offerFile(page, "mapping-control.pdf", controlBytes, true);
  const controlProbe = await page.evaluate(async () => {
    const t08 = (window as any).__t08;
    const handle = t08.controller.currentHandle;
    const checks = t08.adapter.plan(handle, { pages: [0], capabilities: ["native_text"] });
    const emitted: { raw_text: string; normalized_text: string }[] = [];
    await t08.adapter.extract(
      handle,
      checks[0],
      (chunk: { raw_text: string; normalized_text: string }[]) => emitted.push(...chunk),
    );
    return { sha: t08.controller.currentDocument.sha256, texts: emitted.map((o) => o.raw_text) };
  });
  expect(controlProbe.sha).toBe(CONTROL_SHA256);
  expect(controlProbe.texts).toContain("$100");
  expect(controlProbe.texts).not.toContain("$1,000");

  // Replace control (A) with the canary (B) — the delayed A-run terminal
  // must be rejected stale_generation, and B must show none of A's data.
  await offerFile(page, "network-canary-channels.pdf", canaryBytes, true);
  const staleResult = await page.evaluate(async (msg: unknown) => {
    const t08 = (window as any).__t08;
    const { coordinator, adapter } = t08;
    const r = coordinator.receive(msg);
    const handle = t08.controller.currentHandle;
    const checks = adapter.plan(handle, { pages: [0], capabilities: ["native_text"] });
    const emitted: { raw_text: string }[] = [];
    await adapter.extract(handle, checks[0], (chunk: { raw_text: string }[]) =>
      emitted.push(...chunk),
    );
    return {
      rejected: r,
      texts: emitted.map((o) => o.raw_text),
      sha: t08.controller.currentDocument.sha256,
      fileState: coordinator.snapshot().fileState,
      occurrences: coordinator.snapshot().occurrences.length,
    };
  }, cancelProof.staleMessage);
  expect(staleResult.rejected.ok).toBe(false);
  expect(staleResult.rejected.code).toBe("stale_generation");
  expect(staleResult.texts).toContain("INKFLIP-CANARY-TEXT-7B2");
  expect(staleResult.texts).not.toContain("$1,000"); // B never shows A's data
  expect(staleResult.texts).not.toContain("$100");
  expect(staleResult.sha).toBe(CANARY_SHA256);
  expect(staleResult.occurrences).toBe(0); // no run retained anything for B

  await endCapture(page, cap);
  assertCaptureClean(cap);
  await ctx.close();
});

/* ---- 2. real OCR + rotated/scan geometry on the privacy harness --------- */

test("G1 leg 2: OCR + source geometry on the real reader stack", async ({ browser }) => {
  const ctx = await browser.newContext({ acceptDownloads: true });
  armEgress(ctx);
  const page = await ctx.newPage();
  const cap = beginCapture("geometry-ocr");
  await harness(page);

  // Canary document through the real adapter: contract pages, native text,
  // two raster scales — all from the real bytes.
  const canary = await page.evaluate(async (arr: number[]) => {
    const t15 = (window as any).__t15;
    const opened = await t15.openDoc(arr);
    if (!opened.ok) return { step: "open", opened };
    const docId = opened.value.docId;
    const pages = await t15.contractPages(docId);
    if (!pages.ok) return { step: "pages", pages };
    const text = await t15.extractText(docId, 0, "region_p0_canary");
    if (!text.ok) return { step: "text", text };
    const r1 = await t15.rasterize(docId, 0, 1);
    const r2 = await t15.rasterize(docId, 0, 2);
    return {
      step: "done",
      doc: opened.value,
      pages: pages.value,
      text: text.value,
      r1: r1.ok ? r1.value : r1,
      r2: r2.ok ? r2.value : r2,
    };
  }, Array.from(canaryBytes));
  expect(canary.step).toBe("done");
  const canaryDoc = (canary as any).doc as { docId: string; sha256: string; pageCount: number };
  expect(canaryDoc.sha256).toBe(CANARY_SHA256);
  const canaryPages = (canary as any).pages as {
    pages: { canonical_size_pt: [number, number]; rotation: number }[];
  };
  expect(canaryPages.pages[0]!.canonical_size_pt).toEqual([320, 240]);
  const canaryEmitted = (canary as any).text.emitted as {
    id: string;
    raw_text: string;
    geometry: { precision: string; polygon: [number, number][] };
  }[];
  const canaryOcc = canaryEmitted.find((o) => o.raw_text.includes("INKFLIP-CANARY-TEXT-7B2"));
  expect(canaryOcc).toBeTruthy();
  expect(canaryOcc!.geometry.precision).toBe("estimated");
  for (const [px, py] of canaryOcc!.geometry.polygon) {
    expect(px).toBeGreaterThanOrEqual(0);
    expect(py).toBeGreaterThanOrEqual(0);
    expect(px).toBeLessThanOrEqual(320);
    expect(py).toBeLessThanOrEqual(240);
  }
  const r1v = (canary as any).r1 as {
    widthPx: number;
    heightPx: number;
    scalePxPerPt: number;
    pixelSha256: string;
  };
  const r2v = (canary as any).r2 as { widthPx: number; heightPx: number };
  expect(r1v.widthPx).toBeGreaterThan(0);
  expect(r2v.widthPx).toBe(r1v.widthPx * 2);
  expect(r2v.heightPx).toBe(r1v.heightPx * 2);
  MARKERS.push({ name: "raster_sha256", value: r1v.pixelSha256 });

  // Real Tesseract worker: cold prepare (staged same-origin fetch →
  // verified), real OCR of the same canonical region — both readings bound
  // to one region.
  const ocr = await page.evaluate(
    async (args: { docId: string; sha: string; polygon: [number, number][] }) => {
      const t15 = (window as any).__t15;
      const reader = t15.makeOcrReader(args.docId, "g1-run-leg2");
      const prep = await t15.ocrPrepare(reader.readerId);
      if (!prep.ok) return { step: "prepare", prep };
      const opened = await t15.ocrOpen(reader.readerId, args.sha, 1);
      if (!opened.ok) return { step: "open", opened };
      const plan = await t15.ocrPlan(reader.readerId, [
        {
          pageIndex: 0,
          purpose: "region",
          region: { id: "region_p0_canary", polygon: args.polygon, label: "canary region" },
        },
      ]);
      if (!plan.ok) return { step: "plan", plan };
      const out = await t15.ocrExtract(reader.readerId, plan.value[0].id);
      if (!out.ok) return { step: "extract", out };
      return {
        step: "done",
        provenance: prep.value.provenance,
        state: prep.value.state,
        modelSha: out.value.output.model.sha256,
        modelProvenance: out.value.output.model.provenance,
        status: out.value.output.check.status,
        occCount: out.value.output.occurrences.length,
        words: out.value.output.occurrences
          .map((o: { raw_text: string }) => o.raw_text)
          .slice(0, 8),
        precision: out.value.output.occurrences[0]?.geometry.precision,
        polyInside: out.value.output.occurrences.every(
          (o: { geometry: { polygon: [number, number][] | null } }) =>
            (o.geometry.polygon ?? []).every(([x, y]) => x >= 0 && y >= 0 && x <= 320 && y <= 240),
        ),
      };
    },
    { docId: canaryDoc.docId, sha: CANARY_SHA256, polygon: canaryOcc!.geometry.polygon },
  );
  expect(ocr.step).toBe("done");
  expect(ocr.state).toBe("ready_memory");
  expect(ocr.provenance).toBe("network"); // cold leg fetched the staged model once
  const modelFetches = cap.records.filter(
    (r) => r.channel === "requests" && r.url.includes("/models/tessdata-fast-eng/"),
  );
  expect(modelFetches.length).toBe(1);
  expect(ocr.modelSha).toBe("7d4322bd2a7749724879683fc3912cb542f19906c83bcc1a52132556427170b2");
  expect(ocr.status).toBe("completed");
  expect(ocr.occCount).toBeGreaterThan(0);
  // OCR boxes are always `estimated` (COORDINATES.md).
  expect(ocr.precision).toBe("estimated");
  expect(ocr.polyInside).toBe(true);

  // F07: rotated + UserUnit page — canonical extent carries the physical
  // size, the rotation flag is recorded, and the raster comes out portrait
  // from a landscape media box.
  const geo = await page.evaluate(async (arr: number[]) => {
    const t15 = (window as any).__t15;
    const opened = await t15.openDoc(arr);
    if (!opened.ok) return { step: "open", opened };
    const docId = opened.value.docId;
    const pages = await t15.contractPages(docId);
    if (!pages.ok) return { step: "pages", pages };
    const text = await t15.extractText(docId, 0, "region_p0_geo");
    if (!text.ok) return { step: "text", text };
    const raster = await t15.rasterize(docId, 0, 1);
    return {
      step: "done",
      pages: pages.value,
      text: text.value,
      raster: raster.ok ? raster.value : raster,
    };
  }, Array.from(geoBytes));
  expect(geo.step).toBe("done");
  const geoPage = (geo as any).pages.pages[0] as {
    canonical_size_pt: [number, number];
    rotation: number;
    user_unit: number;
  };
  expect(geoPage.rotation).toBe(90);
  expect(geoPage.user_unit).toBe(2);
  // CropBox [20 40 500 390] × UserUnit 2 → 960×700 pt canonical extent.
  expect(geoPage.canonical_size_pt).toEqual([960, 700]);
  const geoEmitted = (geo as any).text.emitted as {
    geometry: { polygon: [number, number][] | null };
  }[];
  expect(geoEmitted.length).toBeGreaterThan(0);
  for (const o of geoEmitted) {
    for (const [px, py] of o.geometry.polygon ?? []) {
      expect(px).toBeGreaterThanOrEqual(0);
      expect(py).toBeGreaterThanOrEqual(0);
      expect(px).toBeLessThanOrEqual(960);
      expect(py).toBeLessThanOrEqual(700);
    }
  }
  const geoRaster = (geo as any).raster as { widthPx: number; heightPx: number };
  // /Rotate 90 turns the 960×700 canonical page into a portrait raster.
  expect(geoRaster.heightPx).toBeGreaterThan(geoRaster.widthPx);

  // F03 (scan-correct): invisible text layer over the owned bitmap scan —
  // must complete with real occurrences and no capability alarm.
  const scan = await page.evaluate(async (arr: number[]) => {
    const t15 = (window as any).__t15;
    const opened = await t15.openDoc(arr);
    if (!opened.ok) return { step: "open", opened };
    const text = await t15.extractText(opened.value.docId, 0, "region_p0_scan");
    if (!text.ok) return { step: "text", text };
    return {
      step: "done",
      status: text.value.result.status,
      texts: text.value.emitted.map((o: { raw_text: string }) => o.raw_text),
      precision: text.value.emitted[0]?.geometry.precision,
    };
  }, Array.from(scanBytes));
  expect(scan.step).toBe("done");
  expect(scan.status).toBe("completed");
  expect(scan.precision).toBe("estimated");
  for (const w of ["QUARTERLY", "INVOICE", "$100.00", "PAGE"]) {
    expect(scan.texts!.join(" "), `scan text layer must contain ${w}`).toContain(w);
  }

  // UI-level rotated region commit through the real open mount: numeric
  // entry in canonical space on the rotated page.
  await openMount(page);
  await offerFile(page, "geometry-90.pdf", geoBytes);
  await page.locator("[data-testid=region-x0]").fill("10");
  await page.locator("[data-testid=region-y0]").fill("10");
  await page.locator("[data-testid=region-x1]").fill("200");
  await page.locator("[data-testid=region-y1]").fill("200");
  await page.locator("[data-testid=region-apply]").click();
  const committed = await page.locator("[data-testid=region-committed]").innerText();
  expect(committed).toContain("10");
  expect(committed).toContain("200");
  expect(committed).toContain("Region on page 1");

  await endCapture(page, cap);
  assertCaptureClean(cap);
  await ctx.close();
});

/* ---- 3. selected export → privacy preview → local reopen → offline ------ */

test("G1 leg 3: selected export → local reopen → offline OCR", async ({ browser }) => {
  const ctx = await browser.newContext({ acceptDownloads: true });
  armEgress(ctx);
  const page = await ctx.newPage();
  const cap = beginCapture("export-reopen");
  await harness(page);

  // Rebuild the canary run inside the export context — real open, text,
  // raster, OCR — then assemble + seal the report in-page (same shape the
  // accepted T15 suite seals) and mount the REAL T16 ExportPanel.
  const run = await page.evaluate(
    async (args: { bytes: number[] }) => {
      const t15 = (window as any).__t15;
      const opened = await t15.openDoc(args.bytes);
      if (!opened.ok) return { step: "open", opened };
      const docId = opened.value.docId;
      const sha = opened.value.sha256;
      const pages = await t15.contractPages(docId);
      if (!pages.ok) return { step: "pages", pages };
      const text = await t15.extractText(docId, 0, "region_p0_canary");
      if (!text.ok) return { step: "text", text };
      const raster = await t15.rasterize(docId, 0, 1);
      if (!raster.ok) return { step: "raster", raster };
      const reader = t15.makeOcrReader(docId, "g1-run-leg3");
      const prep = await t15.ocrPrepare(reader.readerId);
      if (!prep.ok) return { step: "prepare", prep };
      const ocropen = await t15.ocrOpen(reader.readerId, sha, 1);
      if (!ocropen.ok) return { step: "ocr-open", ocropen };
      const occ = text.value.emitted.find((o: { raw_text: string }) =>
        o.raw_text.includes("INKFLIP-CANARY-TEXT-7B2"),
      );
      const plan = await t15.ocrPlan(reader.readerId, [
        {
          pageIndex: 0,
          purpose: "region",
          region: { id: "region_p0_canary", polygon: occ.geometry.polygon, label: "canary" },
        },
      ]);
      if (!plan.ok) return { step: "ocr-plan", plan };
      const ocrOut = await t15.ocrExtract(reader.readerId, plan.value[0].id);
      if (!ocrOut.ok) return { step: "ocr-extract", ocrOut };

      const rep = {
        kind: "report",
        schema_version: "1.0.0",
        report_id: "0".repeat(64),
        document: {
          sha256: sha,
          byte_length: args.bytes.length,
          page_count: 1,
          display_name: "network-canary-channels.pdf",
          source_asset_id: null,
        },
        readers: [t15.adapter.readers.text, t15.adapter.readers.render, ocrOut.value.output.reader],
        pages: pages.value.pages,
        transforms: [
          ...new Map(
            [
              ...pages.value.transforms,
              ...raster.value.transforms,
              ...ocrOut.value.output.transforms,
            ].map((t) => [t.id, t]),
          ).values(),
        ],
        occurrences: [...text.value.emitted, ...ocrOut.value.output.occurrences],
        findings: [
          {
            id: "f_canary",
            kind: "reading_difference",
            title: "Text-layer marker present on rendered page",
            explanation:
              "The named text reader and the OCR reader produced different raw strings for the same selected region; neither output alone establishes document truth.",
            page_index: 0,
            occurrence_ids: [occ.id, ocrOut.value.output.occurrences[0].id],
            check_ids: [text.value.plan.id, ocrOut.value.output.check.id],
            alignment: "page_level",
            region_id: "region_p0_canary",
            priority: "selected",
            basis: "Actual recorded reader outputs of the generated canary document.",
            limitations: ["Synthetic single-line canary text."],
          },
        ],
        annotations: [
          {
            id: "a_canary",
            finding_id: "f_canary",
            page_index: 0,
            text: "Both readings agree at this region.",
            author_label: "g1-gate",
            origin: "human_entered",
          },
        ],
        plan: {
          version: "1.0.0",
          selected_pages: [0],
          regions: [
            { id: "region_p0_canary", page_index: 0, geometry: occ.geometry, label: "canary" },
          ],
          checks: [text.value.plan, raster.value.plan, plan.value[0]],
          normalization_version: "scalar-whitespace-v1",
          alignment_version: "region-match-v1",
          profile: "desktop",
          budget: {
            max_raster_pixels: 4_000_000,
            max_run_ocr_pixels: 20_000_000,
            timeout_ms: 120_000,
            max_retries: 1,
          },
        },
        checks: [text.value.result, raster.value.check, ocrOut.value.output.check],
        execution: {
          execution_id: crypto.randomUUID(),
          run_key: "0".repeat(64),
          status: "complete",
          started_at: new Date().toISOString(),
          duration_ms: 1,
          environment: "Chromium (Playwright) · g1 gate",
          result_origin: "live",
          errors: [],
        },
        export: {
          mode: "evidence",
          scope: "selection",
          included: [],
          omissions: [],
          replay: "requires_original",
          origin_report_id: null,
        },
        assets: [],
        limitations: [
          "G1 gate: report assembled in-page from the actual pdf.js/tesseract readings of the canary document.",
        ],
      };
      const report = t15.seal(rep);
      await t15.showExportPanel(report, args.bytes);
      return {
        step: "done",
        reportId: report.report_id,
        runKey: report.execution.run_key,
        report,
        prepProvenance: prep.value.provenance,
      };
    },
    { bytes: Array.from(canaryBytes) },
  );
  expect(run.step).toBe("done");
  MARKERS.push(
    { name: "report_id", value: run.reportId!, allowed_channels: ["downloads"] },
    { name: "run_key", value: run.runKey!, allowed_channels: ["downloads"] },
  );

  // Export preview: the disclosure panel itself is a privacy gate — the
  // real copy asserts selected scope and no source PDF.
  await expect(page.getByText("Preview what you will export")).toBeVisible();
  await expect(page.getByText("Selected evidence")).toBeVisible();
  await expect(page.getByText(/Original PDF not included/)).toBeVisible();
  for (const label of [
    "Include the original PDF",
    "Include original filename",
    "Include my notes",
  ]) {
    await expect(page.getByLabel(label)).not.toBeChecked();
  }
  await expect(page.getByText("Findings")).toBeVisible();

  // JSON download: real browser download of the selected projection.
  const dlJson = page.waitForEvent("download");
  await page.getByRole("button", { name: "Download portable JSON" }).click();
  const jsonDl = await dlJson;
  const jsonPath = await recordDownload(cap, jsonDl, "export.inkflip-report.json");
  const exported = JSON.parse(readFileSync(jsonPath, "utf8"));
  expect(exported.document.display_name).toBeNull(); // filename opt-in was off
  expect(exported.document.source_asset_id).toBeNull(); // source opt-in was off
  expect(exported.annotations ?? []).toEqual([]); // notes opt-in was off
  const purposes = (exported.assets ?? []).map((a: { purpose: string }) => a.purpose);
  expect(purposes).not.toContain("source_pdf");
  expect((exported.findings ?? []).length).toBe(1);
  const citedIds = new Set((exported.findings[0].occurrence_ids ?? []) as string[]);
  for (const o of exported.occurrences ?? []) {
    expect(citedIds.has(o.id), `occurrence ${o.id} must be cited`).toBe(true);
  }
  expect(exported.document.sha256).toBe(CANARY_SHA256);

  // HTML download: human-readable inspection, self-contained.
  const dlHtml = page.waitForEvent("download");
  await page.getByRole("button", { name: "Download readable HTML" }).click();
  const htmlDl = await dlHtml;
  const htmlPath = await recordDownload(cap, htmlDl, "export.inkflip-report.html");
  const htmlBody = readFileSync(htmlPath, "utf8");
  expect(htmlBody).toContain("Text-layer marker present on rendered page");
  expect(htmlBody).not.toContain("<script");
  expect(htmlBody).not.toMatch(/https?:\/\//);

  // Local reopen through the real T22 import mount — same file input path.
  await page.goto(`${baseURL}/src/features/import/preview.html`);
  await page.waitForFunction(
    () => (window as never as Record<string, unknown>).__t22 !== undefined,
    undefined,
    { timeout: 30_000 },
  );
  const exportJsonBytes = readFileSync(jsonPath);
  await page
    .locator("[data-testid=import-file-input]")
    .setInputFiles({
      name: jsonDl.suggestedFilename(),
      mimeType: "application/json",
      buffer: exportJsonBytes,
    });
  await expect(page.locator("[data-testid=import-report]")).toBeVisible({ timeout: 30_000 });
  await expect(page.locator("[data-testid=finding-f_canary]")).toContainText(
    "Text-layer marker present on rendered page",
  );
  await expect(page.locator("[data-testid=source-missing]")).toContainText(
    "original PDF is not included",
  );
  await expect(page.locator("[data-testid=replay-state]")).toContainText(
    "replay requires the matching original",
  );

  // Replay limitations, asserted through the real T22 import engine.
  const replay = await page.evaluate(
    async (args: { report: number[]; src: number[] }) => {
      const t22 = (window as any).__t22;
      const opened = t22.engine.openReport(Uint8Array.from(args.report));
      if (!opened.ok) return { step: "open", opened };
      const availability = t22.engine.readerAvailability(opened.imported.report, t22.installed);
      const view = t22.engine.replayView(opened.imported, availability, false);
      const src = Uint8Array.from(args.src);
      const match = t22.engine.verifySource(opened.imported.report, src);
      const wrong = t22.engine.verifySource(
        opened.imported.report,
        Uint8Array.from([0x25, 0x50, 0x44, 0x46, 0x00]),
      );
      return {
        step: "done",
        sourceKind: opened.imported.source.kind,
        viewSource: view.source,
        ready: view.ready,
        readersMissing: view.readersMissing,
        match,
        wrong,
      };
    },
    { report: Array.from(exportJsonBytes), src: Array.from(canaryBytes) },
  );
  expect(replay.step).toBe("done");
  expect(replay.sourceKind).toBe("required"); // source PDF absent from export
  expect(replay.viewSource).toBe("missing"); // until the user attaches bytes
  expect(replay.ready).toBe(false); // replay impossible: no source + the OCR reader is not installed
  expect((replay.match as { ok: boolean }).ok).toBe(true); // matching local bytes verify
  expect((replay.wrong as { ok: boolean }).ok).toBe(false); // wrong bytes rejected

  // Reopen through the real main-app shell (landing → workspace import).
  await page.goto(baseURL);
  await page.locator("#btn-open-report").click();
  await expect(page).toHaveURL(/#\/workspace/);
  await page
    .locator("#input-import-report")
    .setInputFiles({
      name: "reopened.inkflip-report.json",
      mimeType: "application/json",
      buffer: exportJsonBytes,
    });
  await expect(page.locator("#finding-item-f_canary")).toContainText(
    "Text-layer marker present on rendered page",
  );
  await expect(page.locator("#evidence-slip")).toContainText(
    "Text-layer marker present on rendered page",
  );

  await endCapture(page, cap);
  // The downloads legitimately contain the report id/run key/canary text —
  // whitelisted via allowed_channels; every other channel must be clean.
  assertCaptureClean(cap);

  // Cache-warm + offline OCR: a second page in the SAME context reuses the
  // verified IndexedDB model slot (zero model fetches), then the prepared
  // reader keeps extracting with ALL network blocked on the live page.
  const warm = await ctx.newPage();
  const capWarm = beginCapture("cache-warm-ocr");
  await harness(warm);
  const warmPrep = await warm.evaluate(
    async (args: { bytes: number[] }) => {
      const t15 = (window as any).__t15;
      const opened = await t15.openDoc(args.bytes);
      if (!opened.ok) return { step: "open", opened };
      const docId = opened.value.docId;
      const text = await t15.extractText(docId, 0, "region_p0_warm");
      if (!text.ok) return { step: "text", text };
      const raster = await t15.rasterize(docId, 0, 1);
      if (!raster.ok) return { step: "raster", raster };
      const reader = t15.makeOcrReader(docId, "g1-run-warm");
      const prep = await t15.ocrPrepare(reader.readerId);
      if (!prep.ok) return { step: "prepare", prep };
      const ocropen = await t15.ocrOpen(reader.readerId, opened.value.sha256, 1);
      if (!ocropen.ok) return { step: "ocr-open", ocropen };
      const occ = text.value.emitted.find((o: { raw_text: string }) =>
        o.raw_text.includes("INKFLIP-CANARY-TEXT-7B2"),
      );
      const plan = await t15.ocrPlan(reader.readerId, [
        {
          pageIndex: 0,
          purpose: "region",
          region: { id: "region_p0_warm", polygon: occ.geometry.polygon, label: "warm" },
        },
      ]);
      if (!plan.ok) return { step: "plan", plan };
      return {
        step: "done",
        provenance: prep.value.provenance,
        state: prep.value.state,
        readerId: reader.readerId,
        checkId: plan.value[0].id,
      };
    },
    { bytes: Array.from(canaryBytes) },
  );
  expect(warmPrep.step).toBe("done");
  expect(warmPrep.provenance).toBe("cache"); // verified IDB slot — no fetch
  expect(warmPrep.state).toBe("ready_cached");
  const warmModelFetches = capWarm.records.filter(
    (r) => r.channel === "requests" && r.url.includes("/models/tessdata-fast-eng/"),
  );
  expect(warmModelFetches, "warm prepare must not refetch the model").toEqual([]);
  await endCapture(warm, capWarm);
  assertCaptureClean(capWarm);

  const capOff = beginCapture("offline-warm", true);
  await ctx.setOffline(true);
  try {
    const offline = await warm.evaluate(
      async (args: { readerId: string; checkId: string }) => {
        const t15 = (window as any).__t15;
        const out = await t15.ocrExtract(args.readerId, args.checkId);
        if (!out.ok) return { step: "extract", out };
        return {
          step: "done",
          status: out.value.output.check.status,
          occ: out.value.output.occurrences.length,
          provenance: out.value.output.model.provenance,
          words: out.value.output.occurrences
            .map((o: { raw_text: string }) => o.raw_text)
            .slice(0, 6),
        };
      },
      { readerId: warmPrep.readerId!, checkId: warmPrep.checkId! },
    );
    expect(offline.step).toBe("done");
    expect(offline.status).toBe("completed");
    expect(offline.occ).toBeGreaterThan(0);
    expect(offline.provenance).toBe("memory"); // resident model — no network
  } finally {
    await ctx.setOffline(false);
  }
  await endCapture(warm, capOff);
  assertCaptureClean(capOff);
  await ctx.close();
});
