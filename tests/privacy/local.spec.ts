/**
 * T15 — Prove initial own-file no-egress behavior (TEST-15): real Chromium
 * coverage over the REAL BUILT site, not a dev server and not mocks.
 *
 * What "the actual built flow" means in this checkout: app composition
 * (T13) has not landed, so `index.html` is the shipped scaffold and the
 * real features ship as separate built mounts. This suite builds the REAL
 * artifacts with the pinned Vite production build —
 *   pass 1 (root apps/web): index.html + the T08 open mount
 *     (src/features/open/preview.html) + the T22 import mount
 *     (src/features/import/preview.html)
 *   pass 2 (root tests/privacy/harness): privacy.html — a TEST-OWNED page
 *     binding the real T09 pdf.js adapter, T10 TesseractOcrReader,
 *     T16 ExportPanel + export engine and the contracts helpers (same role
 *     as the feature mounts; documented as the composition gap).
 * The built tree is served over loopback by a plain static server that
 * applies the planned deployment `_headers` verbatim (CSP included) and
 * keeps an independent server-side access log — so the suite sees what a
 * static deployment would actually emit, while the proof never relies on
 * CSP (every channel is captured and asserted empty of canary material).
 *
 * Journey (invariant I08 + the PRIVACY_AND_NETWORK_TESTS scenario):
 *   cold boot -> open canary -> run plan -> malformed error -> replace ->
 *   real render -> real native-text -> REAL OCR (staged model download ->
 *   IndexedDB warm cache -> worker/wasm -> occurrences) -> real T16
 *   export preview + JSON/HTML downloads -> real T22 import reopen ->
 *   clear. Repeated warm and fully-offline legs follow on the same
 *   prepared context.
 *
 * Canary: a generated PDF whose filename, visible text, hidden Info
 * string, document sha256, pdf base64 head, raster pixels, a user note
 * (+ token), the report id, the run key and the export filename form
 * 11 unique greppable markers.
 * Every request URL/method/headers/body, response, request failure,
 * websocket, beacon/fetch/XHR/worker/service-worker/WebRTC/WebTransport/
 * form.submit tripwire, console payload, dialog, storage key and
 * server-observed path+headers is captured per leg and scanned for every
 * marker in raw, percent, base64, base64url and hex encodings — in-test
 * first (plus a cross-channel split-marker sweep), then again offline by
 * scripts/inspect_network_receipt.py, which additionally decodes base64
 * payloads and fails closed on absent evidence (the committed receipt
 * carries marker digests only, never marker material).
 *
 * Modes: cold (first navigation + first model download), warm (second run
 * reuses the verified IDB model slot), offline (the loaded page + prepared
 * assets complete the workflow with all network blocked; a cold offline
 * context fails specifically as unavailable_offline).
 */
import { execFileSync } from "node:child_process";
import { createHash } from "node:crypto";
import {
  existsSync,
  mkdirSync,
  readFileSync,
  readdirSync,
  rmSync,
  symlinkSync,
  writeFileSync,
} from "node:fs";
import { createServer, type Server } from "node:http";
import { dirname, join, normalize, resolve, sep } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

import {
  expect,
  test,
  type BrowserContext,
  type Page,
  type Request as PlaywrightRequest,
} from "@playwright/test";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..", "..");
const WEB = join(ROOT, "apps", "web");
const HARNESS = join(ROOT, "tests", "privacy", "harness");
const DIST = join(ROOT, "tests", "privacy", "dist");
const PRIVATE = join(ROOT, "tests", "privacy", ".private");
const CAPTURE_DIR = join(PRIVATE, "capture");
const CANARY_FILE = join(PRIVATE, "canary.json");
const ART = join(ROOT, "artifacts", "tasks", "T15");
const OPEN_MOUNT = "/src/features/open/preview.html";
const IMPORT_MOUNT = "/src/features/import/preview.html";
const HARNESS_PAGE = "/privacy.html";

// ---------------------------------------------------------------------------
// Canary markers (deterministic synthetic test strings — never real secrets).
// ---------------------------------------------------------------------------
const TOK = "9KQ2ZVX7T15";
const CANARY_NAME = `inkflip-canary-${TOK}.pdf`;
const CANARY_VISIBLE = `INKFLIP-CANARY-VISIBLE-${TOK}`;
const CANARY_HIDDEN = `INKFLIP-CANARY-HIDDEN-${TOK}`;
const CANARY_NOTE = `inkflip-canary-note-${TOK}"><svg onload=alert(1)>`;
const OTHER_NAME = "other-file.pdf";

interface Marker {
  id: string;
  value: string;
  allowed_channels?: string[];
}

const markers: Marker[] = [
  { id: "filename", value: CANARY_NAME },
  { id: "visible_text", value: CANARY_VISIBLE },
  { id: "hidden_text", value: CANARY_HIDDEN },
  { id: "note", value: CANARY_NOTE },
  // The distinctive token without its hostile trailer — survives inside
  // JSON-escaped payload strings where the raw full note could not match.
  { id: "note_token", value: `inkflip-canary-note-${TOK}` },
  // filled in as the journey produces them:
  // doc_sha256, pdf_b64_head, raster_sha256, report_id, run_key, export_filename
];

const b64 = (s: string) => Buffer.from(s, "utf8").toString("base64");

/** Marker spellings checked inline (the inspector checks a superset). */
function markerSpellings(m: Marker): string[] {
  const out = [m.value, encodeURIComponent(m.value), b64(m.value)];
  if (/^[0-9a-f]{64}$/.test(m.value)) {
    out.push(Buffer.from(m.value, "hex").toString("base64"));
  }
  return out.filter((v) => v.length >= 8);
}

