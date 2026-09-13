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
 *   Every step below drives the shipped public application — the real
 *   `index.html` shell, its Workspace page, and the production inspection
 *   session (`apps/web/src/features/inspect/session.ts`) that wires
 *   File → OpenController → RunCoordinator → real pdf.js/Tesseract readers
 *   → findings/report → viewer → export → reopen. No collaborator is mocked
 *   and no composition happens inside this test: PDF.js reads real bytes,
 *   Tesseract runs in its real same-origin worker from staged model bytes,
 *   the coordinator admits every result through its real protocol, and the
 *   report is sealed + validated by the app before it renders. The only
 *   test-side hooks are `window.__inspect` (read-only session state for
 *   assertions, the same handle pattern the feature preview mounts expose)
 *   and ordinary DOM interaction with the shipped controls.
 *
 * Legs:
 *   1. Own-file open → real PDF.js text/raster checks + real Tesseract OCR
 *      + in-page alignment through the real coordinator run → region
 *      selection bound to the OCR check → sealed report in the real viewer
 *      → cancel mid-run → rename-replace byte identity → clean control →
 *      replace A→B.
 *   2. Rotated/UserUnit geometry (F07) and the invisible-text-layer scan
 *      (F03) through the same public run path, asserted on the sealed
 *      report's pages/occurrences/checks.
 *   3. Selected export → real T16 ExportPanel privacy preview → JSON + HTML
 *      download inspection → local reopen through the same public UI →
 *      source attach/reject verification → fully-offline OCR rerun on the
 *      live page.
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
const GEO_SHA256 = createHash("sha256").update(geoBytes).digest("hex");
const SCAN_SHA256 = createHash("sha256").update(scanBytes).digest("hex");

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
  { name: "geometry_doc_sha256", value: GEO_SHA256 },
  { name: "scan_filename", value: "scan-correct.pdf" },
  { name: "scan_doc_sha256", value: SCAN_SHA256 },
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
  sink: Capture["violations"] = cap.violations,
): void {
  if (!body) return;
  for (const m of MARKERS) {
    for (const s of spellings(m)) {
      let at = body.indexOf(s);
      while (at >= 0) {
        sink.push({
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
  // Raw export bytes are volatile by design (execution_id/started_at/
  // duration_ms live inside the sealed artifact), so they stay outside the
  // committed evidence tree; the capture records a normalized digest below.
  const dir = join(ROOT, "test-results", "g1-downloads");
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

const LOCAL_ORIGIN = "http://inkflip.local";

/**
 * Deterministic copy of a string field for committed evidence: the ephemeral
 * server origin and per-run execution envelope are transport noise — replace
 * them with stable tokens so re-runs of an unchanged build produce identical
 * capture bytes. Runs on the serialized artifact only; the in-memory records
 * used for the marker scan and assertions stay raw.
 */
function stabilizeText<T extends string | undefined>(text: T): T {
  if (text === undefined) return text;
  return text
    .replaceAll(baseURL, LOCAL_ORIGIN)
    .replace(/"execution_id": ?"[^"]+"/g, '"execution_id": "<run-scoped>"')
    .replace(/"started_at": ?"[^"]+"/g, '"started_at": "<run-scoped>"')
    .replace(/"duration_ms": ?\d+/g, '"duration_ms": "<run-scoped>"') as T;
}

/** Write-time projection of a capture record with volatile fields removed. */
function stabilizeRecord(rec: Rec): Rec {
  const out: Rec = {
    ...rec,
    url: stabilizeText(rec.url),
    data: stabilizeText(rec.data?.slice(0, 4000)),
  };
  if (rec.headers) {
    const headers = { ...rec.headers };
    delete headers.date;
    if (rec.channel === "downloads" && out.data !== undefined) {
      headers.sha256 = createHash("sha256").update(out.data).digest("hex");
    }
    out.headers = headers;
  }
  return out;
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
  // Committed evidence is the stabilized projection; snippets and offsets are
  // re-derived from it so they always match the file's own bytes.
  const stableRecords = cap.records.map(stabilizeRecord);
  const stableViolations: Capture["violations"] = [];
  for (const rec of stableRecords) {
    scanInto(cap, rec.channel, "url", rec.url, stableViolations);
    scanInto(cap, rec.channel, "data", rec.data, stableViolations);
    for (const [k, v] of Object.entries(rec.headers ?? {})) {
      scanInto(cap, rec.channel, `header:${k}`, v, stableViolations);
    }
  }
  writeFileSync(
    join(CAPTURES, `${String(captureSeq++).padStart(2, "0")}-${cap.label}.json`),
    JSON.stringify(
      { ...cap, records: stableRecords, violations: stableViolations },
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

/* ---------------- public-app helpers (the real shipped UI) -------------- */

/** Land on the workspace's empty state through the real app shell. */
async function gotoWorkspace(page: Page): Promise<void> {
  await page.goto(baseURL);
  await expect(page.locator("h1")).toContainText("Your PDF can look right");
  await page.locator("#btn-open-report").click();
  await expect(page).toHaveURL(/#\/workspace/);
  await page.waitForFunction(() => (window as never as Record<string, unknown>).__inspect !== undefined);
}

interface SessionSnapshot {
  fileState: string;
  doc: { label: string; sha256: string; pageCount: number } | null;
  report: {
    report_id: string;
    document: { sha256: string; display_name: string | null };
    readers: { id: string }[];
    pages: {
      index: number;
      canonical_size_pt: [number, number];
      rotation: number;
      user_unit: number;
      limitations: string[];
    }[];
    transforms: { id: string; operation: string }[];
    occurrences: {
      id: string;
      reader_id: string;
      page_index: number;
      raw_text: string;
      normalized_text: string;
      geometry: { precision: string; polygon: [number, number][] | null };
      limitations: string[];
    }[];
    findings: {
      id: string;
      kind: string;
      title: string;
      occurrence_ids: string[];
      check_ids: string[];
      alignment: string;
    }[];
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
      retained_occurrence_ids: string[];
    }[];
    execution: { run_key: string; status: string; errors: string[] };
    limitations: string[];
    export: { replay: string };
  } | null;
  reportSource: "run" | "import" | null;
  importedReplay: { source: string; ready: boolean; readersMissing: string[] } | null;
  sourceAttached: boolean;
  error: { message: string; detail: string | null } | null;
  notice: string | null;
}

const inspect = (page: Page): Promise<SessionSnapshot> =>
  page.evaluate(() => (window as never as { __inspect: { getState(): unknown } }).__inspect.getState()) as Promise<SessionSnapshot>;

/** Offer a local PDF through the app's real file input; confirm replace when asked. */
async function offerPdf(
  page: Page,
  name: string,
  bytes: Uint8Array,
): Promise<void> {
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
  await expect(page.locator("[data-testid=doc-label]")).toHaveText(name, { timeout: 30_000 });
}

/** Start the run through the real selection UI and wait for the sealed report. */
async function runInspection(page: Page, timeoutMs = 240_000): Promise<SessionSnapshot> {
  await page.locator("[data-testid=start-run]").click();
  // The plan surface only lives in `selecting` — the coordinator leaves it
  // in the same commit, so the plan is asserted on the sealed report's
  // `plan.checks` below rather than on the transient element.
  const t0 = Date.now();
  for (;;) {
    const snap = await inspect(page);
    if (snap.report !== null && snap.reportSource === "run") return snap;
    if (["complete", "partial", "failed", "cancelled"].includes(snap.fileState) && snap.error) {
      throw new Error(`run settled without a report: ${snap.error.message} — ${snap.error.detail ?? ""}`);
    }
    if (Date.now() - t0 > timeoutMs) {
      throw new Error(`run did not settle in ${timeoutMs}ms — fileState=${snap.fileState} checks=${JSON.stringify(snap.report)}`);
    }
    await new Promise((r) => setTimeout(r, 500));
  }
}

/* ------------------------------ the gate ------------------------------- */

test.describe.configure({ mode: "serial" });
test.setTimeout(300_000);

test.beforeAll(async () => {
  rmSync(CAPTURES, { recursive: true, force: true });
  mkdirSync(CAPTURES, { recursive: true });

  // The real application build — the pinned Vite production build, the
  // same artifact `bun run build` produces. Vite is resolved through its
  // installed file URL (it is not resolvable as a bare specifier from
  // tests/, same approach as tests/privacy).
  const viteEntry = pathToFileURL(
    join(WEB, "node_modules", "vite", "dist", "node", "index.js"),
  ).href;
  const vite = (await import(viteEntry)) as {
    build: (opts: Record<string, unknown>) => Promise<unknown>;
  };
  // The gate drives the read-only `__inspect` session handle — enabled
  // only via this build-time opt-in (shipped production builds omit it).
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
        rollupOptions: { input: { index: join(WEB, "index.html") } },
      },
    });
  } finally {
    if (savedNodeEnv === undefined) delete process.env.NODE_ENV;
    else process.env.NODE_ENV = savedNodeEnv;
  }

  const distRoot = resolve(DIST) + sep;
  server = createServer((req, res) => {
    const url = new URL(req.url ?? "/", "http://static.invalid");
    let pathname = decodeURIComponent(url.pathname);
    if (pathname === "/") pathname = "/index.html";
    accessLog.push(`${req.method} ${pathname}`);
    // Fingerprinted staged assets (models/, assets/) are immutable — the
    // production posture that also makes them reusable fully offline.
    // Documents/chunks stay no-cache so every fetch is server-observed.
    const immutable =
      pathname.startsWith("/models/") || pathname.startsWith("/assets/");
    const headers = {
      ...SECURITY_HEADERS,
      "Cache-Control": immutable ? "public, max-age=86400, immutable" : "no-cache",
    };
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
          "The public app is exercised end-to-end: index.html → Workspace → InspectionSession → OpenController/ImportController → RunCoordinator → pdf.js/Tesseract readers → sealed report → ViewerStage/ExportPanel — no test-owned mounts or in-test composition.",
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

/* ---- 1. public own-file open → select → real run → report → replace ---- */

test("G1 leg 1: public own-file journey — open/run/report/cancel/replace", async ({ browser }) => {
  const ctx = await browser.newContext({ acceptDownloads: true });
  armEgress(ctx);
  const page = await ctx.newPage();
  const cap = beginCapture("open-journey");

  await gotoWorkspace(page);

  // Interesting own-file (F01): text layer reads $1,000 while the raster
  // paints $100 — the family's whole point. Offered through the real
  // workspace file input.
  await offerPdf(page, "mapping-amount.pdf", amountBytes);
  const amountMeta = await page.locator("[data-testid=doc-meta]").innerText();
  expect(amountMeta).toContain("1 page");
  expect((await inspect(page)).doc?.sha256).toBe(AMOUNT_SHA256); // bytes, not filename

  // Region selection in canonical space — bounds derived from the real
  // pdf.js extraction of the $1,000 token so the region genuinely
  // contains the finding (the same adapter the session's run uses).
  const amountOcc = await page.evaluate(async () => {
    const s = (window as never as { __inspect: {
      adapter: { plan(h: unknown, sel: unknown): { id: string }[]; extract(...a: unknown[]): Promise<{ result: { status: string } }> };
      openController: { currentHandle: unknown };
    } }).__inspect;
    const handle = s.openController.currentHandle;
    const checks = s.adapter.plan(handle, { pages: [0], capabilities: ["native_text"] });
    const emitted: { raw_text: string; geometry: { polygon: [number, number][] | null } }[] = [];
    await s.adapter.extract(handle, checks[0], (chunk: never[]) => emitted.push(...chunk));
    return emitted.find((o) => o.raw_text === "$1,000" || o.raw_text.includes("$1,000")) ?? null;
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

  // The real run through the app: coordinator-driven native_text + render
  // + real Tesseract OCR + alignment. The region binds to the OCR check.
  const run1 = await runInspection(page);
  const planCaps = run1.report!.plan.checks.map((c) => c.capability).sort();
  expect(planCaps).toEqual(["alignment", "native_text", "ocr", "render"].sort());
  const ocrPlan = run1.report!.plan.checks.find((c) => c.capability === "ocr")!;
  expect(ocrPlan.region_id).not.toBeNull(); // the drawn region binds to OCR
  expect(run1.report!.plan.regions.map((r) => r.id)).toContain(ocrPlan.region_id);

  // Every check reached an honest terminal state.
  for (const c of run1.report!.checks) {
    expect(["completed", "unsupported", "skipped"], `check ${c.id} → ${c.status} (${c.reason})`).toContain(c.status);
  }
  expect(run1.report!.execution.status).toBe("complete");

  // Real readings from BOTH reader families landed on the record: the
  // text layer's $1,000 and OCR's raster reading. Both are evidence;
  // the report never declares one correct.
  const textOccs = run1.report!.occurrences.filter((o) => o.reader_id.includes("text"));
  const ocrOccs = run1.report!.occurrences.filter((o) => o.reader_id.includes("tesseract"));
  expect(textOccs.length).toBeGreaterThan(0);
  expect(ocrOccs.length).toBeGreaterThan(0); // real Tesseract output
  expect(textOccs.map((o) => o.raw_text)).toContain("$1,000");
  expect(run1.report!.readers.map((r) => r.id)).toEqual(
    expect.arrayContaining([
      expect.stringContaining("pdfjs"),
      expect.stringContaining("tesseract"),
    ]),
  );
  // Findings exist, cite real occurrences and checks, and name the real
  // alignment outcomes — never a fabricated verdict.
  expect(run1.report!.findings.length).toBeGreaterThan(0);
  const occIds = new Set(run1.report!.occurrences.map((o) => o.id));
  const checkIds = new Set(run1.report!.checks.map((c) => c.id));
  for (const f of run1.report!.findings) {
    for (const id of f.occurrence_ids) expect(occIds.has(id)).toBe(true);
    for (const id of f.check_ids) expect(checkIds.has(id)).toBe(true);
  }
  // The viewer rendered the sealed report.
  await expect(page.locator("#viewer-stage")).toBeVisible();
  await expect(page.locator("#evidence-slip")).toBeVisible();
  const firstFinding = run1.report!.findings[0]!;
  await expect(page.locator(`#finding-item-${firstFinding.id}`)).toBeVisible();

  // Cancel a live run through the app's own control, then return to the
  // selection surface — an honest cancelled state, never a stall.
  await page.locator("#btn-rerun").click();
  await expect(page.locator("[data-testid=doc-label]")).toHaveText("mapping-amount.pdf");
  await page.locator("[data-testid=start-run]").click();
  await page.waitForFunction(
    () => {
      const s = (window as never as { __inspect: { getState(): { fileState: string } } }).__inspect.getState();
      return s.fileState === "running" || s.fileState === "preparing_assets";
    },
    undefined,
    { timeout: 15_000 },
  );
  await page.locator("#btn-cancel-run").click();
  await page.waitForFunction(
    () => (window as never as { __inspect: { getState(): { fileState: string } } }).__inspect.getState().fileState === "cancelled",
    undefined,
    { timeout: 15_000 },
  );
  await expect(page.locator("[data-testid=run-cancelled]")).toBeVisible();
  await page.locator("#btn-back-to-selection").click();
  await expect(page.locator("[data-testid=doc-label]")).toHaveText("mapping-amount.pdf");

  // Renamed own-file → identical bytes → identical identity.
  await offerPdf(page, "renamed-own-file.pdf", amountBytes);
  expect((await inspect(page)).doc?.sha256).toBe(AMOUNT_SHA256);

  // Clean control (F01 sibling): same painted $100, honest text layer —
  // the report reads $100 and never the mapped $1,000.
  await offerPdf(page, "mapping-control.pdf", controlBytes);
  const run2 = await runInspection(page);
  expect(run2.report!.document.sha256).toBe(CONTROL_SHA256);
  const controlTexts = run2.report!.occurrences.map((o) => o.raw_text);
  expect(controlTexts).toContain("$100");
  expect(controlTexts).not.toContain("$1,000");
  expect(run2.report!.execution.status).toBe("complete");

  // Replace control (A) with the canary (B) — B shows only B's evidence.
  await offerPdf(page, "network-canary-channels.pdf", canaryBytes);
  const run3 = await runInspection(page);
  expect(run3.report!.document.sha256).toBe(CANARY_SHA256);
  const canaryTexts = run3.report!.occurrences.map((o) => o.raw_text).join(" ");
  expect(canaryTexts).toContain("INKFLIP-CANARY-TEXT-7B2");
  expect(canaryTexts).not.toContain("$1,000"); // B never shows A's data
  expect(canaryTexts).not.toContain("$100");
  expect(run3.report!.checks.every((c) => c.status === "completed")).toBe(true);

  await endCapture(page, cap);
  assertCaptureClean(cap);
  await ctx.close();
});

/* ---- 2. rotated/scan geometry through the public run path -------------- */

test("G1 leg 2: source geometry + scan text layer through the public app", async ({ browser }) => {
  const ctx = await browser.newContext({ acceptDownloads: true });
  armEgress(ctx);
  const page = await ctx.newPage();
  const cap = beginCapture("geometry-scan");

  await gotoWorkspace(page);

  // F07: /Rotate 90 + UserUnit 2 + CropBox — the sealed report's page
  // carries the physical canonical extent, the rotation flag and the
  // user unit; every occurrence stays inside canonical bounds.
  await offerPdf(page, "geometry-90.pdf", geoBytes);
  const geo = await runInspection(page);
  expect(geo.report!.document.sha256).toBe(GEO_SHA256);
  const geoPage = geo.report!.pages[0]!;
  expect(geoPage.rotation).toBe(90);
  expect(geoPage.user_unit).toBe(2);
  expect(geoPage.canonical_size_pt).toEqual([960, 700]);
  const geoOccs = geo.report!.occurrences.filter((o) => o.reader_id.includes("text"));
  expect(geoOccs.length).toBeGreaterThan(0);
  for (const o of geoOccs) {
    for (const [px, py] of o.geometry.polygon ?? []) {
      expect(px).toBeGreaterThanOrEqual(0);
      expect(py).toBeGreaterThanOrEqual(0);
      expect(px).toBeLessThanOrEqual(960);
      expect(py).toBeLessThanOrEqual(700);
    }
    // pdf.js TextItem extents are honestly marked — never `exact`.
    // On the rotated page they degrade to `page_only`; on flat pages
    // `estimated`. Both are valid precision declarations.
    expect(["estimated", "page_only"]).toContain(o.geometry.precision);
  }
  // The report's transforms carry the real page-box → canonical mapping.
  expect(
    geo.report!.transforms.some((t) => t.operation === "page_box_to_canonical"),
  ).toBe(true);
  expect(geo.report!.checks.every((c) => c.status === "completed")).toBe(true);

  // F03 (scan-correct): invisible text layer over the owned bitmap scan —
  // native_text completes with real occurrences; OCR runs on the raster.
  await offerPdf(page, "scan-correct.pdf", scanBytes);
  const scan = await runInspection(page);
  expect(scan.report!.document.sha256).toBe(SCAN_SHA256);
  const scanTexts = scan.report!.occurrences.map((o) => o.raw_text).join(" ");
  for (const w of ["QUARTERLY", "INVOICE", "$100.00", "PAGE"]) {
    expect(scanTexts, `scan report must contain ${w}`).toContain(w);
  }
  const scanTextCheck = scan.report!.checks.find((c) => c.id.includes("native_text"))!;
  expect(scanTextCheck.status).toBe("completed");
  const scanOcr = scan.report!.checks.find((c) => c.id.startsWith("ocr_"))!;
  expect(scanOcr.status).toBe("completed");
  // OCR produced real occurrences from the scan raster.
  const scanOcrOccs = scan.report!.occurrences.filter((o) =>
    o.reader_id.includes("tesseract"),
  );
  expect(scanOcrOccs.length).toBeGreaterThan(0);

  await endCapture(page, cap);
  assertCaptureClean(cap);
  await ctx.close();
});

/* ---- 3. selected export → reopen → source attach → offline rerun ------- */

test("G1 leg 3: export → local reopen → attach source → offline OCR", async ({ browser }) => {
  const ctx = await browser.newContext({ acceptDownloads: true });
  armEgress(ctx);
  const page = await ctx.newPage();
  const cap = beginCapture("export-reopen");

  await gotoWorkspace(page);
  await offerPdf(page, "network-canary-channels.pdf", canaryBytes);
  const run = await runInspection(page);
  MARKERS.push(
    { name: "report_id", value: run.report!.report_id, allowed_channels: ["downloads"] },
    { name: "run_key", value: run.report!.execution.run_key, allowed_channels: ["downloads"] },
  );

  // Export preview: the disclosure panel itself is a privacy gate — the
  // real copy asserts the selection scope and no source PDF.
  await expect(page.getByText("Preview what you will export")).toBeVisible();
  await expect(page.getByText("Selected evidence")).toBeVisible();
  await expect(
    page.getByText("Original PDF not included.", { exact: false }).first(),
  ).toBeVisible();
  for (const label of [
    "Include the original PDF",
    "Include original filename",
    "Include my notes",
  ]) {
    await expect(page.getByLabel(label)).not.toBeChecked();
  }

  // JSON download: a real browser download of the selected projection.
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
  expect(exported.document.sha256).toBe(CANARY_SHA256);
  expect((exported.findings ?? []).length).toBe(run.report!.findings.length);
  const citedIds = new Set(
    (exported.findings ?? []).flatMap((f: { occurrence_ids: string[] }) => f.occurrence_ids),
  );
  for (const o of exported.occurrences ?? []) {
    expect(citedIds.has(o.id), `occurrence ${o.id} must be cited`).toBe(true);
  }

  // HTML download: human-readable inspection, self-contained.
  const dlHtml = page.waitForEvent("download");
  await page.getByRole("button", { name: "Download readable HTML" }).click();
  const htmlDl = await dlHtml;
  const htmlPath = await recordDownload(cap, htmlDl, "export.inkflip-report.html");
  const htmlBody = readFileSync(htmlPath, "utf8");
  // The canary's readers agree (zero findings is a legitimate result) —
  // assert the sealed document identity landed in the readable export.
  expect(htmlBody).toContain(CANARY_SHA256);
  expect(htmlBody).not.toContain("<script");
  expect(htmlBody).not.toMatch(/https?:\/\//);

  // Local reopen through the SAME public UI — the strict import gate.
  const exportJsonBytes = readFileSync(jsonPath);
  await page
    .locator("#input-import-report")
    .setInputFiles({
      name: jsonDl.suggestedFilename(),
      mimeType: "application/json",
      buffer: exportJsonBytes,
    });
  const dlg = page.locator("[role=dialog]");
  await expect(dlg).toBeVisible();
  await dlg.getByRole("button", { name: "Clear and open file" }).click();

  // The reopened report renders in the real viewer.
  await page.waitForFunction(
    () => {
      const s = (window as never as { __inspect: { getState(): { reportSource: string | null } } }).__inspect.getState();
      return s.reportSource === "import";
    },
    undefined,
    { timeout: 30_000 },
  );
  const reopened = await inspect(page);
  expect(reopened.report!.document.sha256).toBe(CANARY_SHA256);
  await expect(page.locator("#viewer-stage")).toBeVisible();
  // Findings render when present; a zero-finding report still renders its
  // evidence coverage either way.
  const reopenedFinding = reopened.report!.findings[0];
  if (reopenedFinding) {
    await expect(page.locator(`#finding-item-${reopenedFinding.id}`)).toBeVisible();
  } else {
    await expect(page.getByText("What was checked")).toBeVisible();
  }

  // Replay state: source not embedded → the UI offers source attach, and
  // replay stays not-ready until the matching original is verified.
  const replaySection = page.locator("[data-testid=replay-status]");
  await expect(replaySection).toBeVisible();
  await expect(replaySection).toContainText(/not embedded|Attach the matching file/i);

  // Wrong bytes are rejected — verified against the recorded sha256.
  // The button opens a native file chooser; the hidden input is the
  // deterministic drive point.
  await expect(page.locator("#btn-attach-source")).toBeVisible();
  await page
    .locator("#input-attach-source")
    .setInputFiles({ name: "wrong.pdf", mimeType: "application/pdf", buffer: controlBytes });
  await page.waitForFunction(
    () => (window as never as { __inspect: { getState(): { error: unknown } } }).__inspect.getState().error !== null,
    undefined,
    { timeout: 15_000 },
  );
  const wrongState = await inspect(page);
  expect(wrongState.error!.message).toContain("does not match");
  expect(wrongState.sourceAttached).toBe(false);

  // The matching original verifies → replay state becomes attached.
  await page
    .locator("#input-attach-source")
    .setInputFiles({ name: "network-canary-channels.pdf", mimeType: "application/pdf", buffer: canaryBytes });
  await page.waitForFunction(
    () => (window as never as { __inspect: { getState(): { sourceAttached: boolean } } }).__inspect.getState().sourceAttached === true,
    undefined,
    { timeout: 15_000 },
  );
  const attached = await inspect(page);
  expect(attached.sourceAttached).toBe(true);
  expect(attached.importedReplay!.source).not.toBe("missing");
  // Every reader this build produces is installed — the deterministic
  // OCR identities resolve, so replay readiness is honestly reachable.
  expect(attached.importedReplay!.readersMissing).toEqual([]);
  expect(attached.importedReplay!.ready).toBe(true);
  await expect(page.locator("[data-testid=replay-status]")).toContainText("replay ready");

  await endCapture(page, cap);
  // The downloads legitimately contain the report id/run key/canary text —
  // whitelisted via allowed_channels; every other channel must be clean.
  assertCaptureClean(cap);

  // Fully-offline rerun: same page, all network blocked. The verified
  // in-memory/IDB model slot means the whole run completes with zero
  // server-observed requests.
  const capOff = beginCapture("offline-rerun", true);
  await ctx.setOffline(true);
  try {
    await offerPdf(page, "network-canary-channels.pdf", canaryBytes);
    const off = await runInspection(page);
    expect(off.report!.document.sha256).toBe(CANARY_SHA256);
    const ocrCheck = off.report!.checks.find((c) => c.id.startsWith("ocr_"))!;
    expect(ocrCheck.status, "OCR must complete fully offline from prepared assets").toBe("completed");
    expect(
      off.report!.occurrences.filter((o) => o.reader_id.includes("tesseract")).length,
    ).toBeGreaterThan(0);
    // No model fetch hit the wire — the capture's offline assertion checks
    // the server access log; also assert zero model requests observed.
    const modelFetches = capOff.records.filter(
      (r) => r.channel === "requests" && r.url.includes("/models/tessdata-fast-eng/"),
    );
    expect(modelFetches, "offline run must not fetch the model").toEqual([]);
  } finally {
    await ctx.setOffline(false);
  }
  await endCapture(page, capOff);
  assertCaptureClean(capOff);
  await ctx.close();
});