// ---------------------------------------------------------------------------
// Canary PDF: real xref/PDF-1.4 bytes; visible marker text, hidden /Info
// marker, one page (612x792 Letter).
// ---------------------------------------------------------------------------
function buildCanaryPdf(
  visible = CANARY_VISIBLE,
  hidden = CANARY_HIDDEN,
): Uint8Array {
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
  // Hidden marker: document metadata that is never rendered or extracted
  // as visible text — still must never leave the browser.
  obj(6, `<< /Producer (${hidden}) /Title (${CANARY_NAME}) >>`);
  const xrefPos = len;
  push(
    "xref\n0 7\n0000000000 65535 f \n" +
      [1, 2, 3, 4, 5, 6]
        .map((i) => `${String(offsets[i]).padStart(10, "0")} 00000 n \n`)
        .join("") +
      `trailer\n<< /Size 7 /Root 1 0 R /Info 6 0 R >>\nstartxref\n${xrefPos}\n%%EOF\n`,
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
const PDF_B64_HEAD = Buffer.from(CANARY_BYTES.subarray(0, 48)).toString("base64");
markers.push(
  { id: "doc_sha256", value: CANARY_SHA256 },
  { id: "pdf_b64_head", value: PDF_B64_HEAD },
);

// ---------------------------------------------------------------------------
// Static server: serves the built tree with the planned deployment headers
// verbatim (planning/deployment/_headers) and keeps an access log used as
// an independent second capture channel.
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
  "Permissions-Policy":
    "camera=(), microphone=(), geolocation=(), payment=(), usb=()",
  "Cross-Origin-Resource-Policy": "same-origin",
};

function cacheControl(pathname: string): string {
  if (pathname === "/index.html" || pathname === "/" || pathname === "/release.json") {
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
  headers: Record<string, string | string[] | undefined>;
}

interface Harness {
  base: string;
  origin: string;
  accessLog: AccessEntry[];
  server: Server;
}

let harness: Harness;

function startStaticServer(): Promise<Harness> {
  const accessLog: AccessEntry[] = [];
  const distRoot = resolve(DIST) + sep;
  const server = createServer((req, res) => {
    const url = new URL(req.url ?? "/", "http://static.invalid");
    let pathname = decodeURIComponent(url.pathname);
    if (pathname === "/") pathname = "/index.html";
    const entry: AccessEntry = {
      method: req.method ?? "GET",
      path: pathname,
      query: url.search ? url.search.slice(1) : null,
      status: 200,
      // Server-side request headers — the second capture layer sees what
      // actually arrived on the wire, independent of the browser channel.
      headers: { ...req.headers },
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
    const file = normalize(join(DIST, pathname));
    if (!file.startsWith(distRoot) || !existsSync(file)) {
      entry.status = 404;
      res.writeHead(404, headers).end("not found");
      return;
    }
    const dot = pathname.lastIndexOf(".");
    const mime = (dot >= 0 && MIME[pathname.slice(dot)]) || "application/octet-stream";
    entry.status = 200;
    res
      .writeHead(200, { ...headers, "Content-Type": mime })
      .end(readFileSync(file));
  });
  return new Promise((resolvePromise) => {
    server.listen(0, "127.0.0.1", () => {
      const address = server.address();
      const port = typeof address === "object" && address !== null ? address.port : 0;
      const base = `http://127.0.0.1:${port}`;
      resolvePromise({ base, origin: base, accessLog, server });
    });
  });
}

// ---------------------------------------------------------------------------
// Build the real artifacts: pinned Vite production build, two passes.
// ---------------------------------------------------------------------------
test.beforeAll(async () => {
  rmSync(DIST, { recursive: true, force: true });
  rmSync(CAPTURE_DIR, { recursive: true, force: true });
  rmSync(join(HARNESS, "node_modules"), { recursive: true, force: true });
  mkdirSync(CAPTURE_DIR, { recursive: true });
  mkdirSync(ART, { recursive: true });

  // The harness lives outside apps/web (scope: tests/privacy only) and
  // bun's isolated linker keeps app deps under apps/web/node_modules, so
  // give plain node resolution a gitignored node_modules of symlinks —
  // the modules then resolve to the same realpaths the app uses.
  const shim = join(HARNESS, "node_modules");
  mkdirSync(shim, { recursive: true });
  for (const pkg of ["react", "react-dom", "pdfjs-dist", "tesseract.js"]) {
    symlinkSync(join(WEB, "node_modules", pkg), join(shim, pkg), "dir");
  }

  const viteEntry = pathToFileURL(
    join(WEB, "node_modules", "vite", "dist", "node", "index.js"),
  ).href;
  const vite = (await import(viteEntry)) as {
    build: (opts: Record<string, unknown>) => Promise<unknown>;
  };
  // Pass 1 — the real app build (apps/web root): shipped index plus the
  // real T08 open and T22 import feature mounts.
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
  // Pass 2 — the test-owned privacy harness page (tests/privacy/harness),
  // bundling the same production packages through the same build pipeline.
  await vite.build({
    root: HARNESS,
    configFile: join(WEB, "vite.config.ts"),
    logLevel: "warn",
    publicDir: false,
    build: {
      outDir: DIST,
      emptyOutDir: false,
      rollupOptions: {
        input: { privacy: join(HARNESS, "privacy.html") },
      },
    },
  });
  harness = await startStaticServer();
});

test.afterAll(async () => {
  harness?.server.close();
});

test.setTimeout(300_000);

// ---------------------------------------------------------------------------
// Capture scaffolding: per-leg request/ws/console/egress/storage records.
// ---------------------------------------------------------------------------
interface HeaderCarrier {
  headers: Record<string, string> | null;
}

interface Capture {
  schema_version: number;
  label: string;
  mode: "cold" | "warm" | "offline" | "online";
  surface: string;
  origin: string;
  cold_boot?: boolean;
  offline?: boolean;
  legs: { name: string; ok: boolean; detail?: string }[];
  requests: ({
    url: string;
    method: string;
    resource_type: string;
    is_navigation: boolean;
    post_body: string | null;
  } & HeaderCarrier)[];
  request_failures: ({
    url: string;
    method: string;
    error: string | null;
  } & HeaderCarrier)[];
  responses: { url: string; status: number }[];
  websockets: {
    url: string;
    frames_sent: string[];
    frames_received: string[];
  }[];
  egress: { kind: string; target: string; detail?: string }[];
  console: { type: string; text: string }[];
  page_errors: string[];
  dialogs: { type: string; message: string }[];
  downloads: { filename: string; bytes: number; sha256: string; kind: string }[];
  storage?: Record<string, unknown>;
  server_log: AccessEntry[];
}

let captureSeq = 0;
const capturesWritten: string[] = [];

function beginCapture(
  page: Page,
  label: string,
  mode: Capture["mode"],
  surface: string,
): Capture {
  const cap: Capture = {
    schema_version: 1,
    label,
    mode,
    surface,
    origin: harness.origin,
    legs: [],
    requests: [],
    request_failures: [],
    responses: [],
    websockets: [],
    egress: [],
    console: [],
    page_errors: [],
    dialogs: [],
    downloads: [],
    server_log: [],
  };
  // Header capture is async in Playwright — keep the live request objects
  // and resolve allHeaders() inside endCapture before assertions run.
  const pendingHeaders: { req: PlaywrightRequest; entry: HeaderCarrier }[] = [];
  (cap as { _pendingHeaders?: unknown })._pendingHeaders = pendingHeaders;
  page.on("request", (req) => {
    const entry: Capture["requests"][number] = {
      url: req.url(),
      method: req.method(),
      resource_type: req.resourceType(),
      is_navigation: req.isNavigationRequest(),
      post_body: req.postData(),
      headers: null,
    };
    pendingHeaders.push({ req, entry });
    cap.requests.push(entry);
  });
  page.on("requestfailed", (req) => {
    const entry: Capture["request_failures"][number] = {
      url: req.url(),
      method: req.method(),
      error: req.failure()?.errorText ?? null,
      headers: null,
    };
    pendingHeaders.push({ req, entry });
    cap.request_failures.push(entry);
  });
  page.on("response", (res) => {
    cap.responses.push({ url: res.url(), status: res.status() });
  });
  page.on("websocket", (ws) => {
    const entry = { url: ws.url(), frames_sent: [] as string[], frames_received: [] as string[] };
    cap.websockets.push(entry);
    ws.on("framesent", (f) => entry.frames_sent.push(String(f.payload).slice(0, 1000)));
    ws.on("framereceived", (f) => entry.frames_received.push(String(f.payload).slice(0, 1000)));
  });
  page.on("console", (msg) => {
    cap.console.push({ type: msg.type(), text: msg.text().slice(0, 2000) });
  });
  page.on("pageerror", (error) => {
    cap.page_errors.push(String(error).slice(0, 2000));
  });
  page.on("dialog", (dialog) => {
    // A fired alert()/confirm() is recorded, never silently swallowed —
    // the hostile annotation leg depends on this staying empty.
    cap.dialogs.push({ type: dialog.type(), message: dialog.message().slice(0, 1000) });
    void dialog.dismiss();
  });
  page.on("download", async (dl) => {
    const path = await dl.path();
    const bytes = path ? readFileSync(path) : Buffer.alloc(0);
    cap.downloads.push({
      filename: dl.suggestedFilename(),
      bytes: bytes.length,
      sha256: createHash("sha256").update(bytes).digest("hex"),
      kind: dl.suggestedFilename().endsWith(".json") ? "json" : "html",
    });
  });
  (cap as { _logStart?: number })._logStart = harness.accessLog.length;
  return cap;
}

/** Collect egress-tripwire + storage state from the live page. */
async function collectPageState(page: Page, cap: Capture, withStorage = true): Promise<void> {
  cap.egress = await page.evaluate(
    () => (globalThis as { __egress?: { kind: string; target: string; detail?: string }[] }).__egress ?? [],
  );
  if (withStorage) cap.storage = await storageDump(page);
}

async function endCapture(
  page: Page,
  cap: Capture,
  opts: { withStorage?: boolean; skipEval?: boolean } = {},
): Promise<void> {
  cap.server_log = harness.accessLog.slice(
    (cap as { _logStart?: number })._logStart ?? 0,
  );
  // Resolve async header capture before any assertion reads it; a header
  // that cannot be read stays null and fails closed in assertCaptureClean.
  const pending = (cap as { _pendingHeaders?: { req: PlaywrightRequest; entry: HeaderCarrier }[] })
    ._pendingHeaders ?? [];
  for (const { req, entry } of pending) {
    try {
      entry.headers = await req.allHeaders();
    } catch {
      entry.headers = null;
    }
  }
  delete (cap as { _pendingHeaders?: unknown })._pendingHeaders;
  if (opts.skipEval !== true) {
    await collectPageState(page, cap, opts.withStorage !== false);
  }
  assertCaptureClean(cap);
  const file = join(
    CAPTURE_DIR,
    `${String(captureSeq++).padStart(2, "0")}-${cap.label}.json`,
  );
  writeFileSync(file, JSON.stringify(cap, null, 2) + "\n");
  capturesWritten.push(file);
}

/** The in-test no-egress gate run on every completed leg capture. */
function assertCaptureClean(cap: Capture): void {
  const origin = harness.origin;
  if (!cap.offline) {
    expect(
      cap.requests.length,
      `${cap.label}: expected some requests`,
    ).toBeGreaterThan(0);
  }
  const wireChecks = (url: string, method: string, label: string) => {
    expect(url.startsWith(origin), `${cap.label} foreign ${label} ${url}`).toBe(true);
    expect(["GET", "HEAD", "OPTIONS"], `${cap.label} ${label} method ${method}`).toContain(method);
    const u = new URL(url);
    expect(u.search, `${cap.label} ${label} query in ${u.pathname}`).toBe("");
  };
  for (const req of cap.requests) {
    wireChecks(req.url, req.method, "request");
    // Headers must be captured — an unread header block is an unmonitored
    // channel and fails closed here rather than passing unseen.
    expect(req.headers, `${cap.label} headers not captured for ${req.url}`).not.toBeNull();
  }
  for (const req of cap.request_failures) {
    wireChecks(req.url, req.method, "request_failure");
    expect(
      req.headers,
      `${cap.label} failure headers not captured for ${req.url}`,
    ).not.toBeNull();
  }
  expect(cap.websockets, `${cap.label} websockets`).toHaveLength(0);
  expect(cap.dialogs, `${cap.label} unexpected dialog`).toHaveLength(0);
  const BAD_EGRESS = new Set([
    "beacon",
    "eventsource",
    "window.open",
    "serviceworker.register",
    "websocket",
    "webrtc",
    "webtransport",
    "form.submit",
  ]);
  const SAME_ORIGIN_EGRESS = new Set(["fetch", "xhr", "worker"]);
  for (const e of cap.egress) {
    // Unknown kinds fail closed — a channel the tripwire learned to emit
    // later can never slip past unexamined.
    expect(
      BAD_EGRESS.has(e.kind) || SAME_ORIGIN_EGRESS.has(e.kind),
      `${cap.label} unrecognized egress kind ${e.kind}`,
    ).toBe(true);
    expect(
      BAD_EGRESS.has(e.kind),
      `${cap.label} ${e.kind} egress channel used toward ${e.target}`,
    ).toBe(false);
    if (SAME_ORIGIN_EGRESS.has(e.kind)) {
      const resolved = new URL(e.target, origin);
      expect(
        resolved.origin === origin || resolved.protocol === "blob:" || resolved.protocol === "data:",
        `${cap.label} foreign ${e.kind} target ${e.target}`,
      ).toBe(true);
    }
  }
  const haystacks: { channel: string; text: string }[] = [];
  cap.requests.forEach((r, i) => {
    haystacks.push({ channel: `requests[${i}].url`, text: r.url });
    haystacks.push({ channel: `requests[${i}].headers`, text: JSON.stringify(r.headers) });
    if (r.post_body !== null) {
      haystacks.push({ channel: `requests[${i}].post`, text: r.post_body });
    }
  });
  cap.request_failures.forEach((r, i) => {
    haystacks.push({ channel: `request_failures[${i}].url`, text: r.url });
    haystacks.push({ channel: `request_failures[${i}].headers`, text: JSON.stringify(r.headers) });
  });
  cap.responses.forEach((r, i) =>
    haystacks.push({ channel: `responses[${i}].url`, text: r.url }),
  );
  cap.egress.forEach((e, i) => {
    haystacks.push({ channel: `egress[${i}]`, text: `${e.target} ${e.detail ?? ""}` });
  });
  cap.console.forEach((m, i) => haystacks.push({ channel: `console[${i}]`, text: m.text }));
  cap.page_errors.forEach((m, i) => haystacks.push({ channel: `page_errors[${i}]`, text: m }));
  cap.legs.forEach((l, i) => {
    if (l.detail !== undefined) {
      haystacks.push({ channel: `legs[${i}].detail`, text: l.detail });
    }
  });
  cap.dialogs.forEach((d, i) =>
    haystacks.push({ channel: `dialogs[${i}]`, text: d.message }),
  );
  cap.server_log.forEach((e, i) =>
    haystacks.push({
      channel: `server_log[${i}]`,
      text: `${e.path} ${e.query ?? ""} ${JSON.stringify(e.headers)}`,
    }),
  );
  if (cap.storage) {
    for (const [field, value] of Object.entries(cap.storage)) {
      haystacks.push({
        channel: `storage.${field}`,
        text: typeof value === "string" ? value : JSON.stringify(value),
      });
    }
  }
  for (const marker of markers) {
    const allowed = marker.allowed_channels ?? [];
    const scoped = haystacks.filter(
      ({ channel }) => !allowed.includes(channel.split("[")[0]),
    );
    for (const spelling of markerSpellings(marker)) {
      for (const { channel, text } of scoped) {
        expect(
          text.includes(spelling),
          `${cap.label}: marker ${marker.id} (${spelling.slice(0, 24)}…) in ${channel}`,
        ).toBe(false);
      }
      // Split-marker sweep: a marker smeared across two log lines is
      // caught by scanning the concatenation and a whitespace-collapsed
      // variant (the offline inspector additionally decodes base64
      // payloads — that layer is authoritative).
      const joined = scoped.map((h) => h.text).join("");
      expect(
        joined.includes(spelling),
        `${cap.label}: marker ${marker.id} split across channels`,
      ).toBe(false);
      expect(
        joined.replace(/\s+/g, "").includes(spelling),
        `${cap.label}: marker ${marker.id} split across whitespace`,
      ).toBe(false);
    }
  }
}

async function storageDump(page: Page): Promise<Record<string, unknown>> {
  return page.evaluate(async () => {
    const dump: Record<string, unknown> = {
      local: {} as Record<string, string | null>,
      session: {} as Record<string, string | null>,
      cookies: document.cookie,
      idb: [] as unknown[],
      cache_storage: [] as string[],
      service_workers: 0,
    };
    const local = dump.local as Record<string, string | null>;
    for (let i = 0; i < window.localStorage.length; i++) {
      const k = window.localStorage.key(i)!;
      local[k] = window.localStorage.getItem(k);
    }
    const session = dump.session as Record<string, string | null>;
    for (let i = 0; i < window.sessionStorage.length; i++) {
      const k = window.sessionStorage.key(i)!;
      session[k] = window.sessionStorage.getItem(k);
    }
    if (navigator.serviceWorker?.getRegistrations) {
      dump.service_workers = (await navigator.serviceWorker.getRegistrations()).length;
    }
    if (window.caches?.keys) {
      for (const name of await window.caches.keys()) {
        const store = await window.caches.open(name);
        for (const request of await store.keys()) {
          (dump.cache_storage as string[]).push(`${name}:${request.url}`);
        }
      }
    }
    if (indexedDB.databases) {
      const hex = (buf: ArrayBuffer) =>
        [...new Uint8Array(buf)].map((b) => b.toString(16).padStart(2, "0")).join("");
      for (const info of await indexedDB.databases()) {
        if (!info.name) continue;
        const db = await new Promise<IDBDatabase>((res, rej) => {
          const req = indexedDB.open(info.name!, info.version);
          req.onsuccess = () => res(req.result);
          req.onerror = () => rej(req.error);
          req.onblocked = () => rej(new Error("idb blocked"));
        });
        for (const storeName of Array.from(db.objectStoreNames)) {
          const store = db.transaction(storeName, "readonly").objectStore(storeName);
          const keys = await new Promise<IDBValidKey[]>((res, rej) => {
            const req = store.getAllKeys();
            req.onsuccess = () => res(req.result);
            req.onerror = () => rej(req.error);
          });
          for (const key of keys) {
            const value = await new Promise<unknown>((res, rej) => {
              const req = store.get(key);
              req.onsuccess = () => res(req.result);
              req.onerror = () => rej(req.error);
            });
            (dump.idb as unknown[]).push({
              db: info.name,
              store: storeName,
              key: String(key),
              value_sha256:
                value instanceof Uint8Array
                  ? hex(await crypto.subtle.digest("SHA-256", value.slice().buffer))
                  : null,
              bytes: value instanceof Uint8Array ? value.byteLength : null,
            });
          }
        }
        db.close();
      }
    }
    return dump;
  });
}

/** Egress tripwires installed before any app script runs (every channel). */
async function armEgress(context: BrowserContext): Promise<void> {
  await context.addInitScript(() => {
    const w = globalThis as unknown as {
      __egress: { kind: string; target: string; detail?: string }[];
      fetch: typeof fetch;
      WebSocket: typeof WebSocket;
      EventSource: typeof EventSource;
      Worker: typeof Worker;
    };
    w.__egress = [];
    const rec = (kind: string, target: unknown, detail?: unknown) => {
      w.__egress.push({
        kind,
        target: String(target),
        ...(detail === undefined ? {} : { detail: String(detail).slice(0, 300) }),
      });
    };
    const nativeFetch = window.fetch?.bind(window);
    if (nativeFetch) {
      window.fetch = ((input: RequestInfo | URL, init?: RequestInit) => {
        rec(
          "fetch",
          typeof input === "string" ? input : input instanceof URL ? input.href : input.url,
          init?.method ?? (typeof input === "object" && "method" in input ? input.method : "GET"),
        );
        return nativeFetch(input as never, init as never);
      }) as typeof fetch;
    }
    const nativeOpen = window.XMLHttpRequest.prototype.open;
    window.XMLHttpRequest.prototype.open = function (
      this: XMLHttpRequest,
      method: string,
      url: string | URL,
    ) {
      rec("xhr", url, method);
      // @ts-expect-error pass through with original arity
      return nativeOpen.apply(this, arguments);
    };
    const nativeBeacon = window.navigator.sendBeacon?.bind(window.navigator);
    if (nativeBeacon) {
      window.navigator.sendBeacon = ((url: string | URL, data?: unknown) => {
        rec("beacon", url, data == null ? "empty" : typeof data);
        return nativeBeacon(url, data as never);
      }) as typeof navigator.sendBeacon;
    }
    const NativeWebSocket = window.WebSocket;
    window.WebSocket = class extends NativeWebSocket {
      constructor(url: string | URL, protocols?: string | string[]) {
        rec("websocket", url);
        super(url, protocols);
      }
    } as typeof WebSocket;
    const NativeEventSource = window.EventSource;
    if (typeof NativeEventSource === "function") {
      window.EventSource = class extends NativeEventSource {
        constructor(url: string | URL, config?: EventSourceInit) {
          rec("eventsource", url);
          super(url, config);
        }
      } as typeof EventSource;
    }
    const nativeWindowOpen = window.open?.bind(window);
    if (nativeWindowOpen) {
      window.open = ((url?: string | URL, target?: string, features?: string) => {
        rec("window.open", url);
        return nativeWindowOpen(url as string, target, features);
      }) as typeof window.open;
    }
    const sw = window.navigator.serviceWorker;
    if (sw?.register) {
      const nativeRegister = sw.register.bind(sw);
      sw.register = ((url: string | URL, options?: RegistrationOptions) => {
        rec("serviceworker.register", url);
        return nativeRegister(url, options);
      }) as ServiceWorkerContainer["register"];
    }
    const NativeWorker = window.Worker;
    window.Worker = class extends NativeWorker {
      constructor(url: string | URL, options?: WorkerOptions) {
        rec("worker", url);
        super(url, options);
      }
    } as typeof Worker;
    // WebRTC/WebTransport emit no 'request' events — construction is
    // recorded so an unused-today channel can never open silently.
    const ww = globalThis as unknown as Record<string, unknown>;
    const NativeRTC = ww.RTCPeerConnection as
      | (new (config?: { iceServers?: unknown }) => unknown)
      | undefined;
    if (typeof NativeRTC === "function") {
      ww.RTCPeerConnection = class extends NativeRTC {
        constructor(config?: { iceServers?: unknown }) {
          rec("webrtc", JSON.stringify(config?.iceServers ?? []));
          super(config);
        }
      };
    }
    const NativeWT = ww.WebTransport as
      | (new (url: string | URL, opts?: unknown) => unknown)
      | undefined;
    if (typeof NativeWT === "function") {
      ww.WebTransport = class extends NativeWT {
        constructor(url: string | URL, opts?: unknown) {
          rec("webtransport", url);
          super(url, opts);
        }
      };
    }
    const nativeSubmit = window.HTMLFormElement?.prototype.submit;
    if (nativeSubmit) {
      window.HTMLFormElement.prototype.submit = function (this: HTMLFormElement) {
        rec("form.submit", this.action || "(no action)");
        return nativeSubmit.call(this);
      };
    }
    const nativeRequestSubmit = window.HTMLFormElement?.prototype.requestSubmit;
    if (nativeRequestSubmit) {
      window.HTMLFormElement.prototype.requestSubmit = function (
        this: HTMLFormElement,
        submitter?: HTMLElement,
      ) {
        rec("form.submit", this.action || "(no action)");
        return nativeRequestSubmit.call(this, submitter);
      };
    }
  });
}

// ---------------------------------------------------------------------------
// Page helpers
// ---------------------------------------------------------------------------
async function offerFile(
  page: Page,
  testid: string,
  name: string,
  bytes: Uint8Array,
  mimeType: string,
): Promise<void> {
  await page.locator(`[data-testid=${testid}]`).setInputFiles({
    name,
    mimeType,
    buffer: Buffer.from(bytes),
  });
}

async function leg<T>(
  cap: Capture,
  name: string,
  fn: () => Promise<T>,
): Promise<T> {
  try {
    const value = await fn();
    cap.legs.push({ name, ok: true });
    return value;
  } catch (error) {
    cap.legs.push({
      name,
      ok: false,
      detail: String(error instanceof Error ? error.message : error).slice(0, 1000),
    });
    throw error;
  }
}

let ctxA: BrowserContext;
let warmPage: Page;
let warmReaderId: string;
let warmCheckId: string;
let exportJsonBytes: Buffer;
let exportFileName: string;
let reportId: string;
let sealedColdReport: Record<string, unknown>;

// ---------------------------------------------------------------------------
// TEST 1 — cold journey on the built site.
// ---------------------------------------------------------------------------
test("cold: built-site own-file journey leaves zero document trace", async ({
  browser,
}) => {
  ctxA = await browser.newContext({ acceptDownloads: true });
  await armEgress(ctxA);
  const page = await ctxA.newPage();

  // -- Cold fixed-asset assessment: first navigation requests only built
  //    files; assessed separately per the contract. ----------------------
  const capBoot = beginCapture(page, "cold-boot-index", "cold", "/index.html");
  capBoot.cold_boot = true;
  await leg(capBoot, "navigate-index", async () => {
    await page.goto(`${harness.base}/`);
    await expect(
      page.getByText("Your PDF can look right"),
      "shipped scaffold should render",
    ).toBeVisible();
  });
  const bootPaths = capBoot.requests.map((r) => new URL(r.url).pathname);
  expect(bootPaths).toContain("/");
  for (const p of bootPaths) {
    expect(
      p === "/" || p === "/index.html" || p.startsWith("/assets/"),
      `cold boot fetched non-asset ${p}`,
    ).toBe(true);
  }
  await endCapture(page, capBoot);

  // -- Open mount: real pdf.js open + render + run plan + error leg. -----
  const capOpen = beginCapture(page, "cold-open-mount", "cold", OPEN_MOUNT);
  await leg(capOpen, "navigate-open-mount", async () => {
    await page.goto(`${harness.base}${OPEN_MOUNT}`);
    await page.waitForFunction(
      () => (globalThis as { __t08?: unknown }).__t08 !== undefined,
      undefined,
      { timeout: 30_000 },
    );
    await expect(page.locator("[data-testid=file-drop]")).toBeVisible();
  });
  await leg(capOpen, "open-canary", async () => {
    await offerFile(page, "file-input", CANARY_NAME, CANARY_BYTES, "application/pdf");
    await expect(page.locator("[data-testid=doc-label]")).toHaveText(CANARY_NAME, {
      timeout: 30_000,
    });
    // The document name renders in DOM — a local label that must never
    // reach any URL or payload (asserted by assertCaptureClean).
    await expect(page.locator("[data-testid=doc-meta]")).toContainText(
      CANARY_SHA256.slice(-8),
    );
  });
  await leg(capOpen, "real-render-raster", async () => {
    const canvas = page.locator("[data-testid=region-canvas]");
    await expect
      .poll(async () => Number(await canvas.getAttribute("width")), {
        timeout: 30_000,
      })
      .toBeGreaterThan(0);
  });
  await leg(capOpen, "run-plan-includes-ocr", async () => {
    await page.locator("[data-testid=start-run]").click();
    await expect(page.locator("[data-testid=plan]")).toBeVisible();
    const caps = await page
      .locator("[data-testid=plan-checks] li")
      .evaluateAll((els) => els.map((e) => e.getAttribute("data-capability")));
    expect(caps).toContain("ocr");
    expect(caps).toContain("native_text");
    expect(caps).toContain("render");
  });
  await leg(capOpen, "error-malformed", async () => {
    // With a document open, any second offer goes through the replace
    // dialog first — confirm it, then the malformed bytes hit the real
    // validation path and the typed error surfaces.
    const truncated = CANARY_BYTES.slice(0, 160);
    await offerFile(page, "file-input", "broken.pdf", truncated, "application/pdf");
    await page
      .getByRole("button", { name: "Clear and open file" })
      .click({ timeout: 10_000 });
    await expect(page.locator("#open-error-malformed")).toBeVisible({
      timeout: 15_000,
    });
  });
  await leg(capOpen, "reopen-and-replace", async () => {
    // After the rejected offer the workspace is empty again.
    await offerFile(page, "file-input", CANARY_NAME, CANARY_BYTES, "application/pdf");
    await expect(page.locator("[data-testid=doc-label]")).toHaveText(CANARY_NAME, {
      timeout: 30_000,
    });
    // Offering a second, genuinely different document surfaces the
    // explicit replace confirmation.
    const other = buildCanaryPdf("SECOND-DOC-LINE-0K1P", "SECOND-DOC-HIDDEN");
    await offerFile(page, "file-input", OTHER_NAME, other, "application/pdf");
    await page
      .getByRole("button", { name: "Clear and open file" })
      .click({ timeout: 10_000 });
    await expect(page.locator("[data-testid=doc-label]")).toHaveText(OTHER_NAME, {
      timeout: 30_000,
    });
  });
  await leg(capOpen, "clear-file", async () => {
    await page.locator("[data-testid=clear-file]").click();
    await expect(page.locator("[data-testid=doc-label]")).toHaveCount(0);
    await expect(page.locator("[data-testid=file-input]")).toBeEnabled();
  });
  await endCapture(page, capOpen);

  // -- Harness page: real native text, real render, REAL OCR, real export.
  const capHarness = beginCapture(page, "cold-harness-ocr-export", "cold", HARNESS_PAGE);
  let textEmitted: {
    id: string;
    geometry: { polygon: number[][] };
    raw_text: string;
  }[] = [];
  let textCheck: Record<string, unknown>;
  let textResult: Record<string, unknown>;
  let renderPlan: Record<string, unknown>;
  let renderResult: Record<string, unknown>;
  let renderTransforms: unknown[];
  let ocrCheckPlan: Record<string, unknown>;
  let pagesContract: { pages: unknown[]; transforms: unknown[] };
  let rasterSha = "";
  let ocrOut: {
    output: {
      check: Record<string, unknown>;
      reader: Record<string, unknown>;
      occurrences: { id: string }[];
      transforms: unknown[];
      raw: { text: string | null };
      diagnostics: { wordCount: number };
      model: { state: string; provenance: string | null; sha256: string };
    };
  };
  let canaryOccurrence: { id: string; geometry: { polygon: number[][] } } | undefined;

  await leg(capHarness, "navigate-harness", async () => {
    await page.goto(`${harness.base}${HARNESS_PAGE}`);
    await page.waitForFunction(
      () => (globalThis as { __t15?: { engineKind?: string } }).__t15 !== undefined,
      undefined,
      { timeout: 30_000 },
    );
    const kind = await page.evaluate(
      () => (globalThis as { __t15: { engineKind: string } }).__t15.engineKind,
    );
    expect(kind).toBe("function");
  });
  const docRef = await leg(capHarness, "open-canary-adapter", async () => {
    const r = await page.evaluate(
      async (arr) => (globalThis as any).__t15.openDoc(arr),
      Array.from(CANARY_BYTES),
    );
    expect(r.ok).toBe(true);
    expect(r.value.sha256).toBe(CANARY_SHA256);
    expect(r.value.pageCount).toBe(1);
    return r.value as { docId: string; sha256: string };
  });
  await leg(capHarness, "contract-pages", async () => {
    const r = await page.evaluate(
      async (id) => (globalThis as any).__t15.contractPages(id),
      docRef.docId,
    );
    expect(r.ok).toBe(true);
    pagesContract = r.value as typeof pagesContract;
    expect(pagesContract!.pages).toHaveLength(1);
  });
  await leg(capHarness, "native-text-canary", async () => {
    const r = await page.evaluate(
      async (id) => (globalThis as any).__t15.extractText(id, 0, "region_canary"),
      docRef.docId,
    );
    expect(r.ok).toBe(true);
    textCheck = r.value.plan;
    textResult = r.value.result;
    textEmitted = r.value.emitted as typeof textEmitted;
    canaryOccurrence = textEmitted.find((o) => o.raw_text.includes("CANARY"));
    expect(
      canaryOccurrence,
      "canary visible text should be extracted by the real reader",
    ).toBeTruthy();
  });
  await leg(capHarness, "render-raster", async () => {
    const r = await page.evaluate(
      async (id) => (globalThis as any).__t15.rasterize(id, 0, 2),
      docRef.docId,
    );
    expect(r.ok).toBe(true);
    rasterSha = r.value.pixelSha256;
    renderResult = r.value.check;
    renderPlan = r.value.plan;
    renderTransforms = r.value.transforms;
    expect(r.value.widthPx).toBeGreaterThan(0);
    markers.push({ id: "raster_sha256", value: rasterSha });
  });
  const ocrReader = await leg(capHarness, "ocr-reader", async () => {
    const r = await page.evaluate(
      async (id) => (globalThis as any).__t15.makeOcrReader(id, "t15-run-cold"),
      docRef.docId,
    );
    return r.readerId as string;
  });
  await leg(capHarness, "ocr-prepare-cold", async () => {
    const r = await page.evaluate(
      async (id) => (globalThis as any).__t15.ocrPrepare(id),
      ocrReader,
    );
    expect(r.ok).toBe(true);
    // Cold mode: the staged same-origin model was fetched and verified.
    expect(r.value.provenance).toBe("network");
    expect(r.value.state).toBe("ready_memory");
    const modelFetches = capHarness.requests.filter((q) =>
      q.url.includes("/models/tessdata-fast-eng/"),
    );
    expect(modelFetches).toHaveLength(1);
  });
  await leg(capHarness, "ocr-open-plan-extract", async () => {
    let r = await page.evaluate(
      async (args) => (globalThis as any).__t15.ocrOpen(...args),
      [ocrReader, CANARY_SHA256, 1] as const,
    );
    expect(r.ok).toBe(true);
    const polygon = canaryOccurrence!.geometry.polygon;
    r = await page.evaluate(
      async (args) => (globalThis as any).__t15.ocrPlan(...args),
      [
        ocrReader,
        [
          {
            pageIndex: 0,
            purpose: "region",
            region: {
              id: "region_canary",
              polygon,
              label: "Canary visible line",
            },
          },
        ],
      ] as const,
    );
    expect(r.ok).toBe(true);
    const checks = r.value as { id: string }[];
    expect(checks.length).toBe(1);
    ocrCheckPlan = checks[0] as unknown as Record<string, unknown>;
    r = await page.evaluate(
      async (args) => (globalThis as any).__t15.ocrExtract(...args),
      [ocrReader, checks[0].id] as const,
    );
    expect(r.ok).toBe(true);
    ocrOut = r.value as typeof ocrOut;
    expect(ocrOut.output.diagnostics.wordCount).toBeGreaterThan(0);
    expect(ocrOut.output.occurrences.length).toBeGreaterThan(0);
    expect(ocrOut.output.model.sha256).toBe(
      "7d4322bd2a7749724879683fc3912cb542f19906c83bcc1a52132556427170b2",
    );
  });

  // -- Assemble the run report in-page from the REAL canary readings,
  //    seal it, and drive the real ExportPanel to actual downloads. ------
  const report = await leg(capHarness, "assemble-seal-report", async () => {
    const report = await page.evaluate(
      async (parts) => {
        const t = (globalThis as any).__t15;
        const rep = {
          kind: "report",
          schema_version: "1.0.0",
          report_id: "0".repeat(64),
          document: parts.document,
          readers: parts.readers,
          pages: parts.pages,
          transforms: parts.transforms,
          occurrences: parts.occurrences,
          findings: parts.findings,
          annotations: parts.annotations,
          plan: parts.plan,
          checks: parts.checks,
          execution: parts.execution,
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
            "T15 privacy suite: report assembled in-page from the actual pdf.js/tesseract readings of the canary document.",
          ],
        };
        return t.seal(rep);
      },
      {
        document: {
          sha256: CANARY_SHA256,
          byte_length: CANARY_BYTES.length,
          page_count: 1,
          display_name: CANARY_NAME,
          source_asset_id: null,
        },
        readers: [
          await page.evaluate(() => (globalThis as any).__t15.adapter.readers.text),
          await page.evaluate(() => (globalThis as any).__t15.adapter.readers.render),
          // The output Reader record — bound to the real raster dpi.
          ocrOut!.output.reader,
        ],
        pages: pagesContract!.pages,
        transforms: [
          ...new Map(
            [
              ...pagesContract!.transforms,
              ...renderTransforms!,
              ...ocrOut!.output.transforms,
            ].map((t) => [(t as { id: string }).id, t]),
          ).values(),
        ],
        occurrences: [...textEmitted, ...ocrOut!.output.occurrences],
        findings: [
          {
            id: "f_canary",
            kind: "reading_difference",
            title: `Canary readings differ on ${CANARY_VISIBLE}`,
            explanation:
              "The named text reader and the OCR reader produced different raw strings for the same selected region; neither output alone establishes document truth.",
            page_index: 0,
            occurrence_ids: [canaryOccurrence!.id, ocrOut!.output.occurrences[0]!.id],
            check_ids: [(textCheck as { id: string }).id, (ocrOut!.output.check as { id: string }).id],
            alignment: "page_level",
            region_id: "region_canary",
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
            text: CANARY_NOTE,
            author_label: "t15-privacy",
            origin: "human_entered",
          },
        ],
        plan: {
          version: "1.0.0",
          selected_pages: [0],
          regions: [
            {
              id: "region_canary",
              page_index: 0,
              geometry: canaryOccurrence!.geometry,
              label: "Canary visible line",
            },
          ],
          checks: [textCheck, renderPlan, ocrCheckPlan],
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
        checks: [textResult, renderResult, ocrOut!.output.check],
        execution: {
          execution_id: crypto.randomUUID(),
          run_key: "0".repeat(64),
          status: "complete",
          started_at: new Date().toISOString(),
          duration_ms: 1,
          environment: "Chromium (Playwright) · t15 privacy harness",
          result_origin: "live",
          errors: [],
        },
      },
    );
    reportId = (report as { report_id: string }).report_id;
    markers.push({
      id: "report_id",
      value: reportId,
      allowed_channels: ["downloads"],
    });
    markers.push({
      id: "run_key",
      value: (report as { execution: { run_key: string } }).execution.run_key,
      allowed_channels: ["downloads"],
    });
    sealedColdReport = report as Record<string, unknown>;
    return sealedColdReport;
  });

  await leg(capHarness, "export-panel-downloads", async () => {
    await page.evaluate(
      async (args) =>
        (globalThis as any).__t15.showExportPanel(args[0], args[1]),
      [report, Array.from(CANARY_BYTES)] as const,
    );
    await expect(page.getByText("Preview what you will export")).toBeVisible();
    // Explicit opt-ins: original bytes, filename and notes ride inside the
    // LOCAL download — the strongest canary-carrying artifact the app makes.
    await page.getByLabel("Include the original PDF").check();
    await page.getByLabel("Include original filename").check();
    await page.getByLabel("Include my notes").check();
    await expect(page.getByText("Original PDF included.")).toBeVisible();

    const dlJson = page.waitForEvent("download");
    await page.getByRole("button", { name: "Download portable JSON" }).click();
    const jsonDl = await dlJson;
    exportFileName = jsonDl.suggestedFilename();
    const jsonPath = await jsonDl.path();
    exportJsonBytes = readFileSync(jsonPath!);
    const parsed = JSON.parse(exportJsonBytes.toString("utf8"));
    // The local artifact genuinely embeds the canary document and markers.
    expect(parsed.document.sha256).toBe(CANARY_SHA256);
    expect(parsed.document.display_name).toBe(CANARY_NAME);
    expect(parsed.document.source_asset_id).not.toBeNull();
    const annotationTexts = (parsed.annotations ?? []).map(
      (a: { text: string }) => a.text,
    );
    expect(annotationTexts).toContain(CANARY_NOTE);
    markers.push({
      id: "export_filename",
      value: exportFileName,
      allowed_channels: ["downloads"],
    });

    const dlHtml = page.waitForEvent("download");
    await page.getByRole("button", { name: "Download readable HTML" }).click();
    const htmlDl = await dlHtml;
    const htmlPath = await htmlDl.path();
    const htmlBytes = readFileSync(htmlPath!);
    expect(htmlBytes.toString("utf8")).toContain("inkflip");
  });
  await endCapture(page, capHarness);

  // -- Import mount: reopen the REAL exported file through the real gate.
  const capImport = beginCapture(page, "cold-import-reopen", "cold", IMPORT_MOUNT);
  await leg(capImport, "navigate-import-mount", async () => {
    await page.goto(`${harness.base}${IMPORT_MOUNT}`);
    await page.waitForFunction(
      () => (globalThis as { __t22?: unknown }).__t22 !== undefined,
      undefined,
      { timeout: 30_000 },
    );
    await expect(page.locator("[data-testid=import-drop]")).toBeVisible();
  });
  await leg(capImport, "reopen-export", async () => {
    await page.locator("[data-testid=import-file-input]").setInputFiles({
      name: exportFileName,
      mimeType: "application/json",
      buffer: exportJsonBytes,
    });
    await expect(page.locator("[data-testid=import-report]")).toBeVisible({
      timeout: 30_000,
    });
    // The reopened report is bound to the canary document identity with
    // the embedded original — the replayable path exercised end-to-end.
    await expect(page.locator("[data-testid=report-id]")).toContainText(
      CANARY_SHA256.slice(-12),
    );
    await expect(page.locator("[data-testid=source-embedded]")).toContainText(
      "Original PDF included",
    );
    await expect(page.locator("[data-testid=replay-state]")).toContainText(
      "Replay also requires the recorded reader environment",
    );
  });
  await endCapture(page, capImport);

  // Persist the private canary manifest for the inspector (never committed:
  // tests/privacy/.private is gitignored; the receipt carries digests only).
  const canaryManifest = {
    document: {
      filename: CANARY_NAME,
      byte_length: CANARY_BYTES.length,
      sha256: CANARY_SHA256,
    },
    model_sha256: "7d4322bd2a7749724879683fc3912cb542f19906c83bcc1a52132556427170b2",
    markers,
    limitations: [
      "App composition (T13) is not landed: the journey drives the real built feature mounts plus a test-owned harness page in sequence — the same production code paths the composed shell will call.",
      "Browser automation cannot see every OS/browser process channel; per planning, release-profile proof additionally needs a proxy/firewall capture.",
      "No service worker ships: offline support means an already-loaded page with prepared assets, verified here; cold offline navigation has no app shell to load and is not claimed.",
      "WebRTC/WebTransport are tripwired (construction is recorded) and asserted unused across the whole journey — verified absent from the built bundles; an already-open data channel's inner frames are not separately captured, so the guarantee is constructor-level.",
      "Log-channel scans are bounded by capture truncation (console/page-error 2000 chars, leg/egress/dialog details 1000, ws frames 1000); network carriers are closed by method/query/allowlist/header checks, so the residual escape window is log-text only — the inspector additionally scans joined and base64-decoded payloads to shrink it.",
    ],
  };
  writeFileSync(CANARY_FILE, JSON.stringify(canaryManifest, null, 2) + "\n");
});

// ---------------------------------------------------------------------------
// TEST 2 — warm mode: same prepared context, model from the verified cache.
// ---------------------------------------------------------------------------
test("warm: second run reuses verified cached model — zero asset refetch", async () => {
  warmPage = await ctxA.newPage();
  const cap = beginCapture(warmPage, "warm-harness", "warm", HARNESS_PAGE);
  await leg(cap, "navigate-harness", async () => {
    await warmPage.goto(`${harness.base}${HARNESS_PAGE}`);
    await warmPage.waitForFunction(
      () => (globalThis as { __t15?: unknown }).__t15 !== undefined,
      undefined,
      { timeout: 30_000 },
    );
  });
  const docRef = await leg(cap, "open-canary-adapter", async () => {
    const r = await warmPage.evaluate(
      async (arr) => (globalThis as any).__t15.openDoc(arr),
      Array.from(CANARY_BYTES),
    );
    expect(r.ok).toBe(true);
    return r.value as { docId: string };
  });
  await leg(cap, "render-raster", async () => {
    const r = await warmPage.evaluate(
      async (id) => (globalThis as any).__t15.rasterize(id, 0, 2),
      docRef.docId,
    );
    expect(r.ok).toBe(true);
  });
  const ocrReader = await leg(cap, "ocr-reader", async () => {
    const r = await warmPage.evaluate(
      async (id) => (globalThis as any).__t15.makeOcrReader(id, "t15-run-warm"),
      docRef.docId,
    );
    return r.readerId as string;
  });
  warmReaderId = ocrReader;
  await leg(cap, "ocr-prepare-warm", async () => {
    const r = await warmPage.evaluate(
      async (id) => (globalThis as any).__t15.ocrPrepare(id),
      ocrReader,
    );
    expect(r.ok).toBe(true);
    // Warm mode: the verified IndexedDB slot supplies the model — no fetch.
    expect(r.value.provenance).toBe("cache");
    expect(r.value.state).toBe("ready_cached");
    const modelFetches = cap.requests.filter((q) =>
      q.url.includes("/models/tessdata-fast-eng/"),
    );
    expect(modelFetches, "warm mode must not refetch the model").toHaveLength(0);
  });
  await leg(cap, "ocr-extract-warm", async () => {
    let r = await warmPage.evaluate(
      async (args) => (globalThis as any).__t15.ocrOpen(...args),
      [ocrReader, CANARY_SHA256, 2] as const,
    );
    expect(r.ok).toBe(true);
    r = await warmPage.evaluate(
      async (args) => (globalThis as any).__t15.ocrPlan(...args),
      [
        ocrReader,
        [
          {
            pageIndex: 0,
            purpose: "region",
            region: {
              id: "region_canary",
              polygon: [
                [40, 60],
                [580, 60],
                [580, 140],
                [40, 140],
              ],
              label: "Canary visible line",
            },
          },
        ],
      ] as const,
    );
    expect(r.ok).toBe(true);
    const checks = r.value as { id: string }[];
    warmCheckId = checks[0]!.id;
    r = await warmPage.evaluate(
      async (args) => (globalThis as any).__t15.ocrExtract(...args),
      [ocrReader, warmCheckId] as const,
    );
    expect(r.ok).toBe(true);
    expect(r.value.output.diagnostics.wordCount).toBeGreaterThan(0);
    // open() re-prepares internally and records 'memory' — the verified
    // bytes were already resident; the cache provenance was asserted at
    // prepare() and the zero-model-fetch check is on the capture below.
    expect(r.value.output.model.provenance).toBe("memory");
  });
  await leg(cap, "export-engine-warm", async () => {
    // The real sealed report from the cold run — projected and serialized
    // again on the warm page through the same engine.
    const text = await warmPage.evaluate(async (src) => {
      const t = (globalThis as any).__t15;
      const { report } = t.exportEngine.projectReport(src, {});
      return t.exportEngine.serializeReportJson(report);
    }, sealedColdReport);
    expect(text.endsWith("\n")).toBe(true);
    expect(text).toContain("INKFLIP-CANARY-VISIBLE");
  });
  await endCapture(warmPage, cap);
});

// ---------------------------------------------------------------------------
// TEST 3 — offline mode: the loaded page + prepared assets complete the
// workflow with ALL network blocked; a cold offline context fails honestly.
// ---------------------------------------------------------------------------
test("offline: prepared page completes workflow with zero requests; cold offline fails specifically", async ({
  browser,
}) => {
  // The warm page stays loaded — its pdf.js worker, OCR worker, model
  // bytes and document handle are all live in memory.
  const cap = beginCapture(warmPage, "offline-harness", "offline", HARNESS_PAGE);
  cap.offline = true;
  await ctxA.setOffline(true);
  try {
    await leg(cap, "offline-ocr-extract", async () => {
      // Re-extract on the live warm reader: live worker + in-memory model —
      // the check must complete with literally zero network.
      const r = await warmPage.evaluate(
        async (args) => (globalThis as any).__t15.ocrExtract(...args),
        [warmReaderId, warmCheckId] as const,
      );
      expect(r.ok).toBe(true);
      expect(r.value.output.diagnostics.wordCount).toBeGreaterThan(0);
      // Recorded provenance is 'memory' — open() reused the verified
      // in-memory bytes; nothing touched the network.
      expect(r.value.output.model.provenance).toBe("memory");
    });
    await leg(cap, "offline-open-and-render", async () => {
      // The pdf.js worker is already resident in this page: a fresh
      // getDocument + text extract + render run entirely from memory.
      const r = await warmPage.evaluate(
        async (arr) => {
          const t = (globalThis as any).__t15;
          const opened = await t.openDoc(arr);
          if (!opened.ok) return { step: "open", opened };
          const text = await t.extractText(opened.value.docId, 0, null);
          if (!text.ok) return { step: "text", text };
          const raster = await t.rasterize(opened.value.docId, 0, 2);
          return { step: "raster", raster };
        },
        Array.from(CANARY_BYTES),
      );
      expect(r.step).toBe("raster");
      expect(r.raster.ok).toBe(true);
    });
    await leg(cap, "offline-export", async () => {
      const name = await warmPage.evaluate(async (src) => {
        const t = (globalThis as any).__t15;
        const { report } = t.exportEngine.projectReport(src, {});
        return t.exportEngine.exportFileName(report, "json");
      }, sealedColdReport);
      expect(name.startsWith("inkflip-evidence-")).toBe(true);
    });
    // Offline evidence: a fresh getDocument spawns a pdf.js worker and a
    // standard-font fetch — both were satisfied by the prepared browser
    // HTTP cache (immutable static assets). The honest assertions:
    //   * zero requests ever reached the server (access log empty);
    //   * zero requests failed;
    //   * every request stayed inside the same-origin allowlist
    //     (asserted for every capture by assertCaptureClean below).
    const serverHits = harness.accessLog.slice(
      (cap as { _logStart?: number })._logStart ?? 0,
    );
    expect(serverHits, "offline requests reached the server").toHaveLength(0);
    expect(cap.request_failures, "offline failed requests").toHaveLength(0);
    for (const req of cap.requests) {
      const p = new URL(req.url).pathname;
      expect(
        p.startsWith("/assets/") || p.startsWith("/models/"),
        `offline cache-served request outside fixed assets: ${p}`,
      ).toBe(true);
    }
    await endCapture(warmPage, cap);
  } finally {
    await ctxA.setOffline(false);
  }

  // -- Cold offline: a fresh context (no prepared IDB model, no resident
  //    worker) fails specifically as unavailable_offline — never silently.
  //    The navigation itself happens online in its own capture; the
  //    offline capture starts at the setOffline boundary.
  const ctxB = await browser.newContext({ acceptDownloads: true });
  await armEgress(ctxB);
  try {
    const pageB = await ctxB.newPage();
    // This navigation runs ONLINE — it prepares the page the offline leg
    // needs; mode 'online' keeps the label honest (no offline flag, no
    // offline assertions) while the file name records which scenario it
    // belongs to.
    const capNav = beginCapture(pageB, "offline-cold-nav", "online", HARNESS_PAGE);
    await leg(capNav, "navigate-harness", async () => {
      await pageB.goto(`${harness.base}${HARNESS_PAGE}`);
      await pageB.waitForFunction(
        () => (globalThis as { __t15?: unknown }).__t15 !== undefined,
        undefined,
        { timeout: 30_000 },
      );
    });
    await endCapture(pageB, capNav);

    const capB = beginCapture(pageB, "offline-cold-model", "offline", HARNESS_PAGE);
    capB.offline = true;
    await ctxB.setOffline(true);
    await leg(capB, "cold-offline-model-fails", async () => {
      // The staged model fetch fails offline in a fresh profile — the
      // adapter reports the typed unavailable_offline/missing_model state.
      const r = await pageB.evaluate(async () => {
        const t = (globalThis as any).__t15;
        const reader = t.makeOcrReader(null, "t15-run-cold-offline");
        return t.ocrPrepare(reader.readerId);
      });
      expect(r.ok).toBe(false);
      expect(["unavailable_offline", "missing_model"]).toContain(r.error.reason);
    });
    // Collect egress + storage BEFORE the navigation attempt — a blocked
    // navigation destroys the execution context, after which no evaluate
    // can run.
    await collectPageState(pageB, capB);
    await leg(capB, "cold-offline-nav-blocked", async () => {
      // Cold navigation while offline has no app shell to load — the site
      // ships no service worker, so this is the documented boundary.
      const nav = await pageB
        .goto(`${harness.base}/`, { timeout: 10_000 })
        .then(() => "navigated")
        .catch(() => "blocked");
      expect(nav).toBe("blocked");
    });
    await endCapture(pageB, capB, { skipEval: true });
  } finally {
    await ctxB.setOffline(false);
    await ctxB.close();
  }
});

// ---------------------------------------------------------------------------
// TEST 4 — the inspector turns the captures into the committed receipt.
// ---------------------------------------------------------------------------
test("receipt: offline inspector validates every capture", async () => {
  expect(existsSync(CANARY_FILE)).toBe(true);
  expect(capturesWritten.length).toBeGreaterThanOrEqual(5);
  const receiptPath = join(ART, "network-receipt.json");
  const redactedDir = join(ART, "capture");
  // Stale redacted copies from earlier runs must not survive — wipe first.
  rmSync(redactedDir, { recursive: true, force: true });
  execFileSync(
    "python3",
    [
      "scripts/inspect_network_receipt.py",
      "--capture",
      CAPTURE_DIR,
      "--canary",
      CANARY_FILE,
      "--dist",
      DIST,
      "--receipt",
      receiptPath,
      "--redacted-capture",
      redactedDir,
      "--require-modes",
      "cold,warm,offline",
    ],
    { cwd: ROOT, stdio: "pipe" },
  );
  const receipt = JSON.parse(readFileSync(receiptPath, "utf8"));
  expect(receipt.verdict).toBe("pass");
  expect(receipt.checks.length).toBeGreaterThanOrEqual(8);
  for (const check of receipt.checks) {
    expect(check.status, `receipt check ${check.id}`).toBe("pass");
  }
  // The committed artifact carries marker digests — never marker material.
  const receiptText = readFileSync(receiptPath, "utf8");
  for (const marker of markers) {
    expect(receiptText.includes(marker.value), `receipt embeds ${marker.id}`).toBe(false);
  }
  // Redacted capture copies exist and are marker-free.
  const redacted = readdirSync(redactedDir);
  expect(redacted.length).toBe(capturesWritten.length);
  for (const file of redacted) {
    const text = readFileSync(join(redactedDir, file), "utf8");
    for (const marker of markers) {
      expect(text.includes(marker.value), `${file} embeds ${marker.id}`).toBe(false);
    }
  }
});

